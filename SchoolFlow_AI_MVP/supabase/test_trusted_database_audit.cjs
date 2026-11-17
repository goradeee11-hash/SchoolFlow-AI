// Isolated PGlite database; auth.uid() is simulated and no remote service is used.
const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const read = name => fs.readFileSync(path.join(__dirname, 'migrations', name), 'utf8');
const initial = read('202611150001_initial_schoolflow.sql')
  .replace(/^create extension if not exists pgcrypto;\s*/i, '');
const legacy = read('202611160001_append_audit_events.sql');
const trusted = read('202611170001_trusted_database_audit.sql');
const school = '00000000-0000-0000-0000-000000000001';
const other = '00000000-0000-0000-0000-000000000002';
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

async function exercise(withLegacyRpc) {
  const db = new PGlite();
  try {
    await db.exec(bootstrap);
    await db.exec(initial);
    if (withLegacyRpc) await db.exec(legacy);
    await db.exec(`
      insert into auth.users values ('${admin}'), ('${teacher}'), ('${otherAdmin}');
      insert into public.schools(id, name) values ('${school}', 'Synthetic'), ('${other}', 'Other');
      insert into public.school_memberships(school_id, user_id, role) values
        ('${school}', '${admin}', 'school_admin'), ('${school}', '${teacher}', 'teacher'),
        ('${other}', '${otherAdmin}', 'school_admin');
      insert into public.students(school_id,student_code,display_name,created_by)
        values ('${school}', 'S1', 'Synthetic', '${admin}');
      select set_config('request.jwt.claim.sub', '${teacher}', false);
      insert into public.audit_events(school_id,event_id,action,status,entity_type,occurred_at,record_data)
        values ('${school}','old','claimed','success','students',now(),'{}');
      select set_config('request.jwt.claim.sub', '', false);
    `);
    if (withLegacyRpc) {
      const signature = (await db.query(`select proargnames, oidvectortypes(proargtypes) as types
        from pg_proc where oid = 'public.append_audit_events(uuid,jsonb)'::regprocedure`)).rows[0];
      assert.deepEqual(signature.proargnames, ['p_school_id', 'p_events']);
      assert.equal(signature.types, 'uuid, jsonb');
      await db.exec(`select set_config('request.jwt.claim.sub','${teacher}',false);
        set role authenticated;
        select public.append_audit_events(p_events => '[]'::jsonb, p_school_id => '${school}');
        reset role;
        select set_config('request.jwt.claim.sub','',false)`);
    }
    await db.exec(trusted);
    await db.exec(trusted);

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
    await db.exec(`update public.students set display_name='Updated' where student_code='S1'`);
    await denied(`insert into public.audit_events(school_id,event_id,actor_user_id,actor_role,action,status,entity_type,occurred_at,record_data)
      values ('${school}','fake','${admin}','school_admin','fake','success','students',now(),'{}')`);
    await denied("update public.audit_events set action='fake'");
    await denied('delete from public.audit_events');
    if (withLegacyRpc) {
      await denied(`select public.append_audit_events('${school}','[]'::jsonb)`);
    }
    assert.equal((await db.query('select * from public.audit_events')).rows.length, 0);

    await identity(admin);
    const events = (await db.query(`select event_id, actor_user_id, actor_role, action,
      status, entity_type, record_data, database_generated from public.audit_events`)).rows;
    assert.equal(events.length, 2);
    assert.equal(events.find(row => row.event_id === 'old').database_generated, false);
    const generated = events.find(row => row.database_generated);
    assert.equal(generated.actor_user_id, teacher);
    assert.equal(generated.actor_role, 'teacher');
    assert.equal(generated.action, 'update');
    assert.equal(generated.status, 'success');
    assert.equal(generated.entity_type, 'students');
    assert.deepEqual(generated.record_data.entity_key, { student_code: 'S1' });
    await denied('delete from public.audit_events');
    await identity(otherAdmin);
    assert.equal((await db.query('select * from public.audit_events')).rows.length, 0);

    await db.exec('reset role');
    await db.exec(`create function public.reject_test_audit() returns trigger language plpgsql
      as $$ begin raise exception 'test audit failure'; end $$;
      create trigger reject_test_audit before insert on public.audit_events
      for each row execute function public.reject_test_audit()`);
    await identity(teacher);
    await assert.rejects(() => db.exec("update public.students set display_name='Must roll back' where student_code='S1'"),
      error => error.message.includes('test audit failure'));
    assert.equal((await db.query("select display_name from public.students where student_code='S1'")).rows[0].display_name, 'Updated');
    console.log(`PASS trusted audit, forgery denial and rollback (${withLegacyRpc ? 'legacy RPC present' : 'legacy RPC absent'})`);
  } finally {
    await db.close();
  }
}

async function main() {
  await exercise(false);
  await exercise(true);
  const collision = new PGlite();
  try {
    await collision.exec(bootstrap);
    await collision.exec(initial);
    await collision.exec('alter table public.audit_events add column database_generated boolean not null default false');
    await assert.rejects(() => collision.exec(trusted), error =>
      error.message.includes('Existing audit provenance column requires manual review'));
    console.log('PASS existing provenance column requires manual review');
  } finally {
    await collision.close();
  }
  const overload = new PGlite();
  try {
    await overload.exec(bootstrap);
    await overload.exec(initial);
    await overload.exec(`create function public.append_audit_events(jsonb)
      returns void language sql as $$ select $$`);
    await assert.rejects(() => overload.exec(trusted), error =>
      error.message.includes('Unexpected append_audit_events overload requires manual review'));
    console.log('PASS unexpected legacy RPC overload requires manual review');
  } finally {
    await overload.close();
  }
}
main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
