-- REVIEW DRAFT ONLY. Requires the preceding class isolation draft.
-- The current application is not yet integrated with this import path.
begin;

create table if not exists public.class_import_batches (
    school_id uuid not null,
    class_id text not null,
    import_id uuid not null default gen_random_uuid(),
    uploaded_by uuid not null references auth.users(id),
    created_at timestamptz not null default now(),
    record_count integer not null check (record_count >= 0),
    primary key (school_id, class_id, import_id),
    foreign key (school_id, class_id)
        references public.classes(school_id, class_id) on delete restrict
);

create table if not exists public.class_import_rows (
    school_id uuid not null,
    class_id text not null,
    import_id uuid not null,
    row_index integer not null check (row_index >= 0),
    student_code text not null,
    record_data jsonb not null
        check (jsonb_typeof(record_data) = 'object'
               and jsonb_typeof(record_data -> 'Student code') = 'string'
               and (record_data ->> 'Student code') is not distinct from student_code),
    primary key (school_id, class_id, import_id, row_index),
    foreign key (school_id, class_id, import_id)
        references public.class_import_batches(school_id, class_id, import_id)
        on delete restrict,
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete restrict
);

create table if not exists public.class_active_imports (
    school_id uuid not null,
    class_id text not null,
    import_id uuid not null,
    updated_by uuid not null references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, class_id),
    foreign key (school_id, class_id, import_id)
        references public.class_import_batches(school_id, class_id, import_id)
        on delete restrict
);

alter table public.class_import_batches enable row level security;
alter table public.class_import_rows enable row level security;
alter table public.class_active_imports enable row level security;

drop policy if exists class_import_batches_read on public.class_import_batches;
create policy class_import_batches_read on public.class_import_batches
    for select to authenticated using (public.can_access_class(school_id, class_id));
drop policy if exists class_import_rows_read on public.class_import_rows;
create policy class_import_rows_read on public.class_import_rows
    for select to authenticated using (
        public.has_school_role(school_id, 'school_admin')
        or (
            public.can_access_class(school_id, class_id)
            and exists (
                select 1 from public.students s
                where s.school_id = class_import_rows.school_id
                  and s.class_id = class_import_rows.class_id
                  and s.student_code = class_import_rows.student_code
            )
        )
    );
drop policy if exists class_active_imports_read on public.class_active_imports;
create policy class_active_imports_read on public.class_active_imports
    for select to authenticated using (public.can_access_class(school_id, class_id));

revoke all on public.class_import_batches, public.class_import_rows,
    public.class_active_imports from public, anon, authenticated;
grant select on public.class_import_batches, public.class_import_rows,
    public.class_active_imports to authenticated;

