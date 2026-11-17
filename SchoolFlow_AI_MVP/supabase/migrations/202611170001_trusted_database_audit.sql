-- Install only after reviewing the target schema and backing up its data.
-- This migration does not change school or class authorization policies.
begin;

do $$
begin
    if exists (
        select 1 from pg_catalog.pg_proc p
        join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'append_audit_events'
          and p.oid <> coalesce(
              to_regprocedure('public.append_audit_events(uuid,jsonb)')::oid, 0::oid
          )
    ) then
        raise exception 'Unexpected append_audit_events overload requires manual review';
    end if;
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'audit_events'
          and column_name = 'database_generated'
    ) then
        if to_regprocedure('public.schoolflow_audit_mode()') is null then
            raise exception 'Existing audit provenance column requires manual review';
        end if;
    else
        alter table public.audit_events
            add column database_generated boolean not null default false;
    end if;
    if to_regprocedure('public.append_audit_events(uuid,jsonb)') is not null then
        execute 'revoke all on function public.append_audit_events(uuid,jsonb) from public, anon, authenticated';
    end if;
end;
$$;

drop policy if exists audit_events_member_insert on public.audit_events;
revoke insert, update, delete on public.audit_events from public, anon, authenticated;

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
            'for each row execute function public.audit_database_change()', table_name
        );
    end loop;
end;
$$;

create or replace function public.schoolflow_audit_mode()
returns text
language sql
stable
set search_path = pg_catalog, pg_temp
as $$ select 'database'::text $$;
revoke all on function public.schoolflow_audit_mode() from public, anon;
grant execute on function public.schoolflow_audit_mode() to authenticated;

notify pgrst, 'reload schema';
commit;
