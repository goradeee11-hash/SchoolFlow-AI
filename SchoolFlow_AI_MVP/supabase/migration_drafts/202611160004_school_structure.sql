-- REVIEW DRAFT ONLY. Requires the class-isolation draft. The application and
-- educational records are not yet integrated with subject-level authorization.
begin;

create table if not exists public.school_stages (
    school_id uuid not null references public.schools(id) on delete restrict,
    stage_id uuid not null default gen_random_uuid(),
    stage_name text not null check (length(btrim(stage_name)) > 0),
    primary key (school_id, stage_id),
    unique (school_id, stage_name)
);

create table if not exists public.school_grades (
    school_id uuid not null,
    grade_id uuid not null default gen_random_uuid(),
    stage_id uuid not null,
    grade_name text not null check (length(btrim(grade_name)) > 0),
    primary key (school_id, grade_id),
    unique (school_id, stage_id, grade_name),
    foreign key (school_id, stage_id)
        references public.school_stages(school_id, stage_id) on delete restrict
);

create table if not exists public.school_subjects (
    school_id uuid not null references public.schools(id) on delete restrict,
    subject_id uuid not null default gen_random_uuid(),
    subject_name text not null check (length(btrim(subject_name)) > 0),
    primary key (school_id, subject_id),
    unique (school_id, subject_name)
);

-- Existing classes remain unclassified until a school administrator reviews them.
alter table public.classes add column if not exists grade_id uuid;
alter table public.classes drop constraint if exists classes_school_id_grade_id_fkey;
alter table public.classes add constraint classes_school_id_grade_id_fkey
    foreign key (school_id, grade_id)
    references public.school_grades(school_id, grade_id) on delete restrict;
alter table public.classes drop constraint if exists classes_school_id_class_name_key;
create unique index if not exists classes_class_name_per_grade
    on public.classes(school_id, grade_id, class_name) where grade_id is not null;
create unique index if not exists classes_unclassified_name
    on public.classes(school_id, class_name) where grade_id is null;

create table if not exists public.teacher_subject_assignments (
    school_id uuid not null,
    class_id text not null,
    subject_id uuid not null,
    teacher_id uuid not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    created_at timestamptz not null default now(),
    primary key (school_id, class_id, subject_id, teacher_id),
    foreign key (school_id, class_id)
        references public.classes(school_id, class_id) on delete restrict,
    foreign key (school_id, subject_id)
        references public.school_subjects(school_id, subject_id) on delete restrict,
    foreign key (school_id, teacher_id)
        references public.school_memberships(school_id, user_id) on delete restrict
);

create or replace function public.validate_teacher_subject_assignment()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
begin
    if not exists (
        select 1 from public.school_memberships m
         where m.school_id = new.school_id and m.user_id = new.teacher_id
           and m.role = 'teacher' and m.is_active
    ) then
        raise exception 'An active teacher in the same school is required'
            using errcode = '23514';
    end if;
    if not exists (
        select 1 from public.classes c
         where c.school_id = new.school_id and c.class_id = new.class_id
           and c.grade_id is not null
    ) then
        raise exception 'Class must have a reviewed grade before assignment'
            using errcode = '23514';
    end if;
    if tg_op = 'INSERT' then
        new.created_by := auth.uid();
    else
        new.created_by := old.created_by;
    end if;
    return new;
end;
$$;
revoke all on function public.validate_teacher_subject_assignment()
    from public, anon, authenticated;
drop trigger if exists validate_teacher_subject_assignment on public.teacher_subject_assignments;
create trigger validate_teacher_subject_assignment
before insert or update on public.teacher_subject_assignments
for each row execute function public.validate_teacher_subject_assignment();

