// Uses an existing @electric-sql/pglite installation; no remote connection.
const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = __dirname;
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');
const initial = read('migrations', '202611150001_initial_schoolflow.sql')
  .replace(/^create extension if not exists pgcrypto;\s*/i, '');
const audit = read('migrations', '202611160001_append_audit_events.sql');
const isolation = read('migration_drafts', '202611160002_class_isolation_and_trusted_audit.sql');
const imports = read('migration_drafts', '202611160003_class_imports.sql');
const structure = read('migration_drafts', '202611160004_school_structure.sql');
const s1 = '00000000-0000-0000-0000-000000000001';
const s2 = '00000000-0000-0000-0000-000000000002';
const a1 = '10000000-0000-0000-0000-000000000001';
const a2 = '10000000-0000-0000-0000-000000000002';
const t1 = '10000000-0000-0000-0000-000000000003';
const t2 = '10000000-0000-0000-0000-000000000004';
const stage1 = '20000000-0000-0000-0000-000000000001';
const stage2 = '20000000-0000-0000-0000-000000000002';
const stageOther = '20000000-0000-0000-0000-000000000003';
const grade1 = '30000000-0000-0000-0000-000000000001';
const grade2 = '30000000-0000-0000-0000-000000000002';
const math = '40000000-0000-0000-0000-000000000001';
const science = '40000000-0000-0000-0000-000000000002';
const otherSubject = '40000000-0000-0000-0000-000000000003';

