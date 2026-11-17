# Supabase setup

The app remains in local, session-only mode until both `SUPABASE_URL` and
`SUPABASE_ANON_KEY` are configured. Cloud mode uses Supabase Auth and the
public anon/publishable key; it never accepts a service-role key.
Local session data is not durable by default. Windows users may explicitly
save a synthetic-only demo snapshot protected by Windows DPAPI for the current
Windows account; saved snapshots are restored in local mode. Changes since the
last explicit save may be lost on reload or close. The snapshot excludes chat,
audit events and credentials, is shared by sessions using the same Windows
account, and is not teacher authentication or class isolation. Concurrent
changes are rejected instead of overwritten. In cloud mode, a failed save leaves changes in the current session;
sign-out retries the save and remains blocked if that retry fails. Reloading or
closing the page can still lose those unsaved changes.

## Initial project setup

1. Create a Supabase project and enable email/password sign-in in **Authentication
   → Providers**.
2. After explicit approval, review and run the migrations in order in the
   Supabase SQL Editor: `migrations/202611150001_initial_schoolflow.sql`,
   `migrations/202611160001_append_audit_events.sql`, then
   `migrations/202611170001_trusted_database_audit.sql`. The last migration
   must run after the legacy audit migration and before using cloud mode.
   Never rerun the legacy migration afterward: it grants access to the
   untrusted client-event function.
3. Create user accounts in **Authentication → Users**.
4. Bootstrap a school and its first administrator in the SQL Editor. Replace
   the example values with the school name and the Auth user's UUID:

   ```sql
   insert into public.schools (name)
   values ('School name')
   returning id;

   insert into public.school_memberships (school_id, user_id, role)
   values ('<school-uuid>', '<auth-user-uuid>', 'school_admin');
   ```

   Add teacher accounts with role `teacher`. School membership changes are
   restricted to school administrators in the app-facing RLS policies.
5. Copy `.streamlit/secrets.toml.template` to `.streamlit/secrets.toml` and set
   the Supabase project URL and public anon/publishable key under `[supabase]`.
   Alternatively, set `SUPABASE_URL` and `SUPABASE_ANON_KEY` environment
   variables. Never put a service-role key in the app or its secrets.
6. Install the project requirements and start Streamlit. The sign-in screen
   appears only when both settings are present.

Do not upload real student data until the school's privacy, retention, access,
and data-processing requirements have been approved. The current policies do
not isolate teachers by class; do not use real student data.

## Data and access model

Every educational record is scoped by `school_id`; composite keys and foreign
keys keep student, lesson, skill, assessment, participation, intervention, and
question records within that school. Imported workbooks are stored as import
batches, with one active-batch pointer so a new import replaces the displayed
dataset without rewriting prior rows. The legacy app workspace is currently restricted to school administrators;
teachers are blocked until assignment-scoped loading and saving are complete.
This application-level block does not change the broad existing database RLS:
teachers can still access school-wide data directly through the database API,
so no real data should be used. Only school administrators can read audit events
and manage memberships. The trusted audit migration records supported database
changes in the same transaction, using the authenticated database identity.
It revokes client writes and execution of the old `append_audit_events` RPC.
Earlier client-submitted events remain unverified; they are not deleted.

If PostgREST reports `PGRST202` for `append_audit_events`, it may be absent,
have a different signature or permissions, or the schema cache may be stale.
The checked-in old signature is `(p_school_id uuid, p_events jsonb)`, matching
the former Python named arguments. The new app does not call it: cloud mode
requires `schoolflow_audit_mode()` and stops with an explicit error if it is
unavailable. The trusted migration includes a PostgREST schema reload
notification. Before applying it to an existing installation, inspect the
target's audit columns, policies, triggers and any overloads or grants of the
legacy function; resolve unexpected differences manually and back up data.
It can run against the initial schema even if the old RPC was never installed.
Do not apply it remotely without approval and isolated testing.

The administrator UI supports class and student assignments, but the supplied
active migrations enforce school-level membership only, not class isolation.
It lists students without a class for administrator review; it does not infer
their class or classify other legacy records automatically. A session is
blocked if its cloud role changes while its workspace is cached; a new session
is needed and unsaved session changes may be lost.

The database stores normalized relationship keys alongside JSONB copies of
existing record fields so the current app's evolving record shapes are
preserved. Session state remains the UI cache. The legacy administrator
backend loads a school's records at sign-in and synchronizes them after app actions.

