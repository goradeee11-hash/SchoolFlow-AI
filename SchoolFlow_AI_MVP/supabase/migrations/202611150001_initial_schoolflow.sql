create extension if not exists pgcrypto;

create table if not exists public.schools (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.school_memberships (
    school_id uuid not null references public.schools(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('teacher', 'school_admin')),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    primary key (school_id, user_id)
);

create or replace function public.is_school_member(target_school_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1
        from public.school_memberships membership
        where membership.school_id = target_school_id
          and membership.user_id = auth.uid()
          and membership.is_active
    );
$$;

create or replace function public.has_school_role(
    target_school_id uuid,
    target_role text
)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1
        from public.school_memberships membership
        where membership.school_id = target_school_id
          and membership.user_id = auth.uid()
          and membership.is_active
          and membership.role = target_role
    );
$$;

create table if not exists public.classes (
    school_id uuid not null references public.schools(id) on delete cascade,
    class_id text not null,
    class_name text not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    created_at timestamptz not null default now(),
    primary key (school_id, class_id),
    unique (school_id, class_name)
);

create table if not exists public.class_assignments (
    school_id uuid not null,
    class_id text not null,
    teacher_id uuid not null references auth.users(id) on delete cascade,
    created_by uuid not null default auth.uid() references auth.users(id),
    created_at timestamptz not null default now(),
    primary key (school_id, class_id, teacher_id),
    foreign key (school_id, class_id)
        references public.classes(school_id, class_id) on delete cascade,
    foreign key (school_id, teacher_id)
        references public.school_memberships(school_id, user_id) on delete cascade
);

create table if not exists public.students (
    school_id uuid not null references public.schools(id) on delete cascade,
    student_code text not null,
    display_name text,
    class_id text,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, student_code),
    foreign key (school_id, class_id)
        references public.classes(school_id, class_id) on delete restrict
);

create table if not exists public.import_batches (
    school_id uuid not null references public.schools(id) on delete cascade,
    import_id text not null,
    uploaded_by uuid not null default auth.uid() references auth.users(id),
    record_count integer not null check (record_count >= 0),
    created_at timestamptz not null default now(),
    primary key (school_id, import_id)
);

create table if not exists public.active_imports (
    school_id uuid primary key references public.schools(id) on delete cascade,
    import_id text not null,
    updated_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    foreign key (school_id, import_id)
        references public.import_batches(school_id, import_id) on delete restrict
);

create table if not exists public.weekly_records (
    school_id uuid not null,
    record_id text not null,
    import_id text not null,
    student_code text,
    week_label text not null,
    row_index integer not null,
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, record_id),
    foreign key (school_id, import_id)
        references public.import_batches(school_id, import_id) on delete cascade,
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade
);
create index if not exists weekly_records_import_order
    on public.weekly_records (school_id, import_id, row_index);

create table if not exists public.skills (
    school_id uuid not null references public.schools(id) on delete cascade,
    skill_id text not null,
    name text not null,
    record_data jsonb not null,
    is_active boolean not null default true,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, skill_id)
);

create table if not exists public.lessons (
    school_id uuid not null references public.schools(id) on delete cascade,
    lesson_id text not null,
    class_id text,
    class_name text,
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, lesson_id),
    foreign key (school_id, class_id)
        references public.classes(school_id, class_id) on delete restrict
);

create table if not exists public.lesson_attendance (
    school_id uuid not null,
    lesson_id text not null,
    student_code text not null,
    attendance_status text not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    primary key (school_id, lesson_id, student_code),
    foreign key (school_id, lesson_id)
        references public.lessons(school_id, lesson_id) on delete cascade,
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade
);

create table if not exists public.participation_records (
    school_id uuid not null,
    record_id text not null,
    lesson_id text not null,
    student_code text not null,
    skill_id text,
    occurred_at timestamptz,
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    primary key (school_id, record_id),
    foreign key (school_id, lesson_id)
        references public.lessons(school_id, lesson_id) on delete cascade,
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade,
    foreign key (school_id, skill_id)
        references public.skills(school_id, skill_id) on delete restrict
);

