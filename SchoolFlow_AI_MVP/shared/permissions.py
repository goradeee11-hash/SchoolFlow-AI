"""
shared/permissions.py
---------------------
Centralized Role-Based Access Control (RBAC) for SchoolFlow AI — Task 10.

Design rules
------------
* Roles and permissions are defined once here — no scattered role-name
  comparisons elsewhere in the application.
* Permissions are explicit named constants; callers check permissions,
  not role names directly.
* Unknown or missing roles are DENIED by default (fail-secure).
* No permission is granted implicitly; every grant is listed explicitly.
* The current implementation uses a local/demo role context — a sidebar
  selector. This is NOT production-grade authentication.
  - Any user with browser access can change the demo role.
  - This provides a clear structure that can later be replaced by a
    trusted identity provider (e.g., OAuth, SAML, LDAP) without changing
    the permission check API.
* has_permission() / require_permission() are the only public entry
  points callers should use — do not compare role strings directly.

Roles
-----
  ROLE_TEACHER      : Classroom teacher — accesses own classes/students.
  ROLE_SCHOOL_ADMIN : School administrator — school-wide read; manages
                      teacher/class access; administrative functions.

Permissions
-----------
  VIEW_DASHBOARD          : Access the main dashboard.
  UPLOAD_DATA             : Upload a new student tracking file.
  VIEW_ANALYSIS           : View the performance analysis section.
  VIEW_REPORTS            : View student reports.
  SEND_PARENT_MESSAGES    : Prepare parent-message drafts.
  USE_LESSON_WORKSPACE    : Access and use the lesson workspace.
  VIEW_STUDENT_PROFILE    : View student profile pages.
  MANAGE_ASSESSMENTS      : Record and edit skill assessments.
  VIEW_ACADEMIC_PROGRESS  : View skills & academic progress page.
  MANAGE_INTERVENTIONS    : Create / update / close interventions.
  VIEW_INTERVENTIONS      : View interventions (read-only access).
  USE_BLOOM_QUESTIONS     : Access the Bloom question classifier / library.
  VIEW_ADMIN_DASHBOARD    : Access school-wide administrative dashboard.
  MANAGE_CLASS_ASSIGNMENTS: Assign teachers to classes (admin only).
  VIEW_ALL_STUDENTS       : Access any student's data school-wide (admin).
  VIEW_ALL_INTERVENTIONS  : View interventions across all teachers (admin).
  VIEW_AUDIT_LOG          : View the audit log (school admin only).

Security note
-------------
  Enforcement is done in Python, not only by hiding navigation items.
  Pages call require_permission() early in render(); a denied result is
  returned to the caller which must halt rendering and display the denial.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

ROLE_TEACHER      = "teacher"
ROLE_SCHOOL_ADMIN = "school_admin"
ROLE_DEMO_REVIEWER = "demo_reviewer"

#: Ordered list of all defined roles (used for display/validation)
ALL_ROLES: tuple[str, ...] = (ROLE_TEACHER, ROLE_SCHOOL_ADMIN, ROLE_DEMO_REVIEWER)

# ---------------------------------------------------------------------------
# Permission constants
# ---------------------------------------------------------------------------

VIEW_DASHBOARD           = "view_dashboard"
UPLOAD_DATA              = "upload_data"
VIEW_ANALYSIS            = "view_analysis"
VIEW_REPORTS             = "view_reports"
SEND_PARENT_MESSAGES     = "send_parent_messages"
USE_LESSON_WORKSPACE     = "use_lesson_workspace"
VIEW_STUDENT_PROFILE     = "view_student_profile"
MANAGE_ASSESSMENTS       = "manage_assessments"
VIEW_ACADEMIC_PROGRESS   = "view_academic_progress"
MANAGE_INTERVENTIONS     = "manage_interventions"
VIEW_INTERVENTIONS       = "view_interventions"
USE_BLOOM_QUESTIONS      = "use_bloom_questions"
VIEW_ADMIN_DASHBOARD     = "view_admin_dashboard"
MANAGE_CLASS_ASSIGNMENTS = "manage_class_assignments"
VIEW_ALL_STUDENTS        = "view_all_students"
VIEW_ALL_INTERVENTIONS   = "view_all_interventions"
VIEW_AUDIT_LOG           = "view_audit_log"

#: Complete set of all defined permissions (used for validation in tests)
ALL_PERMISSIONS: frozenset[str] = frozenset({
    VIEW_DASHBOARD,
    UPLOAD_DATA,
    VIEW_ANALYSIS,
    VIEW_REPORTS,
    SEND_PARENT_MESSAGES,
    USE_LESSON_WORKSPACE,
    VIEW_STUDENT_PROFILE,
    MANAGE_ASSESSMENTS,
    VIEW_ACADEMIC_PROGRESS,
    MANAGE_INTERVENTIONS,
    VIEW_INTERVENTIONS,
    USE_BLOOM_QUESTIONS,
    VIEW_ADMIN_DASHBOARD,
    MANAGE_CLASS_ASSIGNMENTS,
    VIEW_ALL_STUDENTS,
    VIEW_ALL_INTERVENTIONS,
    VIEW_AUDIT_LOG,
})

# ---------------------------------------------------------------------------
# Role-to-permission mapping
# ---------------------------------------------------------------------------
# Each entry is a frozenset of permissions granted to that role.
# A permission absent from the set is DENIED for that role.

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {

    ROLE_TEACHER: frozenset({
        VIEW_DASHBOARD,
        UPLOAD_DATA,
        VIEW_ANALYSIS,
        VIEW_REPORTS,
        SEND_PARENT_MESSAGES,
        USE_LESSON_WORKSPACE,
        VIEW_STUDENT_PROFILE,
        MANAGE_ASSESSMENTS,
        VIEW_ACADEMIC_PROGRESS,
        MANAGE_INTERVENTIONS,
        VIEW_INTERVENTIONS,
        USE_BLOOM_QUESTIONS,
        # NOT granted to teacher:
        # VIEW_ADMIN_DASHBOARD, MANAGE_CLASS_ASSIGNMENTS,
        # VIEW_ALL_STUDENTS, VIEW_ALL_INTERVENTIONS, VIEW_AUDIT_LOG
    }),

    ROLE_SCHOOL_ADMIN: frozenset({
        VIEW_DASHBOARD,
        UPLOAD_DATA,
        VIEW_ANALYSIS,
        VIEW_REPORTS,
        SEND_PARENT_MESSAGES,
        USE_LESSON_WORKSPACE,
        VIEW_STUDENT_PROFILE,
        MANAGE_ASSESSMENTS,
        VIEW_ACADEMIC_PROGRESS,
        MANAGE_INTERVENTIONS,
        VIEW_INTERVENTIONS,
        USE_BLOOM_QUESTIONS,
        # Admin-only additions:
        VIEW_ADMIN_DASHBOARD,
        MANAGE_CLASS_ASSIGNMENTS,
        VIEW_ALL_STUDENTS,
        VIEW_ALL_INTERVENTIONS,
        VIEW_AUDIT_LOG,
    }),

    ROLE_DEMO_REVIEWER: frozenset({
        VIEW_DASHBOARD, UPLOAD_DATA, VIEW_ANALYSIS, VIEW_REPORTS,
        SEND_PARENT_MESSAGES, USE_LESSON_WORKSPACE, VIEW_STUDENT_PROFILE,
        MANAGE_ASSESSMENTS, VIEW_ACADEMIC_PROGRESS, MANAGE_INTERVENTIONS,
        VIEW_INTERVENTIONS, USE_BLOOM_QUESTIONS, VIEW_ADMIN_DASHBOARD,
        VIEW_AUDIT_LOG,
    }),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_permission(role: str | None, permission: str) -> bool:
    """
    Return True if *role* is granted *permission*.

    Parameters
    ----------
    role       : A role constant (ROLE_TEACHER / ROLE_SCHOOL_ADMIN) or None.
    permission : A permission constant from this module.

    Rules
    -----
    * None, empty string, or any unknown role → False (default-deny).
    * Any unknown permission string → False (not in ANY role's grant set).
    * This function never raises.
    """
    if (
        not isinstance(role, str)
        or not role
        or not isinstance(permission, str)
        or not permission
    ):
        return False
    granted = _ROLE_PERMISSIONS.get(role)
    if granted is None:
        return False          # unknown role → deny
    return permission in granted


def require_permission(role: str | None, permission: str) -> dict:
    """
    Return a result dict indicating whether access is allowed.

    Returns
    -------
    {"allowed": True,  "role": role, "permission": permission, "reason": ""}
      or
    {"allowed": False, "role": role, "permission": permission,
     "reason": <human-readable denial message>}

    Callers should check result["allowed"] and halt rendering / action if False.
    The "reason" field is safe to display in the UI.
    """
    allowed = has_permission(role, permission)
    if allowed:
        return {
            "allowed":    True,
            "role":       role,
            "permission": permission,
            "reason":     "",
        }

    if role is None or (isinstance(role, str) and not role):
        reason_en = "No role is active. Please select a role to continue."
        reason_ar = "لا يوجد دور نشط. يرجى اختيار دور للمتابعة."
    elif not isinstance(role, str):
        reason_en = "Invalid role value. Access denied."
        reason_ar = "قيمة الدور غير صالحة. تم رفض الوصول."
    elif role not in _ROLE_PERMISSIONS:
        reason_en = f"Unknown role '{role}'. Access denied."
        reason_ar = f"الدور '{role}' غير معروف. تم رفض الوصول."
    elif not isinstance(permission, str) or not permission:
        reason_en = "Invalid permission value. Access denied."
        reason_ar = "قيمة الصلاحية غير صالحة. تم رفض الوصول."
    else:
        reason_en = (
            f"Your role ('{role}') does not have permission "
            f"to perform '{permission}'."
        )
        reason_ar = (
            f"دورك ('{role}') لا يمتلك صلاحية "
            f"تنفيذ '{permission}'."
        )

    # Bilingual: return both; callers choose the language
    return {
        "allowed":    False,
        "role":       role,
        "permission": permission,
        "reason":     reason_en,
        "reason_ar":  reason_ar,
    }


def get_permitted_nav_keys(role: str | None) -> list[str]:
    """
    Return the list of navigation page keys that the role may access.

    Used by app.py to decide which sidebar nav buttons to render.
    This is a UI convenience only — backend permission checks remain
    regardless of whether a nav button is visible.

    Nav-key → permission mapping:
      "dashboard"        → VIEW_DASHBOARD
      "upload"           → UPLOAD_DATA
      "analysis"         → VIEW_ANALYSIS
      "reports"          → VIEW_REPORTS
      "messages"         → SEND_PARENT_MESSAGES
      "assistant"          → VIEW_DASHBOARD
      "lesson_workspace" → USE_LESSON_WORKSPACE
      "student_profile"  → VIEW_STUDENT_PROFILE
      "academic_progress"→ VIEW_ACADEMIC_PROGRESS
      "interventions"    → MANAGE_INTERVENTIONS
      "bloom_questions"  → USE_BLOOM_QUESTIONS
      "settings"         → VIEW_DASHBOARD   (accessible to all roles)
      "admin_dashboard"  → VIEW_ADMIN_DASHBOARD
      "audit_log"        → VIEW_AUDIT_LOG
    """
    _NAV_PERMISSIONS: dict[str, str] = {
        "dashboard":         VIEW_DASHBOARD,
        "upload":            UPLOAD_DATA,
        "analysis":          VIEW_ANALYSIS,
        "reports":           VIEW_REPORTS,
        "messages":          SEND_PARENT_MESSAGES,
        "assistant":          VIEW_DASHBOARD,
        "lesson_workspace":  USE_LESSON_WORKSPACE,
        "student_profile":   VIEW_STUDENT_PROFILE,
        "academic_progress": VIEW_ACADEMIC_PROGRESS,
        "interventions":     MANAGE_INTERVENTIONS,
        "bloom_questions":   USE_BLOOM_QUESTIONS,
        "settings":          VIEW_DASHBOARD,
        "admin_dashboard":   VIEW_ADMIN_DASHBOARD,
        "audit_log":         VIEW_AUDIT_LOG,
    }
    return [
        key for key, perm in _NAV_PERMISSIONS.items()
        if has_permission(role, perm)
    ]


# ---------------------------------------------------------------------------
# Role display helpers
# ---------------------------------------------------------------------------

ROLE_DISPLAY: dict[str, tuple[str, str]] = {
    ROLE_TEACHER:      ("Teacher",       "معلم"),
    ROLE_SCHOOL_ADMIN: ("School Admin",  "مدير المدرسة"),
    ROLE_DEMO_REVIEWER: ("Demo Reviewer", "مراجع تجريبي"),
}


def role_display_name(role: str | None, arabic: bool = False) -> str:
    """Return a human-readable display name for a role."""
    if not role or role not in ROLE_DISPLAY:
        return "No Role" if not arabic else "لا يوجد دور"
    en, ar = ROLE_DISPLAY[role]
    return ar if arabic else en


# ---------------------------------------------------------------------------
# Demo / local context note
# ---------------------------------------------------------------------------

DEMO_SECURITY_NOTICE = (
    "⚠️  DEMO MODE — Role selected locally in this browser session. "
    "This is NOT production authentication. Any user with browser access "
    "can change the active role. Connect a trusted identity provider "
    "before deploying to a real school environment."
)

DEMO_SECURITY_NOTICE_AR = (
    "⚠️  وضع تجريبي — الدور مُحدَّد محليًا في جلسة المتصفح هذه. "
    "هذا ليس مصادقة إنتاجية حقيقية. يستطيع أي مستخدم لديه وصول للمتصفح "
    "تغيير الدور النشط. يجب ربط مزوّد هوية موثوق قبل النشر في بيئة مدرسية حقيقية."
)