create or replace function public.has_teaching_assignment(
    target_school_id uuid,
    target_stage_id uuid,
    target_grade_id uuid,
    target_class_id text,
    target_subject_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, pg_temp
as $$
    select exists (
        select 1
          from public.teacher_subject_assignments a
          join public.school_memberships m
            on m.school_id = a.school_id and m.user_id = a.teacher_id
           and m.role = 'teacher' and m.is_active
          join public.classes c
            on c.school_id = a.school_id and c.class_id = a.class_id
          join public.school_grades g
            on g.school_id = c.school_id and g.grade_id = c.grade_id
         where a.school_id = target_school_id
           and a.teacher_id = auth.uid()
           and (target_stage_id is null or g.stage_id = target_stage_id)
           and (target_grade_id is null or g.grade_id = target_grade_id)
           and (target_class_id is null or a.class_id = target_class_id)
           and (target_subject_id is null or a.subject_id = target_subject_id)
    );
$$;
revoke all on function public.has_teaching_assignment(uuid, uuid, uuid, text, uuid)
    from public, anon;
grant execute on function public.has_teaching_assignment(uuid, uuid, uuid, text, uuid)
    to authenticated;

-- Once this draft is installed, legacy class-only assignments no longer grant
-- class access. Keep their rows for administrator review, without guessing a subject.
create or replace function public.can_access_class(
    target_school_id uuid, target_class_id text
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, pg_temp
as $$
    select target_class_id is not null and exists (
        select 1 from public.classes c
         where c.school_id = target_school_id and c.class_id = target_class_id
           and (
               public.has_school_role(c.school_id, 'school_admin')
               or public.has_teaching_assignment(c.school_id, null, null, c.class_id, null)
           )
    );
$$;

-- The import save RPC takes a row lock so assignment removal cannot race a save.
-- Draft 003 must be installed before draft 004.
create or replace function public.lock_teacher_class_import_access(
    p_school_id uuid, p_class_id text, p_teacher_id uuid
)
returns boolean
language plpgsql
set search_path = pg_catalog, pg_temp
as $$
begin
    perform 1 from public.teacher_subject_assignments a
     where a.school_id = p_school_id and a.class_id = p_class_id
       and a.teacher_id = p_teacher_id for share;
    return found;
end;
$$;
revoke all on function public.lock_teacher_class_import_access(uuid, text, uuid)
    from public, anon, authenticated;

alter table public.school_stages enable row level security;
alter table public.school_grades enable row level security;
alter table public.school_subjects enable row level security;
alter table public.teacher_subject_assignments enable row level security;

do $$
declare table_name text;
begin
    foreach table_name in array array[
        'school_stages', 'school_grades', 'school_subjects', 'teacher_subject_assignments'
    ] loop
        execute format('drop policy if exists school_admin_manage on public.%I', table_name);
        execute format(
            'create policy school_admin_manage on public.%I for all to authenticated '
            'using (public.has_school_role(school_id, ''school_admin'')) '
            'with check (public.has_school_role(school_id, ''school_admin''))',
            table_name
        );
        execute format('drop trigger if exists audit_database_change on public.%I', table_name);
        execute format(
            'create trigger audit_database_change after insert or update or delete on public.%I '
            'for each row execute function public.audit_database_change()',
            table_name
        );
    end loop;
end;
$$;

drop policy if exists assigned_stage_read on public.school_stages;
create policy assigned_stage_read on public.school_stages for select to authenticated
    using (public.has_teaching_assignment(school_id, stage_id, null, null, null));
drop policy if exists assigned_grade_read on public.school_grades;
create policy assigned_grade_read on public.school_grades for select to authenticated
    using (public.has_teaching_assignment(school_id, null, grade_id, null, null));
drop policy if exists assigned_subject_read on public.school_subjects;
create policy assigned_subject_read on public.school_subjects for select to authenticated
    using (public.has_teaching_assignment(school_id, null, null, null, subject_id));
drop policy if exists teaching_assignment_self_read on public.teacher_subject_assignments;
create policy teaching_assignment_self_read on public.teacher_subject_assignments for select to authenticated
    using (teacher_id = auth.uid() and public.has_school_role(school_id, 'teacher'));
drop policy if exists subject_assigned_class_read on public.classes;

revoke all on public.school_stages, public.school_grades,
    public.school_subjects, public.teacher_subject_assignments from public, anon, authenticated;
grant select, insert, update, delete on public.school_stages, public.school_grades,
    public.school_subjects, public.teacher_subject_assignments to authenticated;

create or replace function public.list_my_teaching_assignments(p_school_id uuid)
returns table (
    stage_id uuid, stage_name text, grade_id uuid, grade_name text,
    class_id text, class_name text, subject_id uuid, subject_name text
)
language sql
stable
security invoker
set search_path = pg_catalog, pg_temp
as $$
    select st.stage_id, st.stage_name, g.grade_id, g.grade_name,
           c.class_id, c.class_name, su.subject_id, su.subject_name
      from public.teacher_subject_assignments a
      join public.classes c on c.school_id = a.school_id and c.class_id = a.class_id
      join public.school_grades g on g.school_id = c.school_id and g.grade_id = c.grade_id
      join public.school_stages st on st.school_id = g.school_id and st.stage_id = g.stage_id
      join public.school_subjects su on su.school_id = a.school_id and su.subject_id = a.subject_id
     where a.school_id = p_school_id and a.teacher_id = auth.uid()
     order by st.stage_name, g.grade_name, c.class_name, su.subject_name;
$$;
revoke all on function public.list_my_teaching_assignments(uuid) from public, anon;
grant execute on function public.list_my_teaching_assignments(uuid) to authenticated;

commit;