create table if not exists public.assessments (
    school_id uuid not null,
    record_id text not null,
    student_code text not null,
    skill_id text not null,
    lesson_id text,
    assessment_date date,
    score double precision not null
        check (score >= 0 and score < 'Infinity'::double precision),
    max_score double precision not null
        check (
            max_score > 0
            and max_score < 'Infinity'::double precision
            and score <= max_score
        ),
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    primary key (school_id, record_id),
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade,
    foreign key (school_id, skill_id)
        references public.skills(school_id, skill_id) on delete restrict,
    foreign key (school_id, lesson_id)
        references public.lessons(school_id, lesson_id) on delete restrict
);

create table if not exists public.interventions (
    school_id uuid not null,
    record_id text not null,
    student_code text not null,
    skill_id text not null,
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, record_id),
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade,
    foreign key (school_id, skill_id)
        references public.skills(school_id, skill_id) on delete restrict
);

create table if not exists public.intervention_checkpoints (
    school_id uuid not null,
    record_id text not null,
    intervention_id text not null,
    student_code text not null,
    skill_id text not null,
    checkpoint_date date,
    score double precision not null
        check (score >= 0 and score < 'Infinity'::double precision),
    max_score double precision not null
        check (
            max_score > 0
            and max_score < 'Infinity'::double precision
            and score <= max_score
        ),
    record_data jsonb not null,
    created_by uuid not null default auth.uid() references auth.users(id),
    primary key (school_id, record_id),
    foreign key (school_id, intervention_id)
        references public.interventions(school_id, record_id) on delete cascade,
    foreign key (school_id, student_code)
        references public.students(school_id, student_code) on delete cascade,
    foreign key (school_id, skill_id)
        references public.skills(school_id, skill_id) on delete restrict
);

create table if not exists public.bloom_questions (
    school_id uuid not null,
    record_id text not null,
    lesson_id text,
    skill_id text,
    record_data jsonb not null,
    is_deleted boolean not null default false,
    created_by uuid not null default auth.uid() references auth.users(id),
    updated_at timestamptz not null default now(),
    primary key (school_id, record_id),
    foreign key (school_id, lesson_id)
        references public.lessons(school_id, lesson_id) on delete restrict,
    foreign key (school_id, skill_id)
        references public.skills(school_id, skill_id) on delete restrict
);

create table if not exists public.lesson_drafts (
    school_id uuid not null references public.schools(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    lesson_id text,
    record_data jsonb not null,
    updated_at timestamptz not null default now(),
    primary key (school_id, user_id),
    foreign key (school_id, lesson_id)
        references public.lessons(school_id, lesson_id) on delete restrict
);

create table if not exists public.audit_events (
    school_id uuid not null references public.schools(id) on delete cascade,
    event_id text not null,
    actor_user_id uuid not null default auth.uid() references auth.users(id),
    actor_role text not null default 'teacher'
        check (actor_role in ('teacher', 'school_admin')),
    action text not null,
    status text not null,
    entity_type text not null,
    occurred_at timestamptz not null,
    record_data jsonb not null,
    primary key (school_id, event_id)
);
create index if not exists audit_events_school_time
    on public.audit_events (school_id, occurred_at desc);

create or replace function public.set_audit_actor()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    membership_role text;
begin
    select membership.role
      into membership_role
      from public.school_memberships membership
     where membership.school_id = new.school_id
       and membership.user_id = auth.uid()
       and membership.is_active;

    if membership_role is null then
        raise exception 'Active school membership required to create audit events';
    end if;

    new.actor_user_id := auth.uid();
    new.actor_role := membership_role;
    return new;
end;
$$;

drop trigger if exists audit_events_set_actor on public.audit_events;
create trigger audit_events_set_actor
before insert on public.audit_events
for each row execute function public.set_audit_actor();

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'students', 'weekly_records', 'skills', 'lessons',
        'interventions', 'bloom_questions', 'lesson_drafts', 'active_imports'
    ] loop
        execute format('drop trigger if exists touch_updated_at on public.%I', table_name);
        execute format(
            'create trigger touch_updated_at before update on public.%I '
            'for each row execute function public.touch_updated_at()',
            table_name
        );
    end loop;
end;
$$;

alter table public.schools enable row level security;
alter table public.school_memberships enable row level security;
alter table public.classes enable row level security;
alter table public.class_assignments enable row level security;
alter table public.students enable row level security;
alter table public.import_batches enable row level security;
alter table public.active_imports enable row level security;
alter table public.weekly_records enable row level security;
alter table public.skills enable row level security;
alter table public.lessons enable row level security;
alter table public.lesson_attendance enable row level security;
alter table public.participation_records enable row level security;
alter table public.assessments enable row level security;
alter table public.interventions enable row level security;
alter table public.intervention_checkpoints enable row level security;
alter table public.bloom_questions enable row level security;
alter table public.lesson_drafts enable row level security;
alter table public.audit_events enable row level security;

