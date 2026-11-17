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
const school = '00000000-0000-0000-0000-000000000001';
const admin = '10000000-0000-0000-0000-000000000001';
const teacher = '10000000-0000-0000-0000-000000000002';
const teacher2 = '10000000-0000-0000-0000-000000000003';

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
      insert into auth.users values ('${admin}'), ('${teacher}'), ('${teacher2}');
      insert into public.schools(id, name) values ('${school}', 'Synthetic school');
      insert into public.school_memberships(school_id, user_id, role) values
        ('${school}', '${admin}', 'school_admin'),
        ('${school}', '${teacher}', 'teacher'),
        ('${school}', '${teacher2}', 'teacher');
      insert into public.classes(school_id, class_id, class_name, created_by) values
        ('${school}', 'A', 'Class A', '${admin}'),
        ('${school}', 'B', 'Class B', '${admin}');
      insert into public.class_assignments(school_id, class_id, teacher_id, created_by) values
        ('${school}', 'A', '${teacher}', '${admin}'),
        ('${school}', 'B', '${teacher2}', '${admin}');
      insert into public.students(school_id, student_code, class_id, display_name, created_by) values
        ('${school}', 'A01', 'A', 'Synthetic A', '${admin}'),
        ('${school}', 'B01', 'B', 'Synthetic B', '${admin}'),
        ('${school}', 'legacy', null, 'Synthetic legacy', '${admin}');
    `);
    await db.exec(isolation);
    await db.exec(imports);

    async function identity(user) {
      await db.exec('reset role');
      await db.query("select set_config('request.jwt.claim.sub', $1, false)", [user]);
      await db.exec('set role authenticated');
    }
    async function save(classId, rows, expected = null) {
      const result = await db.query(
        'select public.save_class_import($1, $2, $3::jsonb, $4) as id',
        [school, classId, JSON.stringify(rows), expected],
      );
      return result.rows[0].id;
    }
    async function load(classId) {
      const result = await db.query('select public.load_class_import($1, $2) as data', [school, classId]);
      return result.rows[0].data;
    }
    const row = code => ({ 'Student code': code, 'Week': 1, 'Days scheduled': 5, 'Days attended': 4 });

    await identity(teacher);
    assert.deepEqual(await load('A'), { import_id: null, rows: [] });
    const first = await save('A', [row('A01'), { ...row('NEW'), 'Student name': 'Synthetic new' }]);
    assert.deepEqual((await load('A')).rows.map(item => item['Student code']), ['A01', 'NEW']);
    assert.deepEqual((await db.query("select student_code from public.students where student_code='NEW'")).rows, [{ student_code: 'NEW' }]);
    console.log('PASS assigned-class import creates new student and reloads ordered rows');

    for (const badCode of ['B01', 'legacy']) {
      await assert.rejects(() => save('A', [row('ROLLED-BACK'), row(badCode)], first), error => error.code === '42501');
      assert.equal((await db.query("select * from public.students where student_code='ROLLED-BACK'")).rows.length, 0);
      assert.equal((await load('A')).import_id, first);
    }
    await assert.rejects(() => save('A', [], first), error => error.code === '22023');
    await assert.rejects(() => save('B', [row('B01')]), error => error.code === '42501');
    await assert.rejects(() => load('B'), error => error.code === '42501');
    await assert.rejects(() => db.exec(`insert into public.class_import_rows
      (school_id,class_id,import_id,row_index,student_code,record_data)
      values ('${school}','A','${first}',2,'A01','{"Student code":"A01"}')`), error => error.code === '42501');
    console.log('PASS other-class, unclassified, unauthorized and direct writes are rejected atomically');

    await identity(teacher2);
    const secondClass = await save('B', [row('B01')]);
    assert.deepEqual((await load('B')).rows.map(item => item['Student code']), ['B01']);
    await assert.rejects(() => load('A'), error => error.code === '42501');
    await identity(teacher);
    const second = await save('A', [row('NEW')], first);
    await assert.rejects(() => save('A', [row('A01')], first), error => error.code === '40001');
    assert.equal((await load('A')).import_id, second);
    await identity(teacher2);
    assert.equal((await load('B')).import_id, secondClass);
    console.log('PASS class pointers are independent and stale updates cannot overwrite');

    await identity(admin);
    await db.exec(`update public.students set class_id='B' where school_id='${school}' and student_code='A01'`);
    await identity(teacher);
    const previousRows = await db.query(
      'select student_code from public.class_import_rows where school_id=$1 and class_id=$2 and import_id=$3',
      [school, 'A', first],
    );
    assert.deepEqual(previousRows.rows, [{ student_code: 'NEW' }]);
    await identity(admin);
    assert.equal((await db.query("select class_id from public.students where student_code='legacy'")).rows[0].class_id, null);
    assert.equal((await db.query('select * from public.class_import_rows where import_id=$1', [first])).rows.length, 2);
    console.log('PASS transferred-student rows are hidden from teacher and history remains for admin');
  } finally {
    await db.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
