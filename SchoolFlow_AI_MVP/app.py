import sys as _sys
import os as _os
import base64 as _base64
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, datetime, timezone
from app_logic import (
    REQUIRED, OPTIONAL_NAME_COL, NUMERIC_COLS,
    pct, parse_percentage, safe_text, fresh_bytes,
    validate, build_outputs, make_workbook, parent_message,
)

# ---------------------------------------------------------------------------
# Make shared/ importable regardless of working directory
# ---------------------------------------------------------------------------
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_LOGO_LIGHT_PATH = _os.path.join(
    _HERE, "assets", "schoolflow_ai_logo_light_background.png"
)
_LOGO_TRANSPARENT_PATH = _os.path.join(
    _HERE, "assets", "schoolflow_ai_logo_transparent.png"
)
with open(_LOGO_TRANSPARENT_PATH, "rb") as _logo_file:
    _LOGO_DATA_URI = "data:image/png;base64," + _base64.b64encode(
        _logo_file.read()
    ).decode("ascii")
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from shared.styles      import ACCENT_LIME, PRIMARY_NAVY, WHITE, inject_css  # noqa: E402
from shared.i18n        import (  # noqa: E402
    T, get_lang, is_arabic, text_dir, translate_column_labels,
)
from shared.state       import init_state        # noqa: E402
from shared.streamlit_compat import full_width  # noqa: E402
from shared.time_utils  import format_timestamp_riyadh  # noqa: E402
from shared.html_utils  import escape_html  # noqa: E402
from shared.permissions import (             # noqa: E402
    has_permission, require_permission, get_permitted_nav_keys,
    role_display_name,
    ROLE_TEACHER, ROLE_SCHOOL_ADMIN, ROLE_DEMO_REVIEWER, ALL_ROLES,
    VIEW_DASHBOARD, UPLOAD_DATA, VIEW_ANALYSIS, VIEW_REPORTS,
    SEND_PARENT_MESSAGES, USE_LESSON_WORKSPACE, VIEW_STUDENT_PROFILE,
    VIEW_ACADEMIC_PROGRESS, MANAGE_INTERVENTIONS, USE_BLOOM_QUESTIONS,
    VIEW_ADMIN_DASHBOARD, VIEW_AUDIT_LOG,
    DEMO_SECURITY_NOTICE, DEMO_SECURITY_NOTICE_AR,
)
from shared.audit import (
    ACTION_DATA_IMPORT,
    ACTION_PERMISSION_CHECK,
    ACTION_REPORT_DOWNLOADED,
    ACTION_REPORT_GENERATED,
    ACTION_ROLE_CHANGED,
    ENTITY_DATA_FILE,
    ENTITY_PAGE,
    ENTITY_REPORT,
    ENTITY_ROLE,
    STATUS_FAILURE,
    log_event,
    reset_page_audit_dedupe_state,
    sanitize_audit_log,
)
from shared.supabase_backend import (
    SupabaseConfigurationError,
    assign_student_to_class,
    assign_teacher_to_class,
    create_school_class,
    create_supabase_client,
    load_audit_mode,
    load_class_management,
    load_database_audit_events,
    load_memberships,
    load_teaching_assignments,
    remove_teacher_from_class,
    load_workspace,
    read_supabase_settings,
    source_rows_fingerprint,
    sync_workspace,
    workspace_fingerprint,
    workspace_record_fingerprints,
)
from shared.demo_storage import (
    DemoStorageError, demo_path, reviewer_demo_path, load_demo, restore_snapshot, save_demo,
    snapshot, snapshot_digest,
)
from postgrest.exceptions import APIError
from streamlit.errors import StreamlitSecretNotFoundError
from supabase_auth.errors import AuthError
from httpx import HTTPError

_shared_demo = (
    _os.environ.get("SCHOOLFLOW_SHARED_DEMO") == "1"
    or (
        _os.environ.get("SCHOOLFLOW_STANDARD_MODE") != "1"
        and _os.environ.get("SCHOOLFLOW_LOCAL_DEMO") != "1"
    )
)
if _shared_demo:
    _os.environ["SCHOOLFLOW_SHARED_DEMO"] = "1"
st.set_page_config(
    page_title="SchoolFlow AI",
    page_icon=_LOGO_TRANSPARENT_PATH,
    layout="wide",
    initial_sidebar_state="auto" if _shared_demo else "expanded",
)
# Keep the internal page modules out of Streamlit's automatic page discovery.
st.navigation(
    [st.Page(lambda: None, title="SchoolFlow AI", default=True)],
    position="hidden",
).run()

# ===========================================================================
# CSS — Dashboard Design (injected from shared/styles.py)
# ===========================================================================
inject_css()

# ===========================================================================
# Session-state initialisation (must run before sidebar renders)
# ===========================================================================
init_state()
if _shared_demo:
    st.session_state["active_role"] = ROLE_DEMO_REVIEWER
st.session_state["_cloud_sync_failed_this_run"] = False
st.session_state["audit_log"] = sanitize_audit_log(
    st.session_state.get("audit_log", [])
)
reset_page_audit_dedupe_state(
    st.session_state,
    st.session_state.get("page", "dashboard"),
    st.session_state.get("active_role"),
)

_cloud_context = None
if _shared_demo or _os.environ.get("SCHOOLFLOW_LOCAL_DEMO") == "1":
    _cloud_settings = None
else:
    try:
        _cloud_secrets = st.secrets
    except StreamlitSecretNotFoundError:
        _cloud_secrets = {}

    try:
        _cloud_settings = read_supabase_settings(_os.environ, _cloud_secrets)
    except StreamlitSecretNotFoundError:
        _cloud_settings = read_supabase_settings(_os.environ, {})
    except SupabaseConfigurationError as _cloud_config_error:
        st.error(f"Supabase configuration error: {_cloud_config_error}")
        st.stop()

_demo_path = None
if _cloud_settings is None and _os.name == "nt":
    try:
        _demo_path = reviewer_demo_path() if _shared_demo else demo_path()
        if not st.session_state.get("_demo_initialized"):
            _saved_demo = load_demo(_demo_path)
            if _saved_demo is not None:
                _demo_data, _demo_file_digest = _saved_demo
                restore_snapshot(st.session_state, _demo_data)
                st.session_state["_demo_file_digest"] = _demo_file_digest
                st.session_state["_demo_snapshot_digest"] = snapshot_digest(
                    snapshot(st.session_state)
                )
            st.session_state["_demo_initialized"] = True
    except (DemoStorageError, TypeError, ValueError) as _demo_load_error:
        st.error(T(
            f"Could not restore the encrypted demo workspace; the saved file was not changed: {_demo_load_error}",
            f"تعذّرت استعادة مساحة التجربة المشفّرة؛ لم يتغيّر الملف المحفوظ: {_demo_load_error}",
        ))
        st.stop()

if _cloud_settings is not None:
    _cloud_client = st.session_state.get("_supabase_client")
    if _cloud_client is None:
        _cloud_client = create_supabase_client(_cloud_settings)
        st.session_state["_supabase_client"] = _cloud_client
        st.session_state["_supabase_url"] = _cloud_settings.url
    elif st.session_state.get("_supabase_url") != _cloud_settings.url:
        st.error("Supabase settings changed during this session. Please reload the app.")
        st.stop()

    if not st.session_state.get("_supabase_user_id"):
        with st.container(key="sf-login-brand"):
            _login_logo_col = st.columns([1, 2, 1])[1]
            with _login_logo_col:
                st.image(_LOGO_LIGHT_PATH, width=300)
        with st.container(key="sf-login-language"):
            _login_lang_en, _login_lang_ar = st.columns(2)
            with _login_lang_en:
                if st.button(
                    "🌐 English" if not is_arabic() else "English",
                    key="login_lang_en",
                    type="primary" if not is_arabic() else "secondary",
                    **full_width(),
                ):
                    st.session_state["ui_lang"] = "en"
                    st.rerun()
            with _login_lang_ar:
                if st.button(
                    "عربي 🌐" if is_arabic() else "عربي",
                    key="login_lang_ar",
                    type="primary" if is_arabic() else "secondary",
                    **full_width(),
                ):
                    st.session_state["ui_lang"] = "ar"
                    st.rerun()
        with st.form("supabase_login_form"):
            st.subheader(T("Sign in to your school", "تسجيل الدخول إلى المدرسة"))
            _cloud_email = st.text_input(T("Email", "البريد الإلكتروني"))
            _cloud_password = st.text_input(
                T("Password", "كلمة المرور"), type="password"
            )
            _cloud_login = st.form_submit_button(
                T("Sign in", "تسجيل الدخول"), type="primary"
            )
        if _cloud_login:
            try:
                _auth_result = _cloud_client.auth.sign_in_with_password(
                    {"email": _cloud_email.strip(), "password": _cloud_password}
                )
            except (AuthError, HTTPError) as _auth_error:
                st.error(T(
                    f"Sign-in failed: {_auth_error}",
                    f"تعذّر تسجيل الدخول: {_auth_error}",
                ))
            else:
                if not getattr(_auth_result, "user", None):
                    st.error(T(
                        "Supabase did not return an authenticated user.",
                        "لم يُرجع Supabase مستخدمًا موثّقًا.",
                    ))
                else:
                    st.session_state["_supabase_user_id"] = _auth_result.user.id
                    st.session_state["_supabase_email"] = (
                        getattr(_auth_result.user, "email", "") or ""
                    )
                    st.rerun()
        st.info(T(
            "Cloud mode is enabled. Sign in with an account provisioned in Supabase Auth.",
            "وضع التخزين السحابي مفعّل. سجّل الدخول بحساب أُنشئ في Supabase Auth.",
        ))
        st.stop()

    try:
        _auth_user = _cloud_client.auth.get_user().user
        if not _auth_user or _auth_user.id != st.session_state["_supabase_user_id"]:
            st.session_state.pop("_supabase_user_id", None)
            st.session_state.pop("_supabase_email", None)
            st.warning(T(
                "Your Supabase session is no longer valid. Please sign in again.",
                "انتهت صلاحية جلسة Supabase. سجّل الدخول مرة أخرى.",
            ))
            st.stop()
        _memberships = load_memberships(_cloud_client, _auth_user.id)
    except AuthError:
        st.session_state.pop("_supabase_user_id", None)
        st.session_state.pop("_supabase_email", None)
        st.rerun()
    except (APIError, HTTPError) as _membership_error:
        st.error(T(
            f"Could not verify your Supabase identity or school membership: {_membership_error}",
            f"تعذّر التحقق من الهوية أو عضوية المدرسة: {_membership_error}",
        ))
        st.stop()

    if not _memberships:
        st.error(T(
            "This account has no active school membership. Ask a school administrator to add it.",
            "لا يملك هذا الحساب عضوية مدرسة نشطة. اطلب من مدير المدرسة إضافته.",
        ))
        st.stop()

    _membership_by_school = {
        row["school_id"]: row for row in _memberships
        if row.get("school_id") and row.get("role") in {ROLE_TEACHER, ROLE_SCHOOL_ADMIN}
    }
    if not _membership_by_school:
        st.error("No valid school membership role was returned.")
        st.stop()

    _selected_school = st.session_state.get("_supabase_school_id")
    if _selected_school not in _membership_by_school:
        _selected_school = next(iter(_membership_by_school))
    if len(_membership_by_school) > 1:
        _selected_school = st.sidebar.selectbox(
            T("School", "المدرسة"),
            list(_membership_by_school),
            index=list(_membership_by_school).index(_selected_school),
            format_func=lambda value: value,
            key="supabase_school_selector",
        )
    if (
        st.session_state.get("_supabase_school_id") not in (None, _selected_school)
        and st.session_state.get("_cloud_last_fingerprint")
        != workspace_fingerprint(st.session_state)
    ):
        st.error(T(
            "The previous school workspace has unsaved cloud changes. Resolve the save error before switching schools.",
            "توجد تغييرات غير محفوظة في مساحة المدرسة السابقة. عالج خطأ الحفظ قبل تبديل المدرسة.",
        ))
        st.stop()

    _school_role = _membership_by_school[_selected_school]["role"]
    if _school_role != ROLE_SCHOOL_ADMIN:
        st.error(T(
            "Teacher cloud workspaces are disabled until assignment isolation is implemented. "
            "Use the local synthetic demo; do not use real student data.",
            "مساحة المعلم السحابية متوقفة حتى يكتمل عزل التكليفات. "
            "استخدم العرض المحلي ببيانات اصطناعية، ولا تستخدم بيانات طلاب حقيقية.",
        ))
        if st.session_state.get("_cloud_loaded_for"):
            st.warning(T(
                "A previous cloud workspace is still in this session. Its unsaved changes "
                "cannot be saved safely; do not reload or close this page.",
                "ما زالت مساحة سحابية سابقة في هذه الجلسة. لا يمكن حفظ تغييراتها غير المحفوظة "
                "بأمان؛ لا تعِد تحميل الصفحة ولا تغلقها.",
            ))
        elif st.button(T("Sign out", "تسجيل الخروج"), key="blocked_teacher_sign_out"):
            try:
                _cloud_client.auth.sign_out()
            except (AuthError, HTTPError) as _signout_error:
                st.error(T(
                    f"Sign-out failed: {_signout_error}",
                    f"تعذّر تسجيل الخروج: {_signout_error}",
                ))
            else:
                for _key in (
                    "_supabase_client", "_supabase_user_id", "_supabase_email",
                    "_supabase_school_id", "supabase_school_selector",
                ):
                    st.session_state.pop(_key, None)
                st.rerun()
        st.stop()
    _previous_cloud_role = st.session_state.get(
        "_cloud_loaded_role", st.session_state.get("active_role")
    )
    if (
        st.session_state.get("_cloud_loaded_for") == _selected_school
        and _previous_cloud_role != _school_role
    ):
        st.error(T(
            "Your school role changed. This session is blocked to protect cached data. "
            "Open a new session; unsaved changes in this session may be lost.",
            "تغيّر دورك في المدرسة. أُوقفت هذه الجلسة لحماية البيانات المخزنة فيها. "
            "افتح جلسة جديدة؛ قد تفقد التغييرات غير المحفوظة في هذه الجلسة.",
        ))
        st.stop()
    st.session_state["_supabase_school_id"] = _selected_school
    st.session_state["active_role"] = _school_role
    _cloud_context = {
        "client": _cloud_client,
        "school_id": _selected_school,
        "user_id": _auth_user.id,
        "email": st.session_state.get("_supabase_email", ""),
        "role": _school_role,
    }

    if st.session_state.get("_cloud_loaded_for") != _selected_school:
        try:
            _audit_mode = load_audit_mode(_cloud_client)
            _workspace = load_workspace(
                _cloud_client,
                _selected_school,
                _auth_user.id,
                _school_role,
                audit_mode=_audit_mode,
            )
        except (APIError, HTTPError, ValueError) as _load_error:
            st.error(T(
                f"Could not load the school workspace from Supabase: {_load_error}",
                f"تعذّر تحميل مساحة المدرسة من Supabase: {_load_error}",
            ))
            st.stop()
        st.session_state["lesson_records"] = _workspace["lesson_records"]
        st.session_state["lesson_draft"] = _workspace["lesson_draft"]
        st.session_state["lesson_active"] = bool(
            _workspace["lesson_draft"].get("lesson_id")
        )
        st.session_state["participation_log"] = _workspace["participation_log"]
        st.session_state["skill_definitions"] = _workspace["skill_definitions"]
        st.session_state["skill_assessments"] = _workspace["skill_assessments"]
        st.session_state["interventions"] = _workspace["interventions"]
        st.session_state["intervention_checkpoints"] = (
            _workspace["intervention_checkpoints"]
        )
        st.session_state["question_library"] = _workspace["question_library"]
        st.session_state["audit_log"] = sanitize_audit_log(_workspace["audit_log"])
        if _workspace["source_rows"]:
            _stored_rows = pd.DataFrame(_workspace["source_rows"])
            _has_name = OPTIONAL_NAME_COL in _stored_rows.columns
            _clean, _summary, _weekly = build_outputs(_stored_rows, _has_name)
            st.session_state["source_rows"] = _stored_rows
            st.session_state["clean"] = _clean
            st.session_state["summary"] = _summary
            st.session_state["weekly"] = _weekly
            st.session_state["has_name"] = _has_name
            st.session_state["issues"] = validate(_stored_rows)
        else:
            for _key in (
                "source_rows", "clean", "summary", "weekly", "has_name", "issues"
            ):
                st.session_state.pop(_key, None)
        st.session_state["_cloud_previous_skill_ids"] = [
            record.get("id")
            for record in _workspace["skill_definitions"]
            if record.get("id")
        ]
        st.session_state["_cloud_source_fingerprint"] = source_rows_fingerprint(
            _workspace["source_rows"]
        )
        st.session_state["_cloud_import_requested"] = False
        st.session_state["_cloud_record_hashes"] = workspace_record_fingerprints(
            st.session_state, _selected_school
        )
        st.session_state["_cloud_previous_question_ids"] = [
            record.get("id")
            for record in _workspace["question_library"]
            if record.get("id")
        ]
        st.session_state["_cloud_saved_audit_ids"] = [
            record.get("event_id")
            for record in _workspace["audit_log"]
            if record.get("event_id")
        ]
        st.session_state["_cloud_loaded_for"] = _selected_school
        st.session_state["_cloud_loaded_role"] = _school_role
        st.session_state["_cloud_audit_mode"] = _audit_mode
        st.session_state["_cloud_last_fingerprint"] = workspace_fingerprint(
            st.session_state
        )
    elif "_cloud_audit_mode" not in st.session_state:
        try:
            st.session_state["_cloud_audit_mode"] = load_audit_mode(_cloud_client)
        except (APIError, HTTPError, ValueError) as _load_error:
            st.error(T(
                f"Could not verify the database audit mode: {_load_error}",
                f"تعذّر التحقق من وضع تدقيق قاعدة البيانات: {_load_error}",
            ))
            st.stop()
        st.session_state["_cloud_loaded_role"] = _school_role