drop policy if exists schools_member_read on public.schools;
create policy schools_member_read on public.schools
    for select to authenticated using (public.is_school_member(id));
drop policy if exists schools_admin_update on public.schools;
create policy schools_admin_update on public.schools
    for update to authenticated
    using (public.has_school_role(id, 'school_admin'))
    with check (public.has_school_role(id, 'school_admin'));

drop policy if exists memberships_self_or_admin_read on public.school_memberships;
create policy memberships_self_or_admin_read on public.school_memberships
    for select to authenticated
    using (
        user_id = auth.uid()
        or public.has_school_role(school_id, 'school_admin')
    );
drop policy if exists memberships_admin_manage on public.school_memberships;
create policy memberships_admin_manage on public.school_memberships
    for all to authenticated
    using (public.has_school_role(school_id, 'school_admin'))
    with check (public.has_school_role(school_id, 'school_admin'));

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'classes', 'students', 'import_batches', 'active_imports',
        'weekly_records', 'skills', 'lessons',
        'lesson_attendance', 'participation_records', 'assessments',
        'interventions', 'intervention_checkpoints', 'bloom_questions'
    ] loop
        execute format('drop policy if exists school_member_access on public.%I', table_name);
        execute format(
            'create policy school_member_access on public.%I for all to authenticated '
            'using (public.is_school_member(school_id)) '
            'with check (public.is_school_member(school_id))',
            table_name
        );
    end loop;
end;
$$;

drop policy if exists lesson_drafts_owner_access on public.lesson_drafts;
create policy lesson_drafts_owner_access on public.lesson_drafts
    for all to authenticated
    using (user_id = auth.uid() and public.is_school_member(school_id))
    with check (user_id = auth.uid() and public.is_school_member(school_id));

drop policy if exists audit_events_admin_read on public.audit_events;
create policy audit_events_admin_read on public.audit_events
    for select to authenticated
    using (public.has_school_role(school_id, 'school_admin'));
drop policy if exists audit_events_member_insert on public.audit_events;
create policy audit_events_member_insert on public.audit_events
    for insert to authenticated
    with check (
        actor_user_id = auth.uid()
        and public.is_school_member(school_id)
    );

drop policy if exists class_assignments_self_or_admin_read on public.class_assignments;
create policy class_assignments_self_or_admin_read on public.class_assignments
    for select to authenticated
    using (
        teacher_id = auth.uid()
        or public.has_school_role(school_id, 'school_admin')
    );
drop policy if exists class_assignments_admin_manage on public.class_assignments;
create policy class_assignments_admin_manage on public.class_assignments
    for all to authenticated
    using (public.has_school_role(school_id, 'school_admin'))
    with check (public.has_school_role(school_id, 'school_admin'));

grant usage on schema public to authenticated;
grant select, update on public.schools to authenticated;
grant select, insert, update, delete on public.school_memberships to authenticated;
grant select, insert, update, delete on public.classes to authenticated;
grant select, insert, update, delete on public.class_assignments to authenticated;
grant select, insert, update, delete on public.students to authenticated;
grant select, insert, update, delete on public.import_batches to authenticated;
grant select, insert, update, delete on public.active_imports to authenticated;
grant select, insert, update, delete on public.weekly_records to authenticated;
grant select, insert, update, delete on public.skills to authenticated;
grant select, insert, update, delete on public.lessons to authenticated;
grant select, insert, update, delete on public.lesson_attendance to authenticated;
grant select, insert, update, delete on public.participation_records to authenticated;
grant select, insert, update, delete on public.assessments to authenticated;
grant select, insert, update, delete on public.interventions to authenticated;
grant select, insert, update, delete on public.intervention_checkpoints to authenticated;
grant select, insert, update, delete on public.bloom_questions to authenticated;
grant select, insert, update, delete on public.lesson_drafts to authenticated;
grant select, insert on public.audit_events to authenticated;
revoke all on function public.is_school_member(uuid) from public, anon;
revoke all on function public.has_school_role(uuid, text) from public, anon;
grant execute on function public.is_school_member(uuid) to authenticated;
grant execute on function public.has_school_role(uuid, text) to authenticated;