## Local security draft — not deployable yet

`migration_drafts/202611160002_class_isolation_and_trusted_audit.sql` is kept
outside the automatic migrations directory intentionally. It restricts class
and student access, retains unclassified records without assigning them, denies
teachers access to other school-wide educational payloads, and records database
changes through server-generated audit events instead of trusting client events.
It has been exercised against an isolated PGlite database, not Supabase.

**Do not apply this draft to an existing project.** The current backend loads
and syncs a school-wide workspace and shares one active import per school. The
draft would prevent teachers from using those educational functions.
Class-scoped imports and workspace synchronization and legacy-data
classification are required before deployment.

`migration_drafts/202611160003_class_imports.sql` is a separate, local-only
draft that depends on the isolation draft. It adds per-class import history
and active pointers without modifying existing school-wide imports. Its atomic
save operation checks current membership and class assignment in the database.
Teachers may create genuinely new student codes in their assigned class;
existing students in a different class or without a class require an
administrator's review. Existing students are never reassigned by import.
Each save requires the previously loaded active import ID, rejecting stale
writes instead of overwriting another user's import. Rows belonging to a
student later moved to another class are hidden from the original teacher.

The Python class-import helpers and SQL draft are not connected to the app's
upload, workspace loading, or synchronization yet. Do not apply either draft
until the selected-class workflow, all educational records and cache
invalidation are integrated and verified together.

`migration_drafts/202611160004_school_structure.sql` is another local-only
review draft, dependent on the isolation and class-import drafts (apply the
drafts in numerical order only to an isolated local test database). It models stages, grades and
subjects per school, attaches an optional grade to a class, and assigns each
teacher to class/subject pairs. An administrator can manage these records
through the app's administrator structure page when the draft schema is
present; a teacher can list their own active
assignments with `list_my_teaching_assignments`. A class may have the same
name as another class in a different grade. Existing classes remain
unclassified until reviewed and explicitly classified by their administrator.
Class renaming is disabled in this page because the legacy workspace still
derives class identifiers from names.

**This is not a deployable integration or a working assignment selector.**
The existing application still loads and synchronizes a school-wide workspace.
When draft 004 follows 002 and 003, class authorization and the class-import
save operation use the new class/subject assignments rather than old
`class_assignments`. Old assignment rows remain for review and are not mapped
to subjects automatically. Class imports still operate at class level, not
subject level, and the new structure does not restrict other educational
records by subject. The Python assignment-loading helper is not connected to
the UI.

Before any deployment, reconcile old and new assignments and all class
policies, and connect student records, imports, educational data, exports,
analytics and audit to a verified authorization context. Complete the
stage/grade/class/subject selector, including safe switching
and revalidation of cached or unsaved data when assignments change. Update
class creation and synchronization to support duplicate class names across
grades without changing existing class identifiers. Preserve unclassified
legacy records for administrator review; do not infer their grade or subject.
Decide explicitly which student and attendance data may be shared among
subject teachers and how subject-specific free-text records are protected.
Test the complete integration locally and on an isolated Supabase test project
before any approved remote migration.

The app requires database audit mode and never submits client-generated
events. The administrator audit page displays
database-generated events separately, retaining the database actor ID and
marking older events as unverified. Session-only actions, such as report
downloads, are not persisted by the database triggers. The trusted migration
adds `database_generated` to distinguish new
events; before any eventual deployment, inspect the target schema to ensure
that this column was not previously introduced or populated by other code.
The draft logs successful changes to the listed educational tables, with a limited
database-derived record key for new events, not reads,
failed attempts, membership changes, or privileged operations without an
authenticated user. Administrators can access unclassified students and
school-wide educational tables, but not another user's legacy lesson draft
through RLS. Existing client-submitted audit history remains unverified.

The focused local test is `test_class_isolation.cjs`; it needs an existing
`@electric-sql/pglite` installation accessible through Node's module path.
It simulates `auth.uid()` and is not a substitute for testing the complete
integration and RLS on an isolated Supabase project.
`test_class_import.cjs` exercises the separate import draft in the same way.
`test_school_structure.cjs` exercises the structure draft and assignment
listing with synthetic data; it does not prove end-to-end app isolation.
`test_trusted_database_audit.cjs` exercises the separate trusted audit
migration on an isolated local database, both with and without the legacy RPC.