async function main() {
  const db = new PGlite();
  try {
    await db.exec(`
      create role anon;
      create role authenticated;
      create schema auth;
      create table auth.users (id uuid primary key);
      create function auth.uid() returns uuid language sql stable
        as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
      grant usage on schema auth to authenticated, anon;
      grant execute on function auth.uid() to authenticated, anon;
    `);
    await db.exec(initial);
    await db.exec(audit);
    await db.exec(`
      insert into auth.users values ('${a1}'), ('${a2}'), ('${t1}'), ('${t2}');
      insert into public.schools(id, name) values ('${s1}', 'School one'), ('${s2}', 'School two');
      insert into public.school_memberships(school_id, user_id, role) values
        ('${s1}','${a1}','school_admin'), ('${s2}','${a2}','school_admin'),
        ('${s1}','${t1}','teacher'), ('${s1}','${t2}','teacher');
      insert into public.classes(school_id,class_id,class_name,created_by)
        values ('${s1}','legacy','Legacy','${a1}');
    `);
    await db.exec(isolation);
    await db.exec(imports);
    await db.exec(structure);
    await db.exec(structure);

    async function identity(user) {
      await db.exec('reset role');
      await db.query("select set_config('request.jwt.claim.sub', $1, false)", [user]);
      await db.exec('set role authenticated');
    }

    await identity(a1);
    await db.exec(`
      insert into public.school_stages(school_id,stage_id,stage_name) values
        ('${s1}','${stage1}','Primary'), ('${s1}','${stage2}','Secondary');
      insert into public.school_grades(school_id,grade_id,stage_id,grade_name) values
        ('${s1}','${grade1}','${stage1}','Grade 1'), ('${s1}','${grade2}','${stage2}','Grade 1');
      insert into public.school_subjects(school_id,subject_id,subject_name) values
        ('${s1}','${math}','Math'), ('${s1}','${science}','Science');
      insert into public.classes(school_id,class_id,grade_id,class_name) values
        ('${s1}','class-a','${grade1}','A'), ('${s1}','class-b','${grade2}','A');
      insert into public.teacher_subject_assignments(school_id,class_id,subject_id,teacher_id) values
        ('${s1}','class-a','${math}','${t1}'),
        ('${s1}','class-b','${science}','${t1}'),
        ('${s1}','class-a','${science}','${t2}');
      insert into public.class_assignments(school_id,class_id,teacher_id) values
        ('${s1}','legacy','${t1}'), ('${s1}','class-a','${t1}');
      insert into public.students(school_id,student_code,class_id,display_name) values
        ('${s1}','legacy-student',null,'Synthetic unclassified');
    `);
    assert.equal((await db.query("select grade_id from public.classes where class_id='legacy'")).rows[0].grade_id, null);
    await assert.rejects(() => db.exec(`insert into public.teacher_subject_assignments
      (school_id,class_id,subject_id,teacher_id) values ('${s1}','legacy','${math}','${t1}')`),
      error => error.code === '23514');
    await db.exec(`update public.school_stages set stage_name='Primary reviewed'
      where school_id='${s1}' and stage_id='${stage1}'`);
    await db.exec(`update public.teacher_subject_assignments set subject_id='${science}'
      where school_id='${s1}' and class_id='class-a' and subject_id='${math}' and teacher_id='${t1}'`);
    await db.exec(`update public.teacher_subject_assignments set subject_id='${math}'
      where school_id='${s1}' and class_id='class-a' and subject_id='${science}' and teacher_id='${t1}'`);

    await identity(a2);
    await db.exec(`
      insert into public.school_stages(school_id,stage_id,stage_name) values ('${s2}','${stageOther}','Custom stage');
      insert into public.school_subjects(school_id,subject_id,subject_name) values ('${s2}','${otherSubject}','Other');
    `);
    assert.equal((await db.query(`select * from public.school_stages where school_id='${s1}'`)).rows.length, 0);

    await identity(t1);
    assert.equal((await db.query('select * from public.school_stages')).rows.length, 2);
    assert.equal((await db.query('select * from public.school_grades')).rows.length, 2);
    assert.equal((await db.query('select * from public.school_subjects')).rows.length, 2);
    const choices = (await db.query(`select * from public.list_my_teaching_assignments('${s1}')`)).rows;
    assert.deepEqual(choices.map(row => [row.stage_name, row.class_id, row.subject_name]), [
      ['Primary reviewed', 'class-a', 'Math'], ['Secondary', 'class-b', 'Science'],
    ]);
    assert.equal((await db.query(`select * from public.list_my_teaching_assignments('${s2}')`)).rows.length, 0);
    assert.deepEqual((await db.query('select class_id from public.classes order by class_id')).rows,
      [{ class_id: 'class-a' }, { class_id: 'class-b' }]);
    assert.equal((await db.query(`select public.has_teaching_assignment('${s1}','${stage1}','${grade1}','class-a','${science}') as allowed`)).rows[0].allowed, false);
    assert.equal((await db.query(`select public.has_teaching_assignment('${s1}','${stage1}','${grade1}','class-a','${math}') as allowed`)).rows[0].allowed, true);
    assert.equal((await db.query(`select public.has_teaching_assignment('${s2}',null,null,null,null) as allowed`)).rows[0].allowed, false);
    assert.equal((await db.query(`select public.can_access_class('${s1}','legacy') as allowed`)).rows[0].allowed, false);
    await assert.rejects(() => db.query(`select public.save_class_import('${s1}','legacy',
      '[{"Student code":"unauthorized"}]'::jsonb,null)`), error => error.code === '42501');
    await assert.rejects(() => db.query(`select public.save_class_import('${s1}','class-a',
      '[{"Student code":"legacy-student"}]'::jsonb,null)`), error => error.code === '42501');
    const saved = (await db.query(`select public.save_class_import('${s1}','class-a',
      '[{"Student code":"new-student","Student name":"Synthetic"}]'::jsonb,null) as id`)).rows[0].id;
    const imported = (await db.query(`select public.load_class_import('${s1}','class-a') as result`)).rows[0].result;
    assert.equal(imported.import_id, saved);
    assert.equal(imported.rows[0]['Student code'], 'new-student');
    await assert.rejects(() => db.exec(`insert into public.school_subjects(school_id,subject_name) values ('${s1}','Unauthorized')`),
      error => error.code === '42501');
    await assert.rejects(() => db.exec(`insert into public.teacher_subject_assignments
      (school_id,class_id,subject_id,teacher_id) values ('${s1}','class-a','${science}','${t1}')`),
      error => error.code === '42501');
    console.log('PASS multiple stages, grades, classes and subjects are scoped to teacher assignments');

    await identity(t2);
    assert.deepEqual((await db.query('select subject_id from public.school_subjects')).rows, [{ subject_id: science }]);
    assert.deepEqual((await db.query('select class_id from public.classes')).rows, [{ class_id: 'class-a' }]);
    await identity(a1);
    assert.equal((await db.query(`select class_id from public.students where student_code='legacy-student'`)).rows[0].class_id, null);
    assert.equal((await db.query(`select * from public.school_subjects where school_id='${s2}'`)).rows.length, 0);
    await db.exec(`delete from public.teacher_subject_assignments
      where school_id='${s1}' and class_id='class-a' and teacher_id='${t1}'`);
    await identity(t1);
    assert.equal((await db.query(`select * from public.classes where class_id='class-a'`)).rows.length, 0);
    await assert.rejects(() => db.query(`select public.load_class_import('${s1}','class-a')`),
      error => error.code === '42501');
    await assert.rejects(() => db.query(`select public.save_class_import('${s1}','class-a',
      '[{"Student code":"unauthorized"}]'::jsonb,null)`), error => error.code === '42501');
    await identity(a1);
    await db.exec(`update public.school_memberships set is_active=false where school_id='${s1}' and user_id='${t1}'`);
    await identity(t1);
    assert.equal((await db.query('select * from public.teacher_subject_assignments')).rows.length, 0);
    assert.equal((await db.query('select * from public.school_grades')).rows.length, 0);
    assert.equal((await db.query(`select * from public.list_my_teaching_assignments('${s1}')`)).rows.length, 0);
    console.log('PASS cross-school, other-teacher and inactive-member access denied');
    console.log('PASS legacy class retained without automatic classification');
  } finally {
    await db.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