def _audit_report_download() -> None:
    """Record a report download only when Streamlit invokes its click callback."""
    role = st.session_state.get("active_role", "unknown")
    if role not in ALL_ROLES:
        role = "unknown"
    st.session_state["audit_log"] = log_event(
        st.session_state.get("audit_log", []),
        action=ACTION_REPORT_DOWNLOADED,
        actor_role=role,
        entity_type=ENTITY_REPORT,
    )


def _sync_cloud_workspace_if_dirty() -> bool:
    """Persist changed workspace state once and report failures to the user."""
    if _cloud_context is None:
        return True

    current_fingerprint = workspace_fingerprint(st.session_state)
    if current_fingerprint == st.session_state.get("_cloud_last_fingerprint"):
        return True

    try:
        sync_workspace(
            _cloud_context["client"],
            _cloud_context["school_id"],
            _cloud_context["user_id"],
            st.session_state,
            role=_cloud_context["role"],
            audit_mode=st.session_state["_cloud_audit_mode"],
        )
    except (APIError, HTTPError, ValueError, TypeError) as save_error:
        st.session_state["_cloud_sync_failed_this_run"] = True
        st.error(T(
            f"Cloud save failed; these changes remain only in this browser session until a retry succeeds. "
            f"Reloading or closing the page may lose them: {save_error}",
            f"فشل الحفظ السحابي؛ ما زالت التغييرات في جلسة المتصفح فقط حتى تنجح إعادة المحاولة. "
            f"قد تؤدي إعادة تحميل الصفحة أو إغلاقها إلى فقدانها: {save_error}",
        ))
        return False

    st.session_state["_cloud_last_fingerprint"] = workspace_fingerprint(
        st.session_state
    )
    return True


# ===========================================================================
# REMOVED MARKER — original inline <style> block moved to shared/styles.py
# ===========================================================================
_CSS_PLACEHOLDER_DO_NOT_USE = """
<style>
/* ── Fonts ───────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif;
}

/* ── App background ──────────────────────────────────────────────────── */
.stApp { background-color: #FFFFFF; }

/* ── Hide Streamlit chrome ───────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar — primary navy ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #102B4E !important;
    border-left: none !important;
}
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
[data-testid="stSidebarNav"] { display: none; }

/* ── Top bar ─────────────────────────────────────────────────────────── */
.sf-topbar {
    background: #FFFFFF;
    border-bottom: 1px solid #E8EBF0;
    padding: 0.5rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.2rem;
    /* direction set inline by Python (_topbar_dir) */
}
.sf-topbar-date {
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.82rem; color: #4B5563; font-weight: 500;
}
.sf-topbar-actions {
    display: flex; align-items: center; gap: 0.6rem;
}
.sf-topbar-icon {
    width: 32px; height: 32px;
    border-radius: 8px; border: 1px solid #E8EBF0;
    background: #FFFFFF;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.9rem; cursor: pointer;
}
.sf-lang-btn {
    padding: 3px 12px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
}
.sf-lang-ar {
    background: #102B4E; color: #FFFFFF;
    border: 1px solid #102B4E;
}
.sf-lang-en {
    background: transparent; color: #6B7280;
    border: 1px solid #E8EBF0;
    margin-right: 4px;
}

/* ── Hero banner ─────────────────────────────────────────────────────── */
.sf-hero {
    background: #102B4E;
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    /* direction set inline by Python (_hero_dir) */
    position: relative;
    overflow: hidden;
}
.sf-hero::before {
    content: '';
    position: absolute;
    top: -40px; left: -40px;
    width: 200px; height: 200px;
    background: rgba(199,232,62,0.08);
    border-radius: 50%;
}
.sf-hero::after {
    content: '';
    position: absolute;
    bottom: -60px; right: 30%;
    width: 280px; height: 280px;
    background: rgba(255,255,255,0.04);
    border-radius: 50%;
}
.sf-hero-text { position: relative; z-index: 2; }
.sf-hero-greeting {
    font-size: 0.85rem; color: #C7E83E;
    font-weight: 600; margin-bottom: 0.3rem;
    display: flex; align-items: center; gap: 0.4rem;
}
.sf-hero-title {
    font-size: 1.7rem; font-weight: 900;
    color: #FFFFFF; line-height: 1.25;
    margin-bottom: 0.5rem;
}
.sf-hero-subtitle {
    font-size: 0.88rem; color: rgba(255,255,255,0.80);
    line-height: 1.6; max-width: 420px;
}
.sf-hero-badge {
    position: relative; z-index: 2;
    background: rgba(199,232,62,0.18);
    border: 1px solid rgba(199,232,62,0.45);
    border-radius: 12px;
    padding: 0.7rem 1.2rem;
    text-align: center;
    min-width: 130px;
}
.sf-hero-badge-icon { font-size: 2rem; }
.sf-hero-badge-text {
    font-size: 0.75rem; color: #C7E83E;
    font-weight: 600; margin-top: 0.3rem;
}

/* ── Metric cards ─────────────────────────────────────────────────────── */
.sf-metrics-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.4rem;
    /* direction set inline by Python (_kpi_dir) */
}
.sf-metric-card {
    background: #FFFFFF;
    border-radius: 14px;
    border: 1px solid #E8EBF0;
    padding: 1.1rem 1.2rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    display: flex;
    align-items: flex-start;
    gap: 0.85rem;
    /* direction inherited from parent .sf-metrics-row */
}
.sf-metric-icon {
    width: 44px; height: 44px;
    border-radius: 11px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.3rem; flex-shrink: 0;
}
.sf-icon-green  { background: rgba(16,43,78,0.10); }
.sf-icon-gold   { background: rgba(199,232,62,0.12); }
.sf-icon-blue   { background: rgba(16,43,78,0.10); }
.sf-icon-purple { background: rgba(199,232,62,0.18); }
.sf-metric-body { flex: 1; }
.sf-metric-label { font-size: 0.76rem; color: #6B7280; font-weight: 600; margin-bottom: 0.2rem; }
.sf-metric-value { font-size: 1.65rem; font-weight: 900; color: #102B4E; line-height: 1; }
.sf-metric-sub   { font-size: 0.75rem; color: #6B7280; margin-top: 0.25rem; }
.sf-metric-badge-up   { color: #16a34a; font-weight: 700; font-size: 0.75rem; }
.sf-metric-badge-warn { color: #D4A017; font-weight: 700; font-size: 0.75rem; }

/* ── Two-column section ──────────────────────────────────────────────── */
.sf-two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.2rem;
    margin-bottom: 1.4rem;
}
.sf-two-col-wide { grid-template-columns: 3fr 2fr; }

/* ── White cards ─────────────────────────────────────────────────────── */
.sf-card {
    background: #FFFFFF;
    border-radius: 14px;
    border: 1px solid #E8EBF0;
    padding: 1.3rem 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    /* direction set inline by Python (_dash_dir) */
}
.sf-card-header {
    display: flex; align-items: center; gap: 0.55rem;
    margin-bottom: 1rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid #F0F1F5;
    /* direction inherited from parent .sf-card */
}
.sf-card-header-icon {
    width: 30px; height: 30px;
    border-radius: 8px;
    background: rgba(16,43,78,0.10);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.95rem;
}
.sf-card-title {
    font-size: 0.92rem; font-weight: 700; color: #102B4E;
}

/* ── Section headers ─────────────────────────────────────────────────── */
.sf-section-header {
    display: flex; align-items: center; gap: 0.6rem;
    margin: 1.6rem 0 0.85rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #E8EBF0;
    /* direction set inline by Python per section */
}
.sf-section-num {
    background: #102B4E; color: #C7E83E;
    width: 28px; height: 28px;
    border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.80rem; font-weight: 700; flex-shrink: 0;
}
.sf-section-title { font-size: 0.98rem; font-weight: 700; color: #102B4E; }

/* ── Observations list ───────────────────────────────────────────────── */
.sf-obs-item {
    display: flex; align-items: flex-start; gap: 0.7rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid #E8EBF0;
    /* direction inherited from parent .sf-card */
}
.sf-obs-item:last-child { border-bottom: none; }
.sf-obs-code {
    background: #102B4E; color: #FFFFFF;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 8px; border-radius: 5px;
    flex-shrink: 0; margin-top: 1px;
}
.sf-obs-text { font-size: 0.82rem; color: #374151; line-height: 1.5; }
.sf-obs-empty { font-size: 0.85rem; color: #4B5563; text-align: center; padding: 1rem 0; }

/* ── Quick actions grid ──────────────────────────────────────────────── */
.sf-quick-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
}
.sf-quick-btn {
    background: #FFFFFF;
    border: 1px solid #E8EBF0;
    border-radius: 11px;
    padding: 0.85rem 1rem;
    display: flex; align-items: center; gap: 0.7rem;
    cursor: pointer; transition: all 0.18s ease;
    /* direction inherited from page-level direction */
    text-decoration: none;
}
.sf-quick-btn:hover { background: rgba(199,232,62,0.12); border-color: #102B4E; }
.sf-quick-icon {
    width: 36px; height: 36px; border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; flex-shrink: 0;
}
.sf-qi-green  { background: rgba(16,43,78,0.10); }
.sf-qi-gold   { background: rgba(199,232,62,0.12); }
.sf-qi-blue   { background: rgba(16,43,78,0.10); }
.sf-qi-purple { background: rgba(199,232,62,0.18); }
.sf-quick-label {
    font-size: 0.82rem; font-weight: 700; color: #102B4E;
    line-height: 1.3;
}

.sf-quick-sub { font-size: 0.72rem; color: #6B7280; }

/* ── Upload card ─────────────────────────────────────────────────────── */
.sf-upload-area {
    background: #FFFFFF;
    border: 2px dashed rgba(16,43,78,0.40);
    border-radius: 14px;
    padding: 1.5rem 1.8rem;
    text-align: center;
    transition: border-color 0.2s;
}
.sf-upload-area:hover { border-color: #102B4E; }

/* ── Status pills ────────────────────────────────────────────────────── */
.sf-pill-ok {
    background: rgba(22,163,74,0.10); color: #166534;
    border: 1px solid rgba(22,163,74,0.25);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}
.sf-pill-warn {
    background: rgba(212,160,23,0.10); color: #92400e;
    border: 1px solid rgba(212,160,23,0.30);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
div.stButton > button[kind="primary"] {
    background: #102B4E !important;
    color: #FFFFFF !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(16,43,78,0.28) !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
}
div.stButton > button[kind="primary"]:hover {
    background: #102B4E !important;
    transform: translateY(-1px) !important;
}
div.stButton > button {
    border-radius: 9px !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
}
div.stDownloadButton > button {
    background: #C7E83E !important;
    color: #102B4E !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(199,232,62,0.28) !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
}
div.stDownloadButton > button:hover {
    background: #C7E83E !important;
    transform: translateY(-1px) !important;
}

/* ── Dataframe ───────────────────────────────────────────────────────── */
.stDataFrame {
    border-radius: 10px !important;
    border: 1px solid #E8EBF0 !important;
}

/* ── Selectbox / inputs ──────────────────────────────────────────────── */
.stSelectbox > div > div { border-radius: 9px !important; }
.stFileUploader > div   { border-radius: 9px !important; }
.stTextArea > div > div > textarea {
    border-radius: 9px !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
    font-size: 0.87rem !important;
}

/* ── Expander ────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: #FFFFFF !important;
    border: 1px solid #E8EBF0 !important;
    border-radius: 9px !important;
    font-weight: 700 !important; color: #102B4E !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
}
.streamlit-expanderContent {
    background: #FFFFFF !important;
    border: 1px solid #E8EBF0 !important;
    border-top: none !important;
    border-radius: 0 0 9px 9px !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
.sf-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #C7E83E55, transparent);
    margin: 1.6rem 0; border: none;
}

/* ── Footer ──────────────────────────────────────────────────────────── */
.sf-footer {
    text-align: center; padding: 1.4rem 1rem 2rem;
    margin-top: 2.5rem; border-top: 1px solid #E8EBF0;
    color: #6B7280; font-size: 0.76rem;
    /* direction set inline by Python (_footer_dir equivalent) */
}
.sf-footer strong { color: #102B4E; }

/* ── Caption ─────────────────────────────────────────────────────────── */
.stCaption { color: #6B7280 !important; font-size: 0.78rem !important; }

/* ── Sidebar nav item active ─────────────────────────────────────────── */
.sf-nav-item-active {
    background: #C7E83E !important;
    color: #102B4E !important;
    border-radius: 9px;
    font-weight: 700 !important;
}

/* ── Sidebar language toggle: dim the inactive button ───────────────── */
[data-testid="stSidebar"] button[kind="secondary"] {
    opacity: 0.55 !important;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    opacity: 0.80 !important;
}

/* ── Chat input bottom bar — reduce height, prevent content overlap ──── */
[data-testid="stBottom"] {
    padding-bottom: 0.5rem !important;
    padding-top: 0.5rem !important;
    background: #FFFFFF !important;
    border-top: 1px solid #E8EBF0 !important;
    box-shadow: 0 -2px 12px rgba(0,0,0,0.06) !important;
}
[data-testid="stBottom"] > div {
    padding-bottom: 0.25rem !important;
    max-width: 900px;
    margin: 0 auto;
}
/* Shrink the textarea inside the chat composer */
[data-testid="stChatInputTextArea"] {
    font-size: 0.92rem !important;
    font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif !important;
    min-height: 2.4rem !important;
    max-height: 6rem !important;
    resize: none !important;
    color: #102B4E !important;
}
[data-testid="stChatInputTextArea"]::placeholder {
    color: #9CA3AF !important;
    font-size: 0.87rem !important;
}
/* Add bottom padding to main content so last message is never hidden */
section.main > div.block-container {
    padding-bottom: 6rem !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   Chat message bubbles
   Streamlit renders chat messages as:
     [data-testid="stChatMessage"]
   with a nested avatar element whose data-testid is either
     "stChatMessageAvatarUser" or "stChatMessageAvatarAssistant"
   We also add attribute-value selectors on [aria-label] and class-name
   fragments as cross-version fallbacks.
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Base reset: every message container ───────────────────────────── */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
    margin-bottom: 0.75rem !important;
    padding: 0.75rem 1rem !important;
}
/* Default text colour (overridden per role below) */
[data-testid="stChatMessage"] *:not(code) {
    color: #102B4E !important;
}

/* ── USER bubble — white card with dark text ────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #FFFFFF !important;
    border: 1.5px solid #E8EBF0 !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) li,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) strong,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) em,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) a,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div {
    color: #102B4E !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) code {
    background: #F0F1F5 !important;
    color: #102B4E !important;
    border-radius: 4px; padding: 1px 5px;
}

/* ── ASSISTANT bubble — primary navy background, pure white text ─────── */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #102B4E !important;
    border: 1.5px solid #102B4E !important;
    box-shadow: 0 2px 10px rgba(16,43,78,0.25) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) li,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) span,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) strong,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) em,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) a,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) div,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) label,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) td,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) th {
    color: #FFFFFF !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) code {
    background: rgba(255,255,255,0.18) !important;
    color: #C7E83E !important;
    border-radius: 4px; padding: 2px 6px;
    font-weight: 600;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) .stCaption,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) small {
    color: rgba(255,255,255,0.75) !important;
}
/* Avatar icon background inside green bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
    [data-testid="stChatMessageAvatarAssistant"] {
    background: rgba(255,255,255,0.15) !important;
    border-radius: 50%;
}

/* ── Fallback selectors for Streamlit builds that use class names ────── */
/* These match any remaining stChatMessage div that was not caught above  */
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarAssistant"])) {
    background: #FFFFFF !important;
    border: 1px solid #E8EBF0 !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarAssistant"])) * {
    color: #102B4E !important;
}
</style>
"""
# End of _CSS_PLACEHOLDER_DO_NOT_USE  (kept as dead string; not rendered)