create or replace function public.load_class_import(
    p_school_id uuid,
    p_class_id text
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, pg_temp
as $$
declare
    active_id uuid;
    rows_json jsonb;
begin
    if not public.can_access_class(p_school_id, p_class_id) then
        raise exception 'Class not available' using errcode = '42501';
    end if;
    select a.import_id into active_id from public.class_active_imports a
     where a.school_id = p_school_id and a.class_id = p_class_id;
    select coalesce(jsonb_agg(r.record_data order by r.row_index), '[]'::jsonb)
      into rows_json
      from public.class_import_rows r
     where r.school_id = p_school_id and r.class_id = p_class_id
       and r.import_id = active_id;
    return jsonb_build_object('import_id', active_id, 'rows', rows_json);
end;
$$;
revoke all on function public.load_class_import(uuid, text) from public, anon;
grant execute on function public.load_class_import(uuid, text) to authenticated;

create or replace function public.lock_teacher_class_import_access(
    p_school_id uuid, p_class_id text, p_teacher_id uuid
)
returns boolean
language plpgsql
set search_path = pg_catalog, pg_temp
as $$
begin
    perform 1 from public.class_assignments a
     where a.school_id = p_school_id and a.class_id = p_class_id
       and a.teacher_id = p_teacher_id for share;
    return found;
end;
$$;
revoke all on function public.lock_teacher_class_import_access(uuid, text, uuid)
    from public, anon, authenticated;

create or replace function public.save_class_import(
    p_school_id uuid,
    p_class_id text,
    p_rows jsonb,
    p_expected_import_id uuid
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
    actor_role text;
    active_id uuid;
    new_id uuid;
begin
    select m.role into actor_role
      from public.school_memberships m
     where m.school_id = p_school_id and m.user_id = auth.uid() and m.is_active
     for share;
    if actor_role is null then
        raise exception 'Active school membership required' using errcode = '42501';
    end if;
    perform 1 from public.classes c
     where c.school_id = p_school_id and c.class_id = p_class_id for share;
    if not found then
        raise exception 'Class not available' using errcode = '42501';
    end if;
    if actor_role = 'teacher' then
        if not public.lock_teacher_class_import_access(p_school_id, p_class_id, auth.uid()) then
            raise exception 'Class not available' using errcode = '42501';
        end if;
    elsif actor_role <> 'school_admin' then
        raise exception 'Unsupported role' using errcode = '42501';
    end if;
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'Rows must be a JSON array' using errcode = '22023';
    end if;
    if jsonb_array_length(p_rows) = 0 then
        raise exception 'At least one student row is required' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_rows) r
        where jsonb_typeof(r) <> 'object'
           or jsonb_typeof(r -> 'Student code') is distinct from 'string'
           or nullif(btrim(r ->> 'Student code'), '') is null
           or r ->> 'Student code' <> btrim(r ->> 'Student code')
    ) then
        raise exception 'Every row requires a nonempty normalized student code'
            using errcode = '22023';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_school_id::text || ':' || p_class_id, 0));
    select a.import_id into active_id from public.class_active_imports a
     where a.school_id = p_school_id and a.class_id = p_class_id;
    if active_id is distinct from p_expected_import_id then
        raise exception 'Active class import changed; reload before saving'
            using errcode = '40001';
    end if;

    insert into public.students (school_id, student_code, class_id, display_name, created_by)
    select p_school_id, first_row.code, p_class_id, first_row.name, auth.uid()
    from (
        select distinct on (r.value ->> 'Student code')
            r.value ->> 'Student code' as code,
            nullif(btrim(r.value ->> 'Student name'), '') as name
        from jsonb_array_elements(p_rows) with ordinality as r(value, position)
        order by r.value ->> 'Student code', r.position
    ) first_row
    on conflict (school_id, student_code) do nothing;

    perform 1 from public.students s
     where s.school_id = p_school_id
       and s.student_code in (
           select r ->> 'Student code' from jsonb_array_elements(p_rows) r
       )
     for share;
    if exists (
        select 1 from jsonb_array_elements(p_rows) r
        where not exists (
            select 1 from public.students s
             where s.school_id = p_school_id
               and s.student_code = r ->> 'Student code'
               and s.class_id = p_class_id
        )
    ) then
        raise exception 'One or more student codes require administrator review'
            using errcode = '42501';
    end if;

    insert into public.class_import_batches
        (school_id, class_id, uploaded_by, record_count)
    values (p_school_id, p_class_id, auth.uid(), jsonb_array_length(p_rows))
    returning import_id into new_id;
    insert into public.class_import_rows
        (school_id, class_id, import_id, row_index, student_code, record_data)
    select p_school_id, p_class_id, new_id, (r.position - 1)::integer,
           r.value ->> 'Student code', r.value
      from jsonb_array_elements(p_rows) with ordinality as r(value, position);
    insert into public.class_active_imports
        (school_id, class_id, import_id, updated_by)
    values (p_school_id, p_class_id, new_id, auth.uid())
    on conflict (school_id, class_id)
    do update set import_id = excluded.import_id, updated_by = excluded.updated_by,
                  updated_at = clock_timestamp();
    return new_id;
end;
$$;
revoke all on function public.save_class_import(uuid, text, jsonb, uuid)
    from public, anon;
grant execute on function public.save_class_import(uuid, text, jsonb, uuid)
    to authenticated;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'class_import_batches', 'class_import_rows', 'class_active_imports'
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
