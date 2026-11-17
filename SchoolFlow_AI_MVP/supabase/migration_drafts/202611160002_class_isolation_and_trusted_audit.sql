-- REVIEW DRAFT ONLY. Do not deploy: the current school-wide workspace and
-- client-submitted audit synchronization are not compatible with this policy.
-- In particular, teachers cannot access legacy educational payloads until the
-- application supports a trustworthy class-scoped workspace.
begin;

create or replace function public.can_access_class(
    target_school_id uuid,
    target_class_id text
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, pg_temp
as $$
    select exists (
        select 1
        from public.classes c
        join public.school_memberships m
          on m.school_id = c.school_id and m.user_id = auth.uid() and m.is_active
        where c.school_id = target_school_id
          and c.class_id = target_class_id
          and (
              m.role = 'school_admin'
              or (
                  m.role = 'teacher'
                  and exists (
                      select 1
                      from public.class_assignments a
                      where a.school_id = c.school_id
                        and a.class_id = c.class_id
                        and a.teacher_id = m.user_id
                  )
              )
          )
    );
$$;
revoke all on function public.can_access_class(uuid, text) from public, anon;
grant execute on function public.can_access_class(uuid, text) to authenticated;

drop policy if exists memberships_self_or_admin_read on public.school_memberships;
create policy memberships_self_or_admin_read on public.school_memberships
    for select to authenticated
    using (
        (user_id = auth.uid() and public.is_school_member(school_id))
        or public.has_school_role(school_id, 'school_admin')
    );

drop policy if exists class_assignments_self_or_admin_read on public.class_assignments;
create policy class_assignments_self_or_admin_read on public.class_assignments
    for select to authenticated
    using (
        (teacher_id = auth.uid() and public.has_school_role(school_id, 'teacher'))
        or public.has_school_role(school_id, 'school_admin')
    );

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'classes', 'students', 'import_batches', 'active_imports',
        'weekly_records', 'skills', 'lessons', 'lesson_attendance',
        'participation_records', 'assessments', 'interventions',
        'intervention_checkpoints', 'bloom_questions'
    ] loop
        execute format('drop policy if exists school_member_access on public.%I', table_name);
        execute format('drop policy if exists school_admin_access on public.%I', table_name);
        execute format(
            'create policy school_admin_access on public.%I for all to authenticated '
            'using (public.has_school_role(school_id, ''school_admin'')) '
            'with check (public.has_school_role(school_id, ''school_admin''))',
            table_name
        );
    end loop;
end;
$$;

drop policy if exists assigned_class_read on public.classes;
create policy assigned_class_read on public.classes
    for select to authenticated
    using (public.can_access_class(school_id, class_id));

drop policy if exists assigned_student_read on public.students;
create policy assigned_student_read on public.students
    for select to authenticated
    using (public.can_access_class(school_id, class_id));
drop policy if exists assigned_student_update on public.students;
create policy assigned_student_update on public.students
    for update to authenticated
    using (public.can_access_class(school_id, class_id))
    with check (public.can_access_class(school_id, class_id));

create or replace function public.protect_student_assignment()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
begin
    if not public.has_school_role(old.school_id, 'school_admin')
       and (new.school_id, new.student_code, new.class_id, new.created_by)
           is distinct from (old.school_id, old.student_code, old.class_id, old.created_by) then
        raise exception 'Only a school administrator may change student assignments or creator'
            using errcode = '42501';
    end if;
    return new;
end;
$$;
drop trigger if exists protect_student_assignment on public.students;
create trigger protect_student_assignment
before update on public.students
for each row execute function public.protect_student_assignment();

-- A draft can contain a full attendance list in JSON and is not class-scoped.
drop policy if exists lesson_drafts_owner_access on public.lesson_drafts;
drop policy if exists lesson_drafts_admin_access on public.lesson_drafts;
create policy lesson_drafts_admin_access on public.lesson_drafts
    for all to authenticated
    using (
        user_id = auth.uid()
        and public.has_school_role(school_id, 'school_admin')
    )
    with check (
        user_id = auth.uid()
        and public.has_school_role(school_id, 'school_admin')
    );

-- Only database triggers create trusted audit events; clients cannot submit them.
do $$
begin
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'audit_events'
          and column_name = 'database_generated'
    ) then
        if to_regprocedure('public.schoolflow_audit_mode()') is null then
            raise exception 'Existing audit provenance column requires manual review';
        end if;
    else
        alter table public.audit_events
            add column database_generated boolean not null default false;
    end if;
end;
$$;
drop policy if exists audit_events_member_insert on public.audit_events;
revoke insert, update, delete on public.audit_events from public, anon, authenticated;
revoke all on function public.append_audit_events(uuid, jsonb) from public, anon, authenticated;

create or replace function public.schoolflow_audit_mode()
returns text
language sql
stable
set search_path = pg_catalog, pg_temp
as $$ select 'database'::text $$;
revoke all on function public.schoolflow_audit_mode() from public, anon;
grant execute on function public.schoolflow_audit_mode() to authenticated;

create or replace function public.audit_database_change()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
    affected_school uuid;
    affected_row jsonb;
    affected_key jsonb;
begin
    if auth.uid() is null then
        return null;
    end if;
    if tg_op = 'DELETE' then
        affected_school := old.school_id;
        affected_row := to_jsonb(old);
    else
        affected_school := new.school_id;
        affected_row := to_jsonb(new);
    end if;
    select coalesce(jsonb_object_agg(key, value), '{}'::jsonb)
      into affected_key
      from jsonb_each(affected_row)
     where key = any (array[
         'class_id', 'student_code', 'teacher_id', 'user_id', 'stage_id',
         'grade_id', 'subject_id', 'import_id', 'row_index', 'record_id',
         'skill_id', 'lesson_id', 'question_id'
     ]) and value <> 'null'::jsonb;
    insert into public.audit_events (
        school_id, event_id, action, status, entity_type, occurred_at, record_data,
        database_generated
    ) values (
        affected_school, gen_random_uuid()::text, lower(tg_op), 'success',
        tg_table_name, clock_timestamp(),
        jsonb_build_object('source', 'database_trigger', 'entity_key', affected_key), true
    );
    return null;
end;
$$;
revoke all on function public.audit_database_change() from public, anon, authenticated;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'classes', 'class_assignments', 'students', 'import_batches',
        'active_imports', 'weekly_records', 'skills', 'lessons',
        'lesson_attendance', 'participation_records', 'assessments',
        'interventions', 'intervention_checkpoints', 'bloom_questions',
        'lesson_drafts'
    ] loop
        execute format('drop trigger if exists audit_database_change on public.%I', table_name);
        execute format(
            'create trigger audit_database_change after insert or update or delete on public.%I '
            'for each row execute function public.audit_database_change()',
            table_name
        );
    end loop;
end;
$$;

commit;