# ===========================================================================
# Helper: build SVG bar chart from weekly data
# ===========================================================================

def _build_weekly_svg(weekly_df: pd.DataFrame, arabic: bool = False) -> str:
    """Generate a compact SVG bar+line chart for weekly attendance & task rates."""
    weeks = weekly_df["Week"].tolist()
    n = len(weeks)
    if n == 0:
        return ""

    # Extract numeric rates
    att_rates  = [parse_percentage(r) for r in weekly_df["Attendance rate"].tolist()]
    task_rates = [parse_percentage(r) for r in weekly_df["Task completion"].tolist()]

    W, H = 340, 180
    pad_l, pad_r, pad_t, pad_b = 30, 15, 15, 40
    chart_w = W - pad_l - pad_r
    chart_h = H - pad_t - pad_b

    bar_w = max(10, int(chart_w / n * 0.5))
    slot_w = chart_w / n

    def x_center(i):
        return pad_l + slot_w * i + slot_w / 2

    def y_val(v, min_v=0):
        clamped = max(min_v, min(v, 110))
        return pad_t + chart_h * (1 - (clamped - min_v) / (110 - min_v))

    # Y-axis grid lines
    grid_lines = ""
    for tick in [0, 25, 50, 75, 100]:
        y = y_val(tick)
        grid_lines += (
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}" '
            f'stroke="#A9C0D5" stroke-width="1"/>'
            f'<text x="{pad_l - 4}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="9" fill="#405D75">{tick}%</text>'
        )

    # Bars (lime — attendance)
    bars = ""
    for i, v in enumerate(att_rates):
        x = x_center(i) - bar_w / 2
        y = y_val(v)
        bh = (H - pad_b) - y
        bars += (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{max(2,bh):.1f}" '
            f'rx="3" fill="{ACCENT_LIME}" opacity="0.9"/>'
        )

    # Line (navy — task completion)
    pts = " ".join(f"{x_center(i):.1f},{y_val(v):.1f}" for i, v in enumerate(task_rates))
    line_path = f'<polyline points="{pts}" fill="none" stroke="{PRIMARY_NAVY}" stroke-width="2.5" stroke-linejoin="round"/>'
    dots = "".join(
        f'<circle cx="{x_center(i):.1f}" cy="{y_val(v):.1f}" r="4" fill="{ACCENT_LIME}" stroke="{PRIMARY_NAVY}" stroke-width="1.5"/>'
        for i, v in enumerate(task_rates)
    )

    week_label = "الأسبوع" if arabic else "Week"
    attendance_label = "نسبة الحضور" if arabic else "Attendance"
    task_label = "إنجاز المهام" if arabic else "Task completion"

    # X-axis labels
    x_labels = "".join(
        f'<text x="{x_center(i):.1f}" y="{H - pad_b + 14}" text-anchor="middle" '
        f'font-size="9" fill="#405D75">{week_label} {escape_html(w)}</text>'
        for i, w in enumerate(weeks)
    )

    # Legend
    legend = (
        f'<rect x="{pad_l}" y="{H - 10}" width="10" height="8" rx="2" fill="{ACCENT_LIME}" opacity="0.9"/>'
        f'<text x="{pad_l + 13}" y="{H - 3}" font-size="8.5" fill="#102B4E">{attendance_label}</text>'
        f'<line x1="{pad_l + 80}" y1="{H - 6}" x2="{pad_l + 93}" y2="{H - 6}" '
        f'stroke="{PRIMARY_NAVY}" stroke-width="2.5"/>'
        f'<circle cx="{pad_l + 87}" cy="{H - 6}" r="3" fill="{ACCENT_LIME}" stroke="{PRIMARY_NAVY}" stroke-width="1"/>'
        f'<text x="{pad_l + 96}" y="{H - 3}" font-size="8.5" fill="#102B4E">{task_label}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block;">'
        f'{grid_lines}{bars}{line_path}{dots}{x_labels}{legend}'
        f'</svg>'
    )


# ===========================================================================
# Language + direction (computed from session_state via shared/i18n.py)
# init_state() was called above, so "ui_lang" is guaranteed to be set.
# T, get_lang, is_arabic, text_dir are all imported from shared.i18n.
# ===========================================================================

_L     = get_lang()       # "en" | "ar"
_IS_AR = is_arabic()      # bool
_DIR   = text_dir()       # "ltr" | "rtl"
_AR_COLUMN_LABELS = {
    "Student code": "رمز الطالب",
    "Student name": "اسم الطالب",
    "Weeks recorded": "الأسابيع المسجلة",
    "Attendance": "الحضور",
    "Attendance attended/scheduled": "الحضور الفعلي/المجدول",
    "Task completion": "إنجاز المهام",
    "Tasks completed/set": "المهام المنجزة/المحددة",
    "Mean quiz / 10": "متوسط الاختبار / 10",
    "Quiz weeks recorded": "أسابيع الاختبارات المسجلة",
    "Latest observation": "أحدث ملاحظة",
    "Next step": "الخطوة التالية",
    "Week": "الأسبوع",
    "Attended days": "أيام الحضور",
    "Scheduled days": "الأيام المجدولة",
    "Tasks completed": "المهام المنجزة",
    "Tasks set": "المهام المحددة",
    "Days scheduled": "الأيام المجدولة",
    "Days attended": "أيام الحضور",
    "Observation": "الملاحظة",
    "Attendance rate": "نسبة الحضور",
    "Column": "العمود",
    "Issue": "المشكلة",
}


def _localized_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    translated = translate_column_labels(list(frame.columns), _AR_COLUMN_LABELS)
    return frame.rename(columns=dict(zip(frame.columns, translated)))


def _deny_page(permission: str) -> None:
    """Render a standardised access-denied message for a page."""
    result = require_permission(st.session_state.get("active_role"), permission)
    role = st.session_state.get("active_role", "unknown")
    if role not in ALL_ROLES:
        role = "unknown"
    denied_context = (st.session_state.get("page", ""), permission, role)
    if st.session_state.get("_audit_denied_context") != denied_context:
        st.session_state["audit_log"] = log_event(
            st.session_state.get("audit_log", []),
            action=ACTION_PERMISSION_CHECK,
            actor_role=role,
            entity_type=ENTITY_PAGE,
            status=STATUS_FAILURE,
        )
        st.session_state["_audit_denied_context"] = denied_context
    st.error(T(
        result.get("reason", "You do not have permission to access this page."),
        result.get("reason_ar", "ليس لديك صلاحية الوصول إلى هذه الصفحة."),
    ))


_PAGE_PERMISSIONS = {
    "dashboard": VIEW_DASHBOARD,
    "upload": UPLOAD_DATA,
    "analysis": VIEW_ANALYSIS,
    "reports": VIEW_REPORTS,
    "messages": SEND_PARENT_MESSAGES,
    "assistant": VIEW_DASHBOARD,
    "settings": VIEW_DASHBOARD,
    "lesson_workspace": USE_LESSON_WORKSPACE,
    "student_profile": VIEW_STUDENT_PROFILE,
    "academic_progress": VIEW_ACADEMIC_PROGRESS,
    "interventions": MANAGE_INTERVENTIONS,
    "bloom_questions": USE_BLOOM_QUESTIONS,
    "admin_dashboard": VIEW_ADMIN_DASHBOARD,
    "audit_log": VIEW_AUDIT_LOG,
}


