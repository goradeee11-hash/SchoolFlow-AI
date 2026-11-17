// Run with an existing @electric-sql/pglite installation; no remote connection.
const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = __dirname;
const initial = fs.readFileSync(path.join(root, 'migrations', '202611150001_initial_schoolflow.sql'), 'utf8')
  .replace(/^create extension if not exists pgcrypto;\s*/i, '');
const audit = fs.readFileSync(path.join(root, 'migrations', '202611160001_append_audit_events.sql'), 'utf8');
const draft = fs.readFileSync(path.join(root, 'migration_drafts', '202611160002_class_isolation_and_trusted_audit.sql'), 'utf8');
const school = '00000000-0000-0000-0000-000000000001';
const otherSchool = '00000000-0000-0000-0000-000000000002';
const admin = '10000000-0000-0000-0000-000000000001';
const teacher = '10000000-0000-0000-0000-000000000002';
const otherAdmin = '10000000-0000-0000-0000-000000000003';
const bootstrap = `
  create role anon;
  create role authenticated;
  create schema auth;
  create table auth.users (id uuid primary key);
  create function auth.uid() returns uuid language sql stable
    as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema auth to authenticated, anon;
  grant execute on function auth.uid() to authenticated, anon;
`;

async function main() {
  const db = new PGlite();
  try {
    await db.exec(bootstrap);
    await db.exec(initial);
    await db.exec(audit);
    await db.exec(`
      insert into auth.users values ('${admin}'), ('${teacher}'), ('${otherAdmin}');
      insert into public.schools(id, name) values ('${school}', 'Demo 1'), ('${otherSchool}', 'Demo 2');
      insert into public.school_memberships(school_id, user_id, role) values
        ('${school}', '${admin}', 'school_admin'),
        ('${school}', '${teacher}', 'teacher'),
        ('${otherSchool}', '${otherAdmin}', 'school_admin');
      insert into public.classes(school_id, class_id, class_name, created_by) values
        ('${school}', 'assigned', 'Assigned', '${admin}'),
        ('${school}', 'other', 'Other', '${admin}'),
        ('${otherSchool}', 'other-school', 'Other school', '${otherAdmin}');
      insert into public.class_assignments(school_id, class_id, teacher_id, created_by)
        values ('${school}', 'assigned', '${teacher}', '${admin}');
      insert into public.students(school_id, student_code, class_id, display_name, created_by) values
        ('${school}', 'A', 'assigned', 'Synthetic A', '${admin}'),
        ('${school}', 'B', 'other', 'Synthetic B', '${admin}'),
        ('${school}', 'legacy', null, 'Synthetic legacy', '${admin}'),
        ('${otherSchool}', 'C', 'other-school', 'Synthetic C', '${otherAdmin}');
      insert into public.skills(school_id, skill_id, name, record_data, created_by)
        values ('${school}', 'legacy', 'Legacy', '{"private":"synthetic"}', '${admin}');
      select set_config('request.jwt.claim.sub', '${teacher}', false);
      insert into public.audit_events(school_id, event_id, action, status, entity_type, occurred_at, record_data)
        values ('${school}', 'legacy-event', 'claimed', 'success', 'students', now(), '{}');
      select set_config('request.jwt.claim.sub', '', false);
    `);
    await db.exec(draft);
    await db.exec(draft);

    async function identity(user) {
      await db.exec('reset role');
      await db.query("select set_config('request.jwt.claim.sub', $1, false)", [user]);
      await db.exec('set role authenticated');
    }
    async function denied(sql) {
      await assert.rejects(() => db.exec(sql), error => error.code === '42501');
    }

    await identity(teacher);
    assert.equal((await db.query('select public.schoolflow_audit_mode() as mode')).rows[0].mode, 'database');
    assert.deepEqual((await db.query('select class_id from public.classes')).rows, [{ class_id: 'assigned' }]);
    console.log('PASS 1 teacher reads assigned class');
    assert.equal((await db.query("select class_id from public.classes where class_id='other'")).rows.length, 0);
    console.log('PASS 2 teacher cannot read unassigned class');
    assert.deepEqual((await db.query('select student_code from public.students')).rows, [{ student_code: 'A' }]);
    assert.equal((await db.query("update public.students set display_name='Changed' where student_code='B' returning student_code")).rows.length, 0);
    console.log('PASS 3 teacher cannot read or update another class student');
    assert.equal((await db.query("delete from public.class_assignments where class_id='assigned' returning class_id")).rows.length, 0);
    assert.equal((await db.query("update public.class_assignments set class_id='other' where class_id='assigned' returning class_id")).rows.length, 0);
    await denied(`insert into public.class_assignments(school_id,class_id,teacher_id)
      values ('${school}','other','${teacher}')`);
    await denied("update public.students set class_id='other' where student_code='A'");
    await denied(`update public.students set created_by='${teacher}' where student_code='A'`);
    assert.equal((await db.query(`update public.school_memberships set role='school_admin'
      where school_id='${school}' and user_id='${teacher}' returning user_id`)).rows.length, 0);
    assert.equal((await db.query("update public.classes set class_name='Changed' where class_id='assigned' returning class_id")).rows.length, 0);
    console.log('PASS 4 teacher cannot change assignments or memberships');
    assert.equal((await db.query('select * from public.skills')).rows.length, 0);
    assert.equal((await db.query("update public.students set display_name='Updated' where student_code='A' returning student_code")).rows.length, 1);
    await denied(`select public.append_audit_events('${school}',
      '[{"event_id":"forged","action":"forged","status":"success","entity_type":"students","occurred_at":"2000-01-01","record_data":{}}]'::jsonb)`);
    await denied(`insert into public.audit_events(school_id,event_id,actor_user_id,actor_role,action,status,entity_type,occurred_at,record_data)
      values ('${school}','forged','${admin}','school_admin','forged','success','students',now(),'{}')`);
    await denied("update public.audit_events set action='forged'");
    await denied('delete from public.audit_events');
    console.log('PASS 6 direct and RPC audit forgery denied');

    await identity(admin);
    assert.equal((await db.query(`select * from public.classes where school_id='${otherSchool}'`)).rows.length, 0);
    assert.equal((await db.query(`select * from public.students where school_id='${otherSchool}'`)).rows.length, 0);
    assert.equal((await db.query(`update public.school_memberships set role='teacher'
      where school_id='${otherSchool}' returning user_id`)).rows.length, 0);
    console.log('PASS 5 admin cannot access another school');
    assert.equal((await db.query("select student_code from public.students where student_code='legacy'")).rows.length, 1);
    const events = (await db.query("select event_id, actor_user_id, actor_role, action, status, entity_type, record_data, database_generated from public.audit_events")).rows;
    assert.equal(events.length, 2);
    const legacyEvent = events.find(event => event.event_id === 'legacy-event');
    assert.equal(legacyEvent.database_generated, false);
    const generated = events.find(event => event.database_generated);
    delete generated.event_id;
    assert.deepEqual(generated, {
      actor_user_id: teacher, actor_role: 'teacher', action: 'update',
      status: 'success', entity_type: 'students',
      record_data: { source: 'database_trigger', entity_key: { student_code: 'A', class_id: 'assigned' } },
      database_generated: true,
    });
    console.log('PASS generated audit event reflects the actual update');
    console.log('PASS legacy student retained for administrator; legacy JSON hidden from teacher');

    const collision = new PGlite();
    try {
      await collision.exec(bootstrap);
      await collision.exec(initial);
      await collision.exec(audit);
      await collision.exec('alter table public.audit_events add column database_generated boolean not null default false');
      await assert.rejects(() => collision.exec(draft), error =>
        error.message.includes('Existing audit provenance column requires manual review'));
      console.log('PASS pre-existing audit provenance column requires manual review');
    } finally {
      await collision.close();
    }
  } finally {
    await db.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