def _navigate_to(page: str) -> None:
    permission = _PAGE_PERMISSIONS.get(page)
    if permission and has_permission(
        st.session_state.get("active_role"), permission
    ):
        st.session_state["page"] = page


# Active role — read once per render; also set inside sidebar below
_active_role = st.session_state.get("active_role", ROLE_TEACHER)

# ===========================================================================
# UI — Sidebar
# ===========================================================================
with st.sidebar:
    # Logo block
    _sub = (
        "منصة ذكية لمساعدة المعلمين<br>وإدارة متابعة الطلاب"
        if _IS_AR else
        "Smart platform for teachers<br>and student tracking"
    )
    st.image(_LOGO_TRANSPARENT_PATH, width=190)
    st.markdown(f"""
    <div style="text-align:center; padding: 0 0.5rem 1rem;">
      <div style="font-size:0.72rem;color:rgba(255,255,255,0.65);
                  margin-top:0.2rem;line-height:1.5;font-family:'Segoe UI',Tahoma,'Noto Sans Arabic',Arial,system-ui,sans-serif;">
        {_sub}
      </div>
    </div>
    <hr style="border-color:rgba(255,255,255,0.12);margin:0 0 0.8rem;"/>
    """, unsafe_allow_html=True)

    # ── Language toggle ───────────────────────────────────────────────────
    _lang_col_en, _lang_col_ar = st.columns(2)
    with _lang_col_en:
        if st.button(
            "🌐 English" if not _IS_AR else "English",
            key="lang_en",
            **full_width(),
            type="primary" if not _IS_AR else "secondary",
        ):
            st.session_state["ui_lang"] = "en"
            st.rerun()
    with _lang_col_ar:
        if st.button(
            "عربي 🌐" if _IS_AR else "عربي",
            key="lang_ar",
            **full_width(),
            type="primary" if _IS_AR else "secondary",
        ):
            st.session_state["ui_lang"] = "ar"
            st.rerun()

    st.markdown('<hr style="border-color:rgba(255,255,255,0.12);margin:0.6rem 0 0.8rem;"/>', unsafe_allow_html=True)

    if _cloud_context is None:
        # ── Role selector (Demo / local context — NOT production auth) ────
        _active_role = st.session_state.get("active_role", ROLE_TEACHER)
        if not _shared_demo:
            st.caption(T(
                "Local mode: changes remain in this session unless you save the optional demo snapshot.",
                "الوضع المحلي: تبقى التغييرات في هذه الجلسة ما لم تحفظ نسخة التجربة الاختيارية.",
            ))
        if _demo_path is not None:
            st.caption(T(
                "Optional Windows-protected storage is for synthetic data only. "
                "Everyone using this Windows account shares the demo; it is not authentication. "
                "Save again after changes. Chat and audit events are not saved.",
                "التخزين الاختياري المحمي بـWindows للبيانات الاصطناعية فقط. "
                "يشترك مستخدمو حساب Windows نفسه في التجربة؛ لا يُعد هذا مصادقة. "
                "احفظ مجددًا بعد التغييرات. لا تُحفظ المحادثات أو أحداث التدقيق.",
            ))
            try:
                _demo_data = snapshot(st.session_state)
                _current_demo_digest = snapshot_digest(_demo_data)
            except (TypeError, ValueError) as _demo_snapshot_error:
                st.error(T(
                    f"Cannot prepare the local demo for saving: {_demo_snapshot_error}",
                    f"تعذّر تجهيز التجربة المحلية للحفظ: {_demo_snapshot_error}",
                ))
            else:
                if st.session_state.get("_demo_file_digest") and (
                    _current_demo_digest != st.session_state.get("_demo_snapshot_digest")
                ):
                    st.warning(T(
                        "Demo changes are not saved; reload or closing the page may lose them.",
                        "تغييرات التجربة غير محفوظة؛ قد تفقدها عند إعادة تحميل الصفحة أو إغلاقها.",
                    ))
                _demo_confirmed = st.checkbox(
                    T("I confirm this workspace contains synthetic data only.",
                      "أؤكد أن مساحة العمل تحتوي على بيانات اصطناعية فقط."),
                    key="demo_synthetic_confirmation",
                )
                if st.button(
                    T("Save encrypted demo", "حفظ التجربة مشفّرة"),
                    key="save_synthetic_demo",
                    disabled=not _demo_confirmed,
                ):
                    try:
                        st.session_state["_demo_file_digest"] = save_demo(
                            _demo_path, _demo_data, st.session_state.get("_demo_file_digest")
                        )
                    except DemoStorageError as _demo_save_error:
                        st.error(T(
                            f"Demo save failed; changes remain in this session only: {_demo_save_error}",
                            f"فشل حفظ التجربة؛ تبقى التغييرات في هذه الجلسة فقط: {_demo_save_error}",
                        ))
                    else:
                        st.session_state["_demo_snapshot_digest"] = _current_demo_digest
                        st.success(T("Encrypted demo saved.", "حُفظت التجربة مشفّرة."))
        if not _shared_demo:
            _role_options_en  = [("teacher", "👨‍🏫 Teacher"), ("school_admin", "🏫 School Admin")]
            _role_options_ar  = [("teacher", "👨‍🏫 معلم"),    ("school_admin", "🏫 مدير المدرسة")]
            _role_opts        = _role_options_ar if _IS_AR else _role_options_en
            _role_keys        = [r for r, _ in _role_opts]
            _role_labels      = [l for _, l in _role_opts]
            _role_idx         = _role_keys.index(_active_role) if _active_role in _role_keys else 0

            st.markdown(
                f'<div style="font-size:0.70rem;color:rgba(255,255,255,0.55);'
                f'margin-bottom:0.2rem;font-family:\'Segoe UI\',Tahoma,\'Noto Sans Arabic\',Arial,system-ui,sans-serif;">'
                f'{T("Demo Role Context (not secure auth):", "سياق الدور التجريبي (ليس مصادقة آمنة):")}'
                f'</div>',
                unsafe_allow_html=True,
            )
            _selected_role_label = st.selectbox(
                T("Active Role", "الدور النشط"),
                _role_labels,
                index=_role_idx,
                key="role_selector",
                label_visibility="collapsed",
            )
            _new_role = _role_keys[_role_labels.index(_selected_role_label)]
            if _new_role != _active_role:
                st.session_state["audit_log"] = log_event(
                    st.session_state.get("audit_log", []),
                    action=ACTION_ROLE_CHANGED,
                    actor_role=_active_role,
                    entity_type=ENTITY_ROLE,
                    changed_fields=["active_role"],
                    extra={"role_from": _active_role, "role_to": _new_role},
                )
                st.session_state["active_role"] = _new_role
            _active_role = _new_role
    else:
        _active_role = _cloud_context["role"]
        st.caption(
            f"{_cloud_context['email']} · "
            f"{role_display_name(_active_role, arabic=_IS_AR)}"
        )
        st.caption(T(
            "Supported database changes are audited; reads, downloads and failed attempts "
            "are not persisted in the database audit log.",
            "تُسجّل تغييرات قاعدة البيانات المدعومة؛ أما القراءة والتنزيل والمحاولات الفاشلة "
            "فلا تُحفظ في سجل تدقيق قاعدة البيانات.",
        ))
        if st.button(T("Sign out", "تسجيل الخروج"), key="supabase_sign_out"):
            if _sync_cloud_workspace_if_dirty():
                try:
                    _cloud_context["client"].auth.sign_out()
                except (AuthError, HTTPError) as _signout_error:
                    st.error(T(
                        f"Sign-out failed: {_signout_error}",
                        f"تعذّر تسجيل الخروج: {_signout_error}",
                    ))
                else:
                    for _key in (
                        "_supabase_client",
                        "_supabase_user_id",
                        "_supabase_email",
                        "_supabase_school_id",
                        "supabase_school_selector",
                        "_cloud_loaded_for",
                        "_cloud_loaded_role",
                        "_cloud_audit_mode",
                        "_cloud_last_fingerprint",
                        "_cloud_previous_skill_ids",
                        "_cloud_source_fingerprint",
                        "_cloud_import_requested",
                        "_cloud_record_hashes",
                        "_cloud_previous_question_ids",
                        "_cloud_saved_audit_ids",
                    ):
                        st.session_state.pop(_key, None)
                    st.rerun()

    st.markdown('<hr style="border-color:rgba(255,255,255,0.12);margin:0.6rem 0 0.8rem;"/>', unsafe_allow_html=True)

    # Navigation — filtered by active role
    _all_nav_items = [
        ("🏠", T("Dashboard",          "لوحة التحكم"),        "dashboard"),
        ("📤", T("Upload Student Data", "رفع بيانات الطلاب"),  "upload"),
        ("📊", T("Performance Analysis","تحليل الأداء"),        "analysis"),
        ("📋", T("Student Reports",     "تقارير الطلاب"),       "reports"),
        ("✉",  T("Parent Messages",     "رسائل أولياء الأمور"),"messages"),
        ("🤖", T("AI Assistant",         "مساعد الذكاء الاصطناعي"), "assistant"),
        ("📖", T("Lesson Workspace",    "مساحة عمل الحصة"),    "lesson_workspace"),
        ("👤", T("Student Profile",     "ملف الطالب"),          "student_profile"),
        ("🎯", T("Skills & Progress",   "المهارات والتحصيل"),   "academic_progress"),
        ("🛟", T("Interventions",        "التدخلات والدعم"),     "interventions"),
        ("🧠", T("Bloom Questions",      "أسئلة بلوم"),          "bloom_questions"),
        ("⚙",  T("Project Settings",   "إعدادات المشروع"),    "settings"),
        ("🏫", T("Admin Dashboard",     "لوحة الإدارة"),        "admin_dashboard"),
        ("🧾", T("Audit Log",           "سجل التدقيق"),          "audit_log"),
    ]
    _permitted_keys = set(get_permitted_nav_keys(_active_role))
    nav_items = [(icon, label, key) for icon, label, key in _all_nav_items if key in _permitted_keys]

    current_page = st.session_state.get("page", "dashboard")

    for icon, label, key in nav_items:
        is_active = (current_page == key)
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{key}",
            **full_width(),
            type="primary" if is_active else "secondary",
        ):
            _navigate_to(key)
            st.rerun()

    # ── Online AI toggle ─────────────────────────────────────────────────────
    st.markdown('<hr style="border-color:rgba(255,255,255,0.12);margin:0.6rem 0 0.8rem;"/>', unsafe_allow_html=True)
    _ai_label = T("🤖 Enable Online AI", "🤖 تفعيل الذكاء الاصطناعي")
    _ai_help  = T(
        "When ON, any unrecognised command you type may be sent to OpenAI. "
        "Do not include student names, codes, grades, or any identifiable "
        "information in your message. "
        "Requires the openai package and a configured API key in "
        ".streamlit/secrets.toml.",
        "عند التفعيل، قد تُرسَل الأوامر غير المعروفة التي تكتبها إلى OpenAI. "
        "لا تُدرج أسماء الطلاب أو رموزهم أو درجاتهم أو أي معلومات تعريفية "
        "في رسالتك. "
        "يتطلب تثبيت حزمة openai ومفتاح API مُهيَّأ في "
        ".streamlit/secrets.toml."
    )
    # "online_ai_enabled" is now guaranteed by init_state() — no guard needed
    if _shared_demo:
        _online_ai_enabled = False
        st.caption(T(
            "Demo chat uses local rules. Gemini examples are available on request; OpenAI is disabled.",
            "محادثة العرض محلية. تتوفر أمثلة Gemini عند الطلب؛ اتصال OpenAI متوقف.",
        ))
    else:
        _online_ai_enabled = st.toggle(
            _ai_label,
            value=st.session_state["online_ai_enabled"],
            help=_ai_help,
            key="online_ai_toggle",
        )
    st.session_state["online_ai_enabled"] = _online_ai_enabled

    # User block — shows active demo role
    _user_dir = "rtl" if _IS_AR else "ltr"
    _user_name = (
        escape_html(_cloud_context["email"])
        if _cloud_context else
        T("Demo user", "مستخدم تجريبي")
    )
    _user_role_disp = (
        role_display_name(ROLE_DEMO_REVIEWER, arabic=_IS_AR)
        if _shared_demo else role_display_name(_active_role, arabic=_IS_AR)
    )
    _user_init = "م" if _IS_AR else "U"
    st.markdown(f"""
    <hr style="border-color:rgba(255,255,255,0.12);margin:1.2rem 0 0.8rem;"/>
    <div style="display:flex;align-items:center;gap:0.7rem;padding:0.5rem 0.3rem;
                direction:{_user_dir};">
      <div style="width:38px;height:38px;background:{ACCENT_LIME};border-radius:50%;
                  display:flex;align-items:center;justify-content:center;
                  font-size:1rem;font-weight:900;color:{PRIMARY_NAVY};flex-shrink:0;">{_user_init}</div>
      <div>
        <div style="font-size:0.85rem;font-weight:700;color:#FFFFFF;
                    font-family:'Segoe UI',Tahoma,'Noto Sans Arabic',Arial,system-ui,sans-serif;">{_user_name}</div>
        <div style="font-size:0.72rem;color:rgba(255,255,255,0.60);
                    font-family:'Segoe UI',Tahoma,'Noto Sans Arabic',Arial,system-ui,sans-serif;">{_user_role_disp}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

if _shared_demo:
    st.warning(T(
        "Shared demo: synthetic data only. Do not enter real names, student data, "
        "passwords or sensitive information. Changes are not saved until you explicitly "
        "save the encrypted demo. Saved data is shared by this Windows account.",
        "عرض مشترك: بيانات اصطناعية فقط. لا تُدخل أسماء حقيقية أو بيانات طلاب "
        "أو كلمات مرور أو معلومات حساسة. لا تُحفظ التغييرات حتى تحفظ التجربة "
        "المشفّرة صراحةً. يشترك مستخدمو حساب Windows هذا في البيانات المحفوظة.",
    ))
    if _demo_path is None:
        st.warning(T(
            "Encrypted demo storage is unavailable; changes will not persist.",
            "التخزين المشفّر غير متاح؛ لن تبقى التغييرات بعد إغلاق الجلسة.",
        ))

_current_page = st.session_state.get("page", "dashboard")
if _current_page not in _PAGE_PERMISSIONS:
    _current_page = "dashboard"
    st.session_state["page"] = _current_page

_page_permission = _PAGE_PERMISSIONS[_current_page]
if not has_permission(st.session_state.get("active_role"), _page_permission):
    _deny_page(_page_permission)
    _current_page = "denied"

# ===========================================================================
if _current_page == "dashboard":
    # UI — Main content
    # ===========================================================================

    # ── Top bar ──────────────────────────────────────────────────────────────
    _today_fmt = date.today().strftime("%A, %d %B %Y")
    if _IS_AR:
        _days_map = {"Monday":"الاثنين","Tuesday":"الثلاثاء","Wednesday":"الأربعاء",
                     "Thursday":"الخميس","Friday":"الجمعة","Saturday":"السبت","Sunday":"الأحد"}
        _mon_map  = {"January":"يناير","February":"فبراير","March":"مارس","April":"أبريل",
                     "May":"مايو","June":"يونيو","July":"يوليو","August":"أغسطس",
                     "September":"سبتمبر","October":"أكتوبر","November":"نوفمبر","December":"ديسمبر"}
        for _en, _ar in {**_days_map, **_mon_map}.items():
            _today_fmt = _today_fmt.replace(_en, _ar)

    _topbar_dir = "rtl" if _IS_AR else "ltr"
    st.markdown(f"""
    <div class="sf-topbar" style="direction:{_topbar_dir};">
      <div class="sf-topbar-date">📅 {_today_fmt}</div>
      <div class="sf-topbar-actions">
        <div class="sf-topbar-icon">❓</div>
        <div class="sf-topbar-icon">🔔</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Hero Banner ───────────────────────────────────────────────────────────
    _hero_greeting = T("👋 Welcome to", "👋 مرحبًا بك في")
    _hero_subtitle  = T(
        "Transform your student data into actionable insights,<br>"
        "smart reports, and effective parent communication.",
        "حوّل بيانات طلابك إلى رؤى عملية، وتقارير ذكية،<br>وتواصل فعّال مع أولياء الأمور."
    )
    _hero_dir = "rtl" if _IS_AR else "ltr"
    st.markdown(f"""
    <div class="sf-hero" style="direction:{_hero_dir};">
      <div class="sf-hero-logo">
        <img src="{_LOGO_DATA_URI}" alt="SchoolFlow AI" />
      </div>
      <div class="sf-hero-text">
        <div class="sf-hero-greeting">{_hero_greeting}</div>
        <div class="sf-hero-subtitle">{_hero_subtitle}</div>
      </div>
      <div class="sf-hero-badge">
        <div class="sf-hero-badge-icon">📚</div>
        <div class="sf-hero-badge-text">MVP v0.1</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Privacy notice ────────────────────────────────────────────────────────
    _priv_title = T("Privacy Notice", "تنبيه الخصوصية")
    if _shared_demo:
        _priv_body = T(
            "Use synthetic data only; uploads are disabled.",
            "استخدم بيانات اصطناعية فقط؛ رفع الملفات متوقف.",
        )
    else:
        _priv_body = T(
            "Start with sample or authorised data. Do not upload real student data "
            "without school consent and approved privacy controls.",
            "ابدأ ببيانات تجريبية أو بيانات مصرح باستخدامها. "
            "لا ترفع بيانات طلاب حقيقية قبل موافقة المدرسة واعتماد ضوابط الخصوصية."
        )
    _priv_dir = "rtl" if _IS_AR else "ltr"
    st.markdown(f"""
    <div style="background:#1A3A61;border:1px solid rgba(212,160,23,0.45);
                border-right:4px solid #D4A017;border-radius:9px;
                padding:0.6rem 1rem;font-size:0.82rem;color:#FFFFFF;
                margin-bottom:1.2rem;direction:{_priv_dir};display:flex;gap:0.5rem;align-items:flex-start;">
      <span>⚠️</span>
      <span><strong>{_priv_title}:</strong> {_priv_body}</span>
    </div>
    """, unsafe_allow_html=True)

    if _cloud_context is None and "summary" not in st.session_state and not any(
        st.session_state.get(key) for key in (
            "lesson_draft", "lesson_records", "participation_log",
            "skill_definitions", "skill_assessments", "interventions",
            "intervention_checkpoints", "question_library",
        )
    ):
        if st.button(
            T("Load synthetic demo data", "تحميل بيانات عرض اصطناعية"),
            key="load_synthetic_demo",
        ):
            _demo_rows = pd.DataFrame([
                {"Student code": code, "Student name": name, "Week": week,
                 "Days scheduled": 5, "Days attended": attended,
                 "Tasks set": 4, "Tasks completed": tasks,
                 "Quiz score / 10": score, "Observation": "Synthetic example",
                 "Next step": "Review"}
                for code, name, week, attended, tasks, score in (
                    ("DEMO-01", "Demo Student A", 1, 5, 4, 8),
                    ("DEMO-01", "Demo Student A", 2, 4, 3, 7),
                    ("DEMO-02", "Demo Student B", 1, 4, 2, 6),
                    ("DEMO-02", "Demo Student B", 2, 5, 3, 7),
                )
            ])
            _demo_issues = validate(_demo_rows)
            if not _demo_issues.empty and _demo_issues["Blocking"].any():
                st.error(T("Synthetic demo data is invalid.", "بيانات العرض الاصطناعية غير صالحة."))
                st.stop()
            _demo_clean, _demo_summary, _demo_weekly = build_outputs(_demo_rows, True)
            st.session_state["source_rows"] = _demo_rows
            st.session_state["clean"] = _demo_clean
            st.session_state["summary"] = _demo_summary
            st.session_state["weekly"] = _demo_weekly
            st.session_state["has_name"] = True
            st.session_state["issues"] = _demo_issues
            st.rerun()

    # ── KPI cards (dynamic after analysis, placeholder before) ────────────────
    if "summary" in st.session_state:
        _sum  = st.session_state["summary"]
        _cln  = st.session_state["clean"]
        _n_s  = len(_sum)
        _n_w  = int(_cln["Week"].nunique())
        _n_r  = len(_cln)
        # Compute aggregate rates
        def _avg_pct(col):
            vals = []
            for v in _sum[col]:
                try:
                    vals.append(float(str(v).replace("%","").strip()))
                except Exception:
                    pass
            return f"{sum(vals)/len(vals):.1f}%" if vals else "N/A"
        _att_avg  = _avg_pct("Attendance")
        _task_avg = _avg_pct("Task completion")
        _scores   = _sum["Mean quiz / 10"].dropna()
        _quiz_avg = f"{_scores.mean():.1f} / 10" if len(_scores) else "N/A"
    else:
        _n_s = "—"; _n_w = "—"; _n_r = "—"
        _att_avg = "—"; _task_avg = "—"; _quiz_avg = "—"

    _kpi_dir = "rtl" if _IS_AR else "ltr"
    st.markdown(f"""
    <div class="sf-metrics-row" style="direction:{_kpi_dir};">
      <div class="sf-metric-card">
        <div class="sf-metric-icon sf-icon-green">👥</div>
        <div class="sf-metric-body">
          <div class="sf-metric-label">{T("Students","عدد الطلاب")}</div>
          <div class="sf-metric-value">{_n_s}</div>
          <div class="sf-metric-sub">{T(f"Total records: {_n_r}", f"إجمالي السجلات: {_n_r}")}</div>
        </div>
      </div>
      <div class="sf-metric-card">
        <div class="sf-metric-icon sf-icon-blue">📅</div>
        <div class="sf-metric-body">
          <div class="sf-metric-label">{T("Attendance Rate","نسبة الحضور")}</div>
          <div class="sf-metric-value">{_att_avg}</div>
          <div class="sf-metric-sub">{T(f"Class avg · {_n_w} weeks", f"متوسط الفصل · {_n_w} أسبوع")}</div>
        </div>
      </div>
      <div class="sf-metric-card">
        <div class="sf-metric-icon sf-icon-gold">✅</div>
        <div class="sf-metric-body">
          <div class="sf-metric-label">{T("Task Completion","إنجاز المهام")}</div>
          <div class="sf-metric-value">{_task_avg}</div>
          <div class="sf-metric-sub">{T("Whole-class average","متوسط الفصل الكامل")}</div>
        </div>
      </div>
      <div class="sf-metric-card">
        <div class="sf-metric-icon sf-icon-purple">🏆</div>
        <div class="sf-metric-body">
          <div class="sf-metric-label">{T("Mean Quiz Score","متوسط الاختبارات")}</div>
          <div class="sf-metric-value">{_quiz_avg}</div>
          <div class="sf-metric-sub">{T("Recorded scores average","معدّل الدرجات المسجّلة")}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Dashboard: weekly chart + observations (only when data is ready) ──────
    if "summary" in st.session_state:
        clean    = st.session_state["clean"]
        summary  = st.session_state["summary"]
        weekly   = st.session_state["weekly"]
        has_name = st.session_state.get("has_name", False)
        issues_stored = st.session_state.get("issues", pd.DataFrame())

        # Build SVG chart
        svg_chart = _build_weekly_svg(weekly, arabic=_IS_AR)

        # Observations HTML
        if issues_stored.empty:
            obs_html = f'<div class="sf-obs-empty">✅ {T("No issues — all data is clean","لا توجد ملاحظات — البيانات سليمة")}</div>'
        else:
            rows_html = ""
            for _, r in issues_stored.iterrows():
                rows_html += (
                    f'<div class="sf-obs-item">'
                    f'<span class="sf-obs-code">{escape_html(r["Student code"])}</span>'
                    f'<span class="sf-obs-text">{escape_html(r["Week"])}: '
                    f'{escape_html(r["Issue"])}</span>'
                    f'</div>'
                )
            obs_html = rows_html

        _dash_dir = "rtl" if _IS_AR else "ltr"
        _chart_title = T("Weekly Class Performance","تطور الأداء الأسبوعي للفصل")
        _obs_title   = T("Key Observations","أبرز الملاحظات")
        st.markdown(f"""
        <div class="sf-card" style="max-width:760px;margin:0 auto 0.75rem;
                                    padding:0.9rem 1.1rem;direction:{_dash_dir};">
          <div class="sf-card-header" style="margin-bottom:0.45rem;padding-bottom:0.45rem;">
            <div class="sf-card-header-icon">📊</div>
            <div class="sf-card-title">{_chart_title}</div>
          </div>
          <div style="max-width:560px;margin:0 auto;">{svg_chart}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(_obs_title, expanded=False):
            st.markdown(obs_html, unsafe_allow_html=True)

        # Quick actions row
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            st.button(
                T("📋 Student Reports", "📋 عرض تقارير الطلاب"),
                key="dashboard_reports",
                **full_width(),
                on_click=_navigate_to,
                args=("reports",),
            )
        with col_q2:
            st.button(
                T("✉ Parent Messages", "✉ رسائل أولياء الأمور"),
                key="dashboard_messages",
                **full_width(),
                on_click=_navigate_to,
                args=("messages",),
            )
        with col_q3:
            st.button(
                T("📤 Upload New File", "📤 رفع ملف جديد"),
                key="dashboard_upload",
                **full_width(),
                on_click=_navigate_to,
                args=("upload",),
            )

        st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)

    # ===========================================================================
if _current_page == "upload":
    # UI — Step 1: Upload
    # ===========================================================================
    _sec1_title = T(
        "Upload Student Tracking File",
        "رفع ملف متابعة الطلاب"
    )
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">1</div>
      <div class="sf-section-title">{_sec1_title}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sf-upload-area">', unsafe_allow_html=True)
    if _shared_demo:
        uploaded = None
        st.info(T(
            "File uploads are disabled in the shared demo. Add, edit or remove synthetic rows below.",
            "رفع الملفات متوقف في العرض المشترك. أضف الصفوف الاصطناعية أو عدّلها أو احذفها أدناه.",
        ))
        st.caption(T(
            "Use synthetic data only. Applying changes updates reports, but does not erase "
            "previous lesson records. End an active lesson before changing student data.",
            "استخدم بيانات اصطناعية فقط. تحديث الصفوف يحدّث التقارير، لكنه لا يحذف "
            "سجلات الحصص السابقة. أنهِ الحصة النشطة قبل تغيير بيانات الطلاب.",
        ))
        _demo_editor_notice = st.session_state.pop("_demo_editor_notice", None)
        if _demo_editor_notice:
            st.success(_demo_editor_notice)
        _demo_columns = REQUIRED + [OPTIONAL_NAME_COL]
        if "source_rows" in st.session_state:
            _demo_rows = st.session_state["source_rows"].copy()
            if OPTIONAL_NAME_COL not in _demo_rows:
                _demo_rows[OPTIONAL_NAME_COL] = ""
            _demo_rows = _demo_rows[_demo_columns]
        else:
            _demo_rows = pd.DataFrame({
                col: pd.Series(dtype="float64" if col in NUMERIC_COLS else "str")
                for col in _demo_columns
            })
        with st.form("synthetic_data_editor_form"):
            _edited_demo_rows = st.data_editor(
                _demo_rows,
                num_rows="dynamic",
                hide_index=True,
                key=f"synthetic_data_editor_{st.session_state.get('_demo_editor_revision', 0)}",
                **full_width(),
            )
            _apply_demo_rows = st.form_submit_button(
                T("Apply synthetic data", "تطبيق البيانات الاصطناعية"),
                disabled=st.session_state.get("lesson_active", False),
            )
        if st.session_state.get("lesson_active", False):
            st.warning(T(
                "End the current lesson before applying student data changes.",
                "أنه الحصة الحالية قبل تطبيق تغييرات بيانات الطلاب.",
            ))
        if _apply_demo_rows:
            _edited_demo_rows = _edited_demo_rows.dropna(how="all").reset_index(drop=True)
            if _edited_demo_rows.empty:
                for _key in ("source_rows", "clean", "summary", "weekly", "has_name", "issues"):
                    st.session_state.pop(_key, None)
            else:
                _demo_issues = validate(_edited_demo_rows)
                if not _demo_issues.empty and _demo_issues["Blocking"].any():
                    st.error(T(
                        "Correct invalid or duplicate rows before applying changes.",
                        "صحّح الصفوف غير الصالحة أو المكررة قبل تطبيق التغييرات.",
                    ))
                    st.dataframe(
                        _localized_dataframe(_demo_issues.drop(columns=["Blocking"])),
                        **full_width(), hide_index=True,
                    )
                    st.stop()
                _demo_clean, _demo_summary, _demo_weekly = build_outputs(_edited_demo_rows, True)
                st.session_state["source_rows"] = _edited_demo_rows.copy()
                st.session_state["clean"] = _demo_clean
                st.session_state["summary"] = _demo_summary
                st.session_state["weekly"] = _demo_weekly
                st.session_state["has_name"] = True
                st.session_state["issues"] = _demo_issues
            st.session_state["_demo_editor_revision"] = st.session_state.get("_demo_editor_revision", 0) + 1
            st.session_state["_demo_editor_notice"] = T(
                "Synthetic data updated in this session.", "حُدّثت البيانات الاصطناعية في هذه الجلسة."
            )
            st.rerun()
    else:
        uploaded = st.file_uploader(
            T("Drag and drop an Excel file (.xlsx) here, or click to choose",
              "اسحب ملف Excel (.xlsx) وأفلته هنا، أو انقر للاختيار"),
            type=["xlsx"],
            label_visibility="visible",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    if uploaded:
        try:
            xls = pd.ExcelFile(fresh_bytes(uploaded))
        except Exception as e:
            st.error(T(f"Could not open file: {e}", f"تعذر فتح الملف: {e}"))
            st.stop()

        col_sheet, col_info = st.columns([2, 3])
        with col_sheet:
            default_idx = xls.sheet_names.index("Weekly tracking") if "Weekly tracking" in xls.sheet_names else 0
            sheet = st.selectbox(
                T("📋 Select data sheet", "📋 اختر ورقة البيانات"),
                xls.sheet_names, index=default_idx,
            )
        with col_info:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption(T(f"Available sheets: {', '.join(xls.sheet_names)}",
                         f"الأوراق المتاحة: {', '.join(xls.sheet_names)}"))

        try:
            raw = pd.read_excel(fresh_bytes(uploaded), sheet_name=sheet, header=4)
        except Exception as e:
            st.error(T(f"Could not read sheet: {e}", f"تعذر قراءة الورقة: {e}"))
            st.stop()

        raw.columns = [str(c).strip() for c in raw.columns]
        missing_cols = [c for c in REQUIRED if c not in raw.columns]
        has_name = OPTIONAL_NAME_COL in raw.columns

        if missing_cols:
            st.error(
                T("The following columns are missing: ", "الأعمدة التالية غير موجودة في الملف: ")
                + ", ".join(missing_cols)
            )
            st.write(T("Columns found:", "الأعمدة التي وجدناها:"), list(raw.columns))
            st.stop()

        cols_to_load = REQUIRED + ([OPTIONAL_NAME_COL] if has_name else [])
        data = raw[cols_to_load].dropna(how="all")

        name_status = (
            T("✓ Name column present", "✓ عمود الاسم موجود")
            if has_name else
            T("Student code will be used", "سيُستخدم رمز الطالب")
        )
        st.markdown(
            f'<span class="sf-pill-ok">✓ {T(f"Loaded {len(data)} records from", f"تمت القراءة — {len(data)} سجل من")} '
            f'"{escape_html(sheet)}" · {name_status}</span>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander(T("👁 Preview first 10 records", "👁 معاينة أول 10 سجلات"), expanded=False):
            st.dataframe(data.head(10), **full_width(), hide_index=True)

        # -----------------------------------------------------------------------
        # Step 2 – Validation
        # -----------------------------------------------------------------------
        _sec2_title = T(
            "Data Quality Check",
            "مراجعة جودة البيانات"
        )
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">2</div>
          <div class="sf-section-title">{_sec2_title}</div>
        </div>
        """, unsafe_allow_html=True)

        issues = validate(data)
        blocking_issues = not issues.empty and issues["Blocking"].any()
        if issues.empty:
            st.markdown(
                f'<span class="sf-pill-ok">✓ {T("No issues — all required values present and valid","لا توجد مشكلات — جميع القيم المطلوبة موجودة ومنطقية")}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="sf-pill-warn">⚠ {T(f"{len(issues)} data issues found — review before continuing", f"وُجدت {len(issues)} مشكلة في البيانات — راجعها قبل المتابعة")}</span>',
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="sf-card">', unsafe_allow_html=True)
            st.dataframe(_localized_dataframe(issues.drop(columns=["Blocking"])), **full_width(), hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption(
                T(
                    "Note: rows with issues are NOT removed automatically. "
                    "Zero (0) ≠ missing (blank). Fix data in Excel first if needed.",
                    "ملاحظة: الصفوف التي بها مشكلات لن تُحذف تلقائيًا. "
                    "قيمة صفر (0) ≠ قيمة مفقودة (فارغة). "
                    "راجع البيانات في Excel أولاً إذا أردت تصحيحها."
                )
            )

        if blocking_issues:
            st.error(T(
                "Correct the invalid or duplicate records in Excel before analysing or importing.",
                "صحّح السجلات غير الصالحة أو المكررة في ملف Excel قبل التحليل أو الاستيراد.",
            ))
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(T("⚡  Analyse Data & Generate Reports", "⚡  تحليل البيانات وإنشاء التقارير"), type="primary", disabled=blocking_issues):
            clean, summary, weekly = build_outputs(data, has_name)
            st.session_state["source_rows"] = data.copy()
            st.session_state["_cloud_import_requested"] = True
            st.session_state["clean"]    = clean
            st.session_state["summary"]  = summary
            st.session_state["weekly"]   = weekly
            st.session_state["has_name"] = has_name
            st.session_state["issues"]   = issues   # store for dashboard
            # Both events follow successful processing; neither includes row data.
            _role_for_audit = st.session_state.get("active_role", "unknown")
            if _role_for_audit not in ALL_ROLES:
                _role_for_audit = "unknown"
            _audit_log = st.session_state.get("audit_log", [])
            _audit_log = log_event(
                _audit_log,
                action=ACTION_DATA_IMPORT,
                actor_role=_role_for_audit,
                entity_type=ENTITY_DATA_FILE,
            )
            st.session_state["audit_log"] = log_event(
                _audit_log,
                action=ACTION_REPORT_GENERATED,
                actor_role=_role_for_audit,
                entity_type=ENTITY_REPORT,
            )
            st.session_state["page"] = "analysis"
            if _sync_cloud_workspace_if_dirty():
                st.success(T("✅  Analysis complete. Review results below.", "✅  اكتمل التحليل بنجاح. راجع النتائج أدناه."))
                st.rerun()

    # ===========================================================================
if _current_page == "reports":
    # UI — Steps 3–8: Results
    # ===========================================================================

    if "summary" in st.session_state:
        clean    = st.session_state["clean"]
        summary  = st.session_state["summary"]
        weekly   = st.session_state["weekly"]
        has_name = st.session_state.get("has_name", False)

        st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)

        # Step 3 – Teacher overview
        _s3 = T("Teacher Dashboard", "ملخص المعلم")
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">3</div>
          <div class="sf-section-title">{_s3}</div>
        </div>
        """, unsafe_allow_html=True)

        # Step 4 – Weekly summary
        _s4 = T("Weekly Class Summary", "الملخص الأسبوعي للفصل")
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">4</div>
          <div class="sf-section-title">{_s4}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(_localized_dataframe(weekly), **full_width(), hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Step 5 – Student summary
        _s5 = T("Student Summary", "ملخص كل طالب")
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">5</div>
          <div class="sf-section-title">{_s5}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(_localized_dataframe(summary), **full_width(), hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Step 6 – Per-student drill-down
        _s6 = T("Student Weekly Drill-Down", "تفاصيل أسبوعية لطالب محدد")
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">6</div>
          <div class="sf-section-title">{_s6}</div>
        </div>
        """, unsafe_allow_html=True)

        student_options = summary["Student code"].tolist()
        if has_name:
            label_map = dict(zip(summary["Student code"], summary["Student name"]))
            student_options_labels = [f"{c} — {label_map[c]}" for c in student_options]
        else:
            student_options_labels = student_options

        selected_label = st.selectbox(T("🎓 Select student", "🎓 اختر الطالب"), student_options_labels)
        selected_code  = student_options[student_options_labels.index(selected_label)]
        student_rows   = clean[clean["Student code"] == selected_code].sort_values("Week")
        detail_cols    = ["Week", "Days scheduled", "Days attended",
                          "Tasks set", "Tasks completed", "Quiz score / 10",
                          "Observation", "Next step"]
        if has_name and OPTIONAL_NAME_COL in student_rows.columns:
            detail_cols = [OPTIONAL_NAME_COL] + detail_cols

        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(
            _localized_dataframe(student_rows[detail_cols]),
            **full_width(),
            hide_index=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # Step 8 – Download
        _s8 = T("Download Reports", "تنزيل النتائج")
        st.markdown(f"""
        <div class="sf-section-header">
          <div class="sf-section-num">8</div>
          <div class="sf-section-title">{_s8}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        col_dl, col_note = st.columns([2, 4])
        with col_dl:
            workbook = make_workbook(clean, summary, weekly)
            st.download_button(
                T("📥  Download Excel Reports File","📥  تنزيل ملف التقارير Excel"),
                data=workbook,
                file_name="SchoolFlow_AI_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                on_click=_audit_report_download,
            )
        with col_note:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption(
                T("File contains 3 sheets: Validated data · Student summaries · Weekly summary",
                  "الملف يحتوي على 3 أوراق: البيانات المُتحقق منها · ملخص الطلاب · الملخص الأسبوعي")
            )
        st.markdown('</div>', unsafe_allow_html=True)

        st.caption(
            T(
                "This is an early version: no automatic messaging, no replacement for teacher review. "
                "Verify data accuracy and message templates with your school before use.",
                "هذه نسخة أولية: لا ترسل رسائل تلقائيًا، ولا تستبدل مراجعة المعلم. "
                "يجب التحقق من دقة البيانات والقوالب مع المدرسة قبل اعتمادها."
            )
        )

    # ===========================================================================
    else:
        st.info(T(
            "Upload and analyse a workbook before opening student reports.",
            "ارفع ملفًا وحلّله قبل فتح تقارير الطلاب.",
        ))

# Performance Analysis page
if _current_page == "analysis":
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">📊</div>
          <div class="sf-section-title">
            {T("Performance Analysis", "تحليل الأداء")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if "summary" not in st.session_state:
        st.info(T(
            "Upload and analyse a workbook to view class performance.",
            "ارفع ملفًا وحلّله لعرض أداء الفصل.",
        ))
    else:
        summary = st.session_state["summary"]
        weekly = st.session_state["weekly"]
        attendance_values = [
            parse_percentage(value)
            for value in weekly.get("Attendance rate", [])
        ]
        task_values = [
            parse_percentage(value)
            for value in weekly.get("Task completion", [])
        ]
        metric_cols = st.columns(3)
        metric_cols[0].metric(T("Students", "الطلاب"), f"{len(summary)}")
        metric_cols[1].metric(
            T("Weeks analysed", "الأسابيع المحللة"), f"{len(weekly)}"
        )
        metric_cols[2].metric(
            T("Average attendance", "متوسط الحضور"),
            f"{sum(attendance_values) / len(attendance_values):.1f}%"
            if attendance_values else "—",
        )
        st.markdown(
            f"**{T('Weekly class trends', 'اتجاهات أداء الفصل أسبوعيًا')}**"
        )
        st.dataframe(
            _localized_dataframe(weekly),
            **full_width(),
            hide_index=True,
        )
        if task_values:
            st.caption(T(
                f"Average task completion: {sum(task_values) / len(task_values):.1f}%.",
                f"متوسط إنجاز المهام: {sum(task_values) / len(task_values):.1f}%.",
            ))
        workbook = make_workbook(st.session_state["clean"], summary, weekly)
        st.download_button(
            T("📥 Export Excel Report", "📥 تصدير تقرير Excel"),
            data=workbook,
            file_name="SchoolFlow_AI_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            on_click=_audit_report_download,
        )

# Parent Messages page
if _current_page == "messages":
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">✉</div>
          <div class="sf-section-title">
            {T("Parent Messages", "رسائل أولياء الأمور")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if "summary" not in st.session_state:
        st.info(T(
            "Upload and analyse a workbook before preparing parent messages.",
            "ارفع ملفًا وحلّله قبل إعداد رسائل أولياء الأمور.",
        ))
    else:
        summary = st.session_state["summary"]
        has_name = st.session_state.get("has_name", False)

        col_lang, _ = st.columns([2, 4])
        with col_lang:
            language = st.radio(T("🌐 Message language", "🌐 لغة الرسالة"), ["English", "العربية"], horizontal=True)

        st.markdown("<br>", unsafe_allow_html=True)

        for _, row in summary.iterrows():
            label = row["Student name"] if has_name else row["Student code"]
            _exp_label = T(f"✉  Message for: {label}", f"✉  رسالة الطالب: {label}")
            with st.expander(_exp_label):
                st.text_area(
                    T("Review before sending", "راجع الرسالة قبل إرسالها"),
                    parent_message(row, language),
                    height=210,
                    key=f"msg_{row['Student code']}_{language}",
                )

if _current_page == "settings":
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">⚙</div>
          <div class="sf-section-title">
            {T("Project Settings", "إعدادات المشروع")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    settings_cols = st.columns(3)
    settings_cols[0].metric(
        T("Interface language", "لغة الواجهة"),
        T("Arabic", "العربية") if _IS_AR else T("English", "الإنجليزية"),
    )
    settings_cols[1].metric(
        T("Online AI", "الذكاء الاصطناعي عبر الإنترنت"),
        T("Gemini on request", "Gemini عند الطلب") if _shared_demo else
        T("On", "مفعّل")
        if st.session_state.get("online_ai_enabled")
        else T("Off", "متوقف"),
    )
    settings_cols[2].metric(
        T("Storage", "التخزين"),
        T("Cloud", "سحابي") if _cloud_context else
        T("Encrypted on request", "مشفّر عند الحفظ") if _demo_path is not None else
        T("Session only", "للجلسة فقط"),
    )
    st.info(T(
        "Change language and Online AI from the controls in the sidebar. Cloud mode uses your authenticated school membership.",
        "غيّر اللغة والذكاء الاصطناعي من عناصر التحكم في الشريط الجانبي. يستخدم الوضع السحابي عضوية المدرسة الموثقة.",
    ))

if _current_page == "assistant":
    # UI — SchoolFlow AI Assistant (Section 9)
    # ===========================================================================
    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
    _s9_title = T("SchoolFlow AI Assistant", "مساعد SchoolFlow AI")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">9</div>
      <div class="sf-section-title">{_s9_title}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Import assistant modules ─────────────────────────────────────────────
    import sys as _sys, os as _os
    _assistant_dir = _os.path.dirname(__file__)
    if _assistant_dir not in _sys.path:
        _sys.path.insert(0, _assistant_dir)

    _ASSISTANT_ERR = ""   # safe default; overwritten only if import fails
    try:
        from assistant.intent_router import route as _route
        from assistant.llm_client import get_mode as _get_mode
        _ASSISTANT_READY = True
    except Exception:
        _ASSISTANT_READY = False
        _ASSISTANT_ERR = T("Assistant module unavailable.", "وحدة المساعد غير متاحة.")

    # ── Session state for chat ───────────────────────────────────────────────
    # "chat_history" and "assistant_mode" are guaranteed by init_state() above

    # ── Mode indicator ────────────────────────────────────────────────────────
    if _ASSISTANT_READY:
        _mode = _get_mode()
        _user_ai_on = st.session_state.get("online_ai_enabled", False)
        _effective_mode = _mode if _user_ai_on else "offline"
        st.session_state["assistant_mode"] = _effective_mode
        if _effective_mode == "online":
            _mode_txt = T(
                "● OpenAI configured and enabled — connection not yet verified",
                "● إعداد OpenAI مفعّل — لم يُتحقق من الاتصال بعد"
            )
        elif _user_ai_on:
            _mode_txt = T(
                "● Online AI unavailable — configure the OpenAI key and package",
                "● الذكاء الاصطناعي غير متاح — يلزم إعداد مفتاح OpenAI والحزمة"
            )
        elif _mode == "online" and not _user_ai_on:
            _mode_txt = T(
                "● API key configured — Online AI disabled by user",
                "● مفتاح API مُهيَّأ — الذكاء الاصطناعي معطَّل من قِبَل المستخدم"
            )
        else:
            _mode_txt = T(
                "● Offline Mode — rule-based responses only",
                "● وضع محلي — ردود قائمة على القواعد فقط"
            )
    else:
        _mode_txt = T("● Assistant load error", "● خطأ في تحميل المساعد")

    # ── Assistant header ──────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:{PRIMARY_NAVY};
                border-radius:12px 12px 0 0;padding:0.7rem 1.2rem;
                display:flex;align-items:center;gap:0.6rem;
                direction:{'rtl' if _IS_AR else 'ltr'};">
      <span style="font-size:1.2rem;">🤖</span>
      <div>
        <div style="color:#FFFFFF;font-weight:700;font-size:0.95rem;">SchoolFlow AI Assistant</div>
        <div style="font-size:0.72rem;color:rgba(255,255,255,0.75);">{_mode_txt}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if _shared_demo and _ASSISTANT_READY:
        from assistant.synthetic_ai import TEMPLATES, generate_synthetic_template

        st.caption(T(
            "Gemini sends only the selected fixed synthetic example, not your chat or class data. "
            "A configured key does not prove a connection. Requests may incur charges.",
            "يرسل Gemini المثال الاصطناعي الثابت المختار فقط، دون المحادثة أو بيانات الفصل. "
            "إعداد المفتاح لا يثبت الاتصال. قد تترتب رسوم على الطلبات.",
        ))
        _template_labels = {
            "lesson": T("Synthetic lesson plan", "خطة حصة اصطناعية"),
            "bloom": T("Synthetic Bloom questions", "أسئلة بلوم اصطناعية"),
            "gagne": T("Synthetic Gagne events", "أحداث غانييه اصطناعية"),
        }
        _template_id = st.selectbox(
            T("Gemini example", "مثال Gemini"),
            options=list(TEMPLATES),
            format_func=lambda value: _template_labels[value],
            key="gemini_template",
        )
        if st.button(T("Request Gemini example", "طلب مثال من Gemini"), key="request_gemini"):
            try:
                _gemini_response = generate_synthetic_template(_template_id)
            except RuntimeError as _gemini_error:
                _gemini_errors = {
                    "no_key": T("Gemini key is not configured.", "مفتاح Gemini غير مُهيّأ."),
                    "no_package": T("Gemini package is not installed.", "حزمة Gemini غير مثبتة."),
                    "bad_key": T("Gemini rejected the credentials.", "رفض Gemini بيانات الاتصال."),
                    "rate_limit": T("Gemini request limit reached.", "تم بلوغ حد طلبات Gemini."),
                    "local_rate_limit": T("Local Gemini request limit reached.", "تم بلوغ الحد المحلي لطلبات Gemini."),
                    "quota_unavailable": T("Cannot verify the local request limit.", "تعذّر التحقق من حد الطلبات المحلي."),
                    "connection_error": T("Could not connect to Gemini.", "تعذّر الاتصال بـGemini."),
                    "empty_response": T("Gemini returned an empty response.", "أعاد Gemini ردًا فارغًا."),
                }
                st.error(_gemini_errors.get(str(_gemini_error), T(
                    "The Gemini request failed.", "فشل طلب Gemini.",
                )))
            else:
                st.session_state["chat_history"].append({
                    "role": "bot", "content": f"Gemini:\n\n{_gemini_response}",
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                st.rerun()

    # ── Chat history (native st.chat_message — no DOM conflict) ──────────────
    _chat_container = st.container()
    with _chat_container:
        history = st.session_state["chat_history"]
        if not history:
            with st.chat_message("assistant"):
                st.markdown(
                    T(
                        "Hello! I'm SchoolFlow AI Assistant 🎓\n\n"
                        "Upload your data file first, then ask me about student performance.\n\n"
                        "Available commands:\n\n**help**",
                        "مرحبًا! أنا مساعد SchoolFlow AI 🎓\n\n"
                        "ارفع ملف البيانات أولاً ثم اسألني عن أداء الطلاب.\n\n"
                        "الأوامر المتاحة:\n\n**مساعدة**"
                    )
                )
        else:
            for _msg in history:
                _role    = _msg.get("role", "bot")
                _content = _msg.get("content", "")
                _ts_str  = _msg.get("ts", "")
                _st_role = "user" if _role == "user" else "assistant"
                with st.chat_message(_st_role):
                    st.markdown(_content)
                    if _ts_str:
                        if len(_ts_str) == 5 and _ts_str[2] == ":":
                            _ts_display = T(
                                f"Legacy local time: {_ts_str}",
                                f"وقت محلي قديم: {_ts_str}",
                            )
                        else:
                            _ts_display = format_timestamp_riyadh(
                                _ts_str, include_date=False
                            )
                        st.caption(_ts_display)

    # ── Clear button ─────────────────────────────────────────────────────────
    if st.session_state["chat_history"]:
        if st.button(T("🗑 Clear chat", "🗑 مسح المحادثة"), key="clear_chat"):
            st.session_state["chat_history"] = []
            st.rerun()

    # ── Quick-command chips ──────────────────────────────────────────────────
    _chip_label = T("Quick commands:", "أوامر سريعة:")
    st.markdown(
        f'<div style="direction:{"rtl" if _IS_AR else "ltr"};margin:0.5rem 0 0.4rem;">'
        f'<span style="font-size:0.78rem;color:#405D75;font-weight:600;">{_chip_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Bilingual chip pairs — (english_command, arabic_command, display_label)
    _chips_def = [
        ("class analysis",        "تحليل الفصل",         T("Class Analysis",    "تحليل الفصل")),
        ("show at-risk students", "من يحتاج متابعة؟",    T("At-Risk Students",  "من يحتاج متابعة؟")),
        ("data issues",           "مشكلات البيانات",      T("Data Issues",       "مشكلات البيانات")),
        ("list students",         "قائمة الطلاب",         T("List Students",     "قائمة الطلاب")),
        ("explain",               "اشرح النتائج",         T("Explain Results",   "اشرح النتائج")),
        ("help",                  "مساعدة",                T("Help",              "مساعدة")),
    ]
    for _row_start in range(0, len(_chips_def), 3):
        _chip_cols = st.columns(3)
        for _col_idx in range(3):
            _i = _row_start + _col_idx
            if _i >= len(_chips_def):
                continue
            _cmd_en, _cmd_ar, _label = _chips_def[_i]
            _visual_col = 2 - _col_idx if _IS_AR else _col_idx
            with _chip_cols[_visual_col]:
                if st.button(_label, key=f"chip_{_i}", **full_width()):
                    _ts2 = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    _chip = _cmd_ar   # always send Arabic command to the router (patterns cover both)
                    st.session_state["chat_history"].append(
                        {"role": "user", "content": _label, "ts": _ts2}
                    )
                    if _ASSISTANT_READY:
                        try:
                            _r = _route(
                                _chip, lang=_L,
                                online_ai_enabled=st.session_state.get("online_ai_enabled", False),
                            )
                            st.session_state["chat_history"].append(
                                {"role": "bot" if _r.get("ok") else "error",
                                 "content": _r.get("response", ""), "ts": _ts2}
                            )
                        except Exception:
                            st.session_state["chat_history"].append(
                                {"role": "error", "content": T(
                                    "An unexpected assistant error occurred.",
                                    "حدث خطأ غير متوقع في المساعد.",
                                ), "ts": _ts2}
                            )
                    st.rerun()

    # ── Chat input (native Streamlit — React-safe) ────────────────────────────
    _placeholder = T(
        "Example: report S01 | at-risk students | help",
        "مثال: تقرير S01 | من يحتاج متابعة؟ | مساعدة",
    )
    _user_msg = st.chat_input(_placeholder)

    if _user_msg and _user_msg.strip():
        _ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        st.session_state["chat_history"].append({
            "role": "user", "content": _user_msg.strip(), "ts": _ts,
        })

        if not _ASSISTANT_READY:
            _bot_text = T(f"⚠️ Assistant failed to load: {_ASSISTANT_ERR}",
                          f"⚠️ تعذر تحميل المساعد: {_ASSISTANT_ERR}")
            _bot_role = "error"
        else:
            try:
                _result   = _route(
                    _user_msg.strip(), lang=_L,
                    online_ai_enabled=st.session_state.get("online_ai_enabled", False),
                )
                _bot_text = _result.get("response", T("No response.", "لا توجد إجابة."))
                _bot_role = "bot" if _result.get("ok") else "error"
            except Exception:
                _bot_text = T("⚠️ Unexpected assistant error.", "⚠️ خطأ غير متوقع في المساعد.")
                _bot_role = "error"

        st.session_state["chat_history"].append({
            "role": _bot_role, "content": _bot_text, "ts": _ts,
        })
        st.rerun()

# ===========================================================================
# UI — Lesson Workspace page (routed via sidebar nav)
# ===========================================================================
if _current_page == "lesson_workspace":
    if not has_permission(st.session_state.get("active_role"), USE_LESSON_WORKSPACE):
        _deny_page(USE_LESSON_WORKSPACE)
    else:
        _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
        _pages_dir = _os.path.join(_HERE_APP, "pages")
        if _pages_dir not in _sys.path:
            _sys.path.insert(0, _pages_dir)
        try:
            from pages.lesson_workspace import render as _lw_render
            _lw_render()
        except Exception as _lw_err:
            st.error(T(
                f"Could not load Lesson Workspace: {_lw_err}",
                f"تعذّر تحميل مساحة عمل الحصة: {_lw_err}",
            ))

# ===========================================================================
# UI — Student Profile page (routed via sidebar nav)
# ===========================================================================
if _current_page == "student_profile":
    if not has_permission(st.session_state.get("active_role"), VIEW_STUDENT_PROFILE):
        _deny_page(VIEW_STUDENT_PROFILE)
    else:
        _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
        _pages_dir = _os.path.join(_HERE_APP, "pages")
        if _pages_dir not in _sys.path:
            _sys.path.insert(0, _pages_dir)
        try:
            from pages.student_profile import render as _sp_render
            _sp_render()
        except Exception as _sp_err:
            st.error(T(
                f"Could not load Student Profile: {_sp_err}",
                f"تعذّر تحميل ملف الطالب: {_sp_err}",
            ))

# ===========================================================================
# UI — Academic Progress page (routed via sidebar nav)
# ===========================================================================
if _current_page == "academic_progress":
    if not has_permission(st.session_state.get("active_role"), VIEW_ACADEMIC_PROGRESS):
        _deny_page(VIEW_ACADEMIC_PROGRESS)
    else:
        _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
        _pages_dir = _os.path.join(_HERE_APP, "pages")
        if _pages_dir not in _sys.path:
            _sys.path.insert(0, _pages_dir)
        try:
            from pages.academic_progress import render as _ap_render
            _ap_render()
        except Exception as _ap_err:
            st.error(T(
                f"Could not load Academic Progress: {_ap_err}",
                f"تعذّر تحميل صفحة المهارات والتحصيل: {_ap_err}",
            ))

# ===========================================================================
# UI — Interventions page (routed via sidebar nav)
# ===========================================================================
if _current_page == "interventions":
    if not has_permission(st.session_state.get("active_role"), MANAGE_INTERVENTIONS):
        _deny_page(MANAGE_INTERVENTIONS)
    else:
        _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
        _pages_dir = _os.path.join(_HERE_APP, "pages")
        if _pages_dir not in _sys.path:
            _sys.path.insert(0, _pages_dir)
        try:
            from pages.interventions import render as _int_render
            _int_render()
        except Exception as _int_err:
            st.error(T(
                f"Could not load Interventions page: {_int_err}",
                f"تعذّر تحميل صفحة التدخلات: {_int_err}",
            ))

# ===========================================================================
# UI — Bloom Questions page (routed via sidebar nav)
# ===========================================================================
if _current_page == "bloom_questions":
    if not has_permission(st.session_state.get("active_role"), USE_BLOOM_QUESTIONS):
        _deny_page(USE_BLOOM_QUESTIONS)
    else:
        _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
        _pages_dir = _os.path.join(_HERE_APP, "pages")
        if _pages_dir not in _sys.path:
            _sys.path.insert(0, _pages_dir)
        try:
            from pages.bloom_questions import render as _bq_render
            _bq_render()
        except Exception as _bq_err:
            st.error(T(
                f"Could not load Bloom Questions page: {_bq_err}",
                f"تعذّر تحميل صفحة أسئلة بلوم: {_bq_err}",
            ))

# ===========================================================================
# UI — Admin Dashboard page (routed via sidebar nav — school_admin only)
# ===========================================================================
if _current_page == "admin_dashboard":
    if not has_permission(st.session_state.get("active_role"), VIEW_ADMIN_DASHBOARD):
        _deny_page(VIEW_ADMIN_DASHBOARD)
    else:
        # Inline admin dashboard — no separate page file needed for MVP
        st.markdown(
            f"""
            <div class="sf-section-header" style="direction:{_DIR};">
              <div class="sf-section-num">🏫</div>
              <div class="sf-section-title">
                {T("Admin Dashboard", "لوحة الإدارة")}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info(
            T(
                "School Admin view: class-wide summaries, teacher assignments, "
                "and cross-class interventions will be available here.",
                "عرض مدير المدرسة: ملخصات على مستوى المدرسة، إسناد المعلمين، "
                "والتدخلات عبر الفصول ستكون متاحة هنا.",
            )
        )
        _has_school_structure = False
        if _cloud_context is not None:
            try:
                load_teaching_assignments(_cloud_context["client"], _cloud_context["school_id"])
                _has_school_structure = True
            except APIError as _structure_probe_error:
                if _structure_probe_error.code != "PGRST202":
                    st.error(T(
                        f"Could not verify school structure: {_structure_probe_error}",
                        f"تعذّر التحقق من هيكل المدرسة: {_structure_probe_error}",
                    ))
                    st.stop()
                st.warning(T(
                    "The school structure schema is unavailable; existing class management is shown.",
                    "مخطط هيكل المدرسة غير متاح؛ تظهر إدارة الفصول الحالية.",
                ))
            except (HTTPError, ValueError) as _structure_probe_error:
                st.error(T(
                    f"Could not verify school structure: {_structure_probe_error}",
                    f"تعذّر التحقق من هيكل المدرسة: {_structure_probe_error}",
                ))
                st.stop()
        if _cloud_context is not None and _has_school_structure:
            try:
                from pages.school_structure import render as _structure_render
                _structure_render(_cloud_context["client"], _cloud_context["school_id"])
            except (APIError, HTTPError, ValueError) as _structure_error:
                st.error(T(
                    f"Could not load school structure: {_structure_error}",
                    f"تعذّر تحميل هيكل المدرسة: {_structure_error}",
                ))
        elif _cloud_context is not None:
            st.warning(T(
                "Class assignments are not yet enforced by database policies. "
                "Do not use real student data until class isolation is complete.",
                "إسناد الفصول لا تفرضه سياسات قاعدة البيانات بعد. "
                "لا تستخدم بيانات طلاب حقيقية حتى يكتمل عزل الفصول.",
            ))
            _class_notice = st.session_state.pop("_class_admin_notice", None)
            if _class_notice:
                st.success(_class_notice)
            try:
                _class_management = load_class_management(
                    _cloud_context["client"], _cloud_context["school_id"]
                )
            except (APIError, HTTPError) as _class_error:
                st.error(T(
                    f"Could not load class assignments: {_class_error}",
                    f"تعذّر تحميل إسنادات الفصول: {_class_error}",
                ))
            else:
                with st.form("admin_create_class"):
                    _class_name = st.text_input(T("New class name", "اسم الفصل الجديد"))
                    _create_class = st.form_submit_button(T("Create class", "إنشاء فصل"))
                if _create_class:
                    try:
                        create_school_class(
                            _cloud_context["client"], _cloud_context["school_id"], _class_name
                        )
                    except (APIError, HTTPError, ValueError) as _class_error:
                        st.error(T(
                            f"Could not create class: {_class_error}",
                            f"تعذّر إنشاء الفصل: {_class_error}",
                        ))
                    else:
                        st.session_state["_class_admin_notice"] = T(
                            "Class created.", "تم إنشاء الفصل."
                        )
                        st.rerun()

                _classes = {
                    row["class_id"]: row["class_name"]
                    for row in _class_management["classes"]
                }
                _teachers = [row["user_id"] for row in _class_management["teachers"]]
                _students = {
                    row["student_code"]: row
                    for row in _class_management["students"]
                }
                _unclassified_students = [
                    row for row in _class_management["students"]
                    if not row.get("class_id")
                ]
                if _unclassified_students:
                    st.warning(T(
                        f"{len(_unclassified_students)} students need a class assignment. "
                        "Review their records before assigning them.",
                        f"يحتاج {len(_unclassified_students)} من الطلاب إلى تحديد الفصل. "
                        "راجع سجلاتهم قبل إسنادهم.",
                    ))
                    st.dataframe(
                        pd.DataFrame(_unclassified_students)[["student_code", "display_name"]],
                        **full_width(), hide_index=True,
                    )
                if _classes and _teachers:
                    with st.form("admin_assign_teacher"):
                        _teacher_class = st.selectbox(
                            T("Class for teacher", "فصل المعلم"),
                            list(_classes), format_func=_classes.get,
                        )
                        _teacher_id = st.selectbox(T("Teacher ID", "معرّف المعلم"), _teachers)
                        _assign_teacher = st.form_submit_button(
                            T("Assign teacher", "إسناد المعلم")
                        )
                    if _assign_teacher:
                        try:
                            assign_teacher_to_class(
                                _cloud_context["client"], _cloud_context["school_id"],
                                _teacher_class, _teacher_id,
                            )
                        except (APIError, HTTPError) as _class_error:
                            st.error(T(
                                f"Could not assign teacher: {_class_error}",
                                f"تعذّر إسناد المعلم: {_class_error}",
                            ))
                        else:
                            st.session_state["_class_admin_notice"] = T(
                                "Teacher assigned.", "تم إسناد المعلم."
                            )
                            st.rerun()
                if _classes and _students:
                    with st.form("admin_assign_student"):
                        _student_code = st.selectbox(
                            T("Student", "الطالب"), list(_students),
                            format_func=lambda value: (
                                f"{value} — {_students[value].get('display_name') or value}"
                                f" — {_classes.get(_students[value].get('class_id'), T('Unassigned', 'غير مسند'))}"
                            ),
                        )
                        _student_class = st.selectbox(
                            T("Class for student", "فصل الطالب"),
                            list(_classes), format_func=_classes.get,
                        )
                        _assign_student = st.form_submit_button(
                            T("Assign student", "إسناد الطالب")
                        )
                    if _assign_student:
                        try:
                            assign_student_to_class(
                                _cloud_context["client"], _cloud_context["school_id"],
                                _student_code, _student_class,
                            )
                        except (APIError, HTTPError, ValueError) as _class_error:
                            st.error(T(
                                f"Could not assign student: {_class_error}",
                                f"تعذّر إسناد الطالب: {_class_error}",
                            ))
                        else:
                            st.session_state["_class_admin_notice"] = T(
                                "Student assigned.", "تم إسناد الطالب."
                            )
                            st.rerun()
                if _class_management["assignments"]:
                    _assignments = [
                        (row["class_id"], row["teacher_id"])
                        for row in _class_management["assignments"]
                    ]
                    with st.form("admin_remove_teacher"):
                        _assignment = st.selectbox(
                            T("Existing assignment", "الإسناد الحالي"),
                            _assignments,
                            format_func=lambda value: (
                                f"{_classes.get(value[0], value[0])} — {value[1]}"
                            ),
                        )
                        _remove_teacher = st.form_submit_button(
                            T("Remove teacher assignment", "إلغاء إسناد المعلم")
                        )
                    if _remove_teacher:
                        try:
                            remove_teacher_from_class(
                                _cloud_context["client"], _cloud_context["school_id"],
                                _assignment[0], _assignment[1],
                            )
                        except (APIError, HTTPError, ValueError) as _class_error:
                            st.error(T(
                                f"Could not remove assignment: {_class_error}",
                                f"تعذّر إلغاء الإسناد: {_class_error}",
                            ))
                        else:
                            st.session_state["_class_admin_notice"] = T(
                                "Teacher assignment removed.", "تم إلغاء إسناد المعلم."
                            )
                            st.rerun()
                    st.dataframe(
                        pd.DataFrame(_class_management["assignments"]),
                        **full_width(), hide_index=True,
                    )
        # Show all loaded student data if available (school-wide read)
        if "summary" in st.session_state:
            st.markdown(f"**{T('All Students (school-wide)', 'جميع الطلاب (على مستوى المدرسة)')}**")
            st.markdown('<div class="sf-card">', unsafe_allow_html=True)
            st.dataframe(
                _localized_dataframe(st.session_state["summary"]),
                **full_width(),
                hide_index=True,
            )
            st.markdown('</div>', unsafe_allow_html=True)

# ===========================================================================
# UI — Audit Log page (school-admin permission enforced in router and page)
# ===========================================================================
if _current_page == "audit_log":
    if not has_permission(st.session_state.get("active_role"), VIEW_AUDIT_LOG):
            _deny_page(VIEW_AUDIT_LOG)
    else:
            _HERE_APP = _os.path.dirname(_os.path.abspath(__file__))
            _pages_dir = _os.path.join(_HERE_APP, "pages")
            if _pages_dir not in _sys.path:
                _sys.path.insert(0, _pages_dir)
            try:
                from pages.audit_log import render as _audit_render
                _database_events = None
                if _cloud_context is not None:
                    _database_events = load_database_audit_events(
                        _cloud_context["client"],
                        _cloud_context["school_id"],
                        st.session_state["_cloud_audit_mode"],
                    )
                _audit_render(
                    database_events=_database_events,
                    database_managed=st.session_state.get("_cloud_audit_mode") == "database",
                )
            except Exception as _audit_err:
                st.error(T(
                    f"Could not load Audit Log: {_audit_err}",
                    f"تعذّر تحميل سجل التدقيق: {_audit_err}",
                ))

if not st.session_state.get("_cloud_sync_failed_this_run"):
    _sync_cloud_workspace_if_dirty()

# ===========================================================================
# Footer
# ===========================================================================
_footer_sub = T(
    "Smart platform for teachers and student tracking management",
    "منصة ذكية لمساعدة المعلمين وإدارة متابعة الطلاب"
)
_footer_note = T(
    "For trial use only — Not for production use without data governance approval",
    "للاستخدام التجريبي فقط — Not for production use without data governance approval"
)
st.markdown(f"""
<div class="sf-footer">
  <strong>SchoolFlow AI</strong> &nbsp;·&nbsp; MVP v0.1 Beta &nbsp;·&nbsp;
  {_footer_sub}<br>
  <span>{_footer_note}</span>
</div>
""", unsafe_allow_html=True)
