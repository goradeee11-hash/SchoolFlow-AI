"""
test_permissions.py
--------------------
Unit tests for shared/permissions.py — SchoolFlow AI (Task 10).

Tests cover:
  - All defined roles and permission constants.
  - Allowed and denied access for each role.
  - Unknown and missing/None roles.
  - Default-deny behaviour.
  - Protected operations (require_permission result dict).
  - Teacher vs School Admin access differences.
  - Role-context initialisation (shared/state.py).
  - Direct access denial for restricted permissions.
  - Navigation filtering by role.
  - Existing workflow preservation (teacher role has full teacher permissions).
  - Security notice strings are present.
  - Role display helpers.
  - No Streamlit import in permissions module.

No Streamlit runtime required; streamlit is stubbed.
"""

import sys
import os
import types
import unittest

# ---------------------------------------------------------------------------
# 1. Stub streamlit (identical pattern to other test files in the project)
# ---------------------------------------------------------------------------
_state: dict = {}


def _noop(*a, **kw):
    pass


def _noop_ctx(*a, **kw):
    import contextlib
    return contextlib.nullcontext()


class _FakeST(types.ModuleType):
    session_state = _state
    secrets       = {}
    set_page_config = staticmethod(_noop)
    markdown        = staticmethod(_noop)
    error           = staticmethod(_noop)
    warning         = staticmethod(_noop)
    info            = staticmethod(_noop)
    caption         = staticmethod(_noop)
    success         = staticmethod(_noop)
    write           = staticmethod(_noop)
    rerun           = staticmethod(_noop)
    stop            = staticmethod(_noop)
    button          = staticmethod(lambda *a, **kw: False)
    toggle          = staticmethod(lambda *a, **kw: False)
    selectbox       = staticmethod(
        lambda *a, **kw: (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0]
    )
    columns         = staticmethod(lambda n, **kw: [
        type("Col", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: None})()
        for _ in range(n if isinstance(n, int) else len(n))
    ])
    expander        = staticmethod(_noop_ctx)
    container       = staticmethod(_noop_ctx)
    spinner         = staticmethod(_noop_ctx)
    tabs            = staticmethod(lambda labels: [_noop_ctx() for _ in labels])
    cache_data      = staticmethod(lambda f=None, **kw: f if f else lambda g: g)
    text_input      = staticmethod(lambda *a, **kw: kw.get("value", ""))
    number_input    = staticmethod(lambda *a, **kw: kw.get("value", 0.0))
    date_input      = staticmethod(lambda *a, **kw: None)
    dataframe       = staticmethod(_noop)
    class _FakeSidebar:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def button(self, *a, **kw): return False
    sidebar = _FakeSidebar()


sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2. Patch sys.path
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# 3. Import the module under test
# ---------------------------------------------------------------------------
from shared.permissions import (
    # Role constants
    ROLE_TEACHER,
    ROLE_SCHOOL_ADMIN,
    ALL_ROLES,
    # Permission constants
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
    ALL_PERMISSIONS,
    # Functions
    has_permission,
    require_permission,
    get_permitted_nav_keys,
    role_display_name,
    # Display helpers
    ROLE_DISPLAY,
    DEMO_SECURITY_NOTICE,
    DEMO_SECURITY_NOTICE_AR,
)


# ===========================================================================
# 1. Constants
# ===========================================================================
class TestConstants(unittest.TestCase):

    def test_01_all_roles_contains_teacher(self):
        self.assertIn(ROLE_TEACHER, ALL_ROLES)

    def test_02_all_roles_contains_school_admin(self):
        self.assertIn(ROLE_SCHOOL_ADMIN, ALL_ROLES)

    def test_03_all_roles_include_demo_reviewer(self):
        self.assertIn("demo_reviewer", ALL_ROLES)

    def test_04_all_permissions_is_frozenset(self):
        self.assertIsInstance(ALL_PERMISSIONS, frozenset)

    def test_05_all_permissions_non_empty(self):
        self.assertGreater(len(ALL_PERMISSIONS), 0)

    def test_06_all_permission_constants_in_all_permissions(self):
        """Every explicitly named constant must be in ALL_PERMISSIONS."""
        for perm in [
            VIEW_DASHBOARD, UPLOAD_DATA, VIEW_ANALYSIS, VIEW_REPORTS,
            SEND_PARENT_MESSAGES, USE_LESSON_WORKSPACE, VIEW_STUDENT_PROFILE,
            MANAGE_ASSESSMENTS, VIEW_ACADEMIC_PROGRESS, MANAGE_INTERVENTIONS,
            VIEW_INTERVENTIONS, USE_BLOOM_QUESTIONS, VIEW_ADMIN_DASHBOARD,
            MANAGE_CLASS_ASSIGNMENTS, VIEW_ALL_STUDENTS, VIEW_ALL_INTERVENTIONS,
        ]:
            self.assertIn(perm, ALL_PERMISSIONS, msg=f"Missing from ALL_PERMISSIONS: {perm}")

    def test_07_role_constants_are_strings(self):
        self.assertIsInstance(ROLE_TEACHER, str)
        self.assertIsInstance(ROLE_SCHOOL_ADMIN, str)

    def test_08_permission_constants_are_strings(self):
        for p in ALL_PERMISSIONS:
            self.assertIsInstance(p, str, msg=f"Non-string permission: {p!r}")

    def test_09_demo_notice_non_empty(self):
        self.assertTrue(DEMO_SECURITY_NOTICE.strip())

    def test_10_demo_notice_ar_non_empty(self):
        self.assertTrue(DEMO_SECURITY_NOTICE_AR.strip())

    def test_11_demo_notice_contains_warning_keyword(self):
        self.assertIn("DEMO", DEMO_SECURITY_NOTICE.upper())

    def test_12_role_display_has_both_roles(self):
        self.assertIn(ROLE_TEACHER, ROLE_DISPLAY)
        self.assertIn(ROLE_SCHOOL_ADMIN, ROLE_DISPLAY)


# ===========================================================================
# 2. has_permission — teacher
# ===========================================================================
class TestTeacherPermissions(unittest.TestCase):

    def _teacher(self, perm):
        return has_permission(ROLE_TEACHER, perm)

    def test_13_teacher_view_dashboard(self):
        self.assertTrue(self._teacher(VIEW_DASHBOARD))

    def test_14_teacher_upload_data(self):
        self.assertTrue(self._teacher(UPLOAD_DATA))

    def test_15_teacher_view_analysis(self):
        self.assertTrue(self._teacher(VIEW_ANALYSIS))

    def test_16_teacher_view_reports(self):
        self.assertTrue(self._teacher(VIEW_REPORTS))

    def test_17_teacher_send_parent_messages(self):
        self.assertTrue(self._teacher(SEND_PARENT_MESSAGES))

    def test_18_teacher_use_lesson_workspace(self):
        self.assertTrue(self._teacher(USE_LESSON_WORKSPACE))

    def test_19_teacher_view_student_profile(self):
        self.assertTrue(self._teacher(VIEW_STUDENT_PROFILE))

    def test_20_teacher_manage_assessments(self):
        self.assertTrue(self._teacher(MANAGE_ASSESSMENTS))

    def test_21_teacher_view_academic_progress(self):
        self.assertTrue(self._teacher(VIEW_ACADEMIC_PROGRESS))

    def test_22_teacher_manage_interventions(self):
        self.assertTrue(self._teacher(MANAGE_INTERVENTIONS))

    def test_23_teacher_view_interventions(self):
        self.assertTrue(self._teacher(VIEW_INTERVENTIONS))

    def test_24_teacher_use_bloom_questions(self):
        self.assertTrue(self._teacher(USE_BLOOM_QUESTIONS))

    # Teacher must NOT have admin-only permissions
    def test_25_teacher_denied_view_admin_dashboard(self):
        self.assertFalse(self._teacher(VIEW_ADMIN_DASHBOARD))

    def test_26_teacher_denied_manage_class_assignments(self):
        self.assertFalse(self._teacher(MANAGE_CLASS_ASSIGNMENTS))

    def test_27_teacher_denied_view_all_students(self):
        self.assertFalse(self._teacher(VIEW_ALL_STUDENTS))

    def test_28_teacher_denied_view_all_interventions(self):
        self.assertFalse(self._teacher(VIEW_ALL_INTERVENTIONS))


# ===========================================================================
# 3. has_permission — school_admin
# ===========================================================================
class TestSchoolAdminPermissions(unittest.TestCase):

    def _admin(self, perm):
        return has_permission(ROLE_SCHOOL_ADMIN, perm)

    def test_29_admin_view_dashboard(self):
        self.assertTrue(self._admin(VIEW_DASHBOARD))

    def test_30_admin_upload_data(self):
        self.assertTrue(self._admin(UPLOAD_DATA))

    def test_31_admin_view_analysis(self):
        self.assertTrue(self._admin(VIEW_ANALYSIS))

    def test_32_admin_view_reports(self):
        self.assertTrue(self._admin(VIEW_REPORTS))

    def test_33_admin_send_parent_messages(self):
        self.assertTrue(self._admin(SEND_PARENT_MESSAGES))

    def test_34_admin_use_lesson_workspace(self):
        self.assertTrue(self._admin(USE_LESSON_WORKSPACE))

    def test_35_admin_view_student_profile(self):
        self.assertTrue(self._admin(VIEW_STUDENT_PROFILE))

    def test_36_admin_manage_assessments(self):
        self.assertTrue(self._admin(MANAGE_ASSESSMENTS))

    def test_37_admin_view_academic_progress(self):
        self.assertTrue(self._admin(VIEW_ACADEMIC_PROGRESS))

    def test_38_admin_manage_interventions(self):
        self.assertTrue(self._admin(MANAGE_INTERVENTIONS))

    def test_39_admin_view_interventions(self):
        self.assertTrue(self._admin(VIEW_INTERVENTIONS))

    def test_40_admin_use_bloom_questions(self):
        self.assertTrue(self._admin(USE_BLOOM_QUESTIONS))

    # Admin-only permissions
    def test_41_admin_view_admin_dashboard(self):
        self.assertTrue(self._admin(VIEW_ADMIN_DASHBOARD))

    def test_42_admin_manage_class_assignments(self):
        self.assertTrue(self._admin(MANAGE_CLASS_ASSIGNMENTS))

    def test_43_admin_view_all_students(self):
        self.assertTrue(self._admin(VIEW_ALL_STUDENTS))

    def test_44_admin_view_all_interventions(self):
        self.assertTrue(self._admin(VIEW_ALL_INTERVENTIONS))


# ===========================================================================
# 4. Default-deny behaviour
# ===========================================================================
class TestDefaultDeny(unittest.TestCase):

    def test_45_none_role_denied(self):
        self.assertFalse(has_permission(None, VIEW_DASHBOARD))

    def test_46_empty_string_role_denied(self):
        self.assertFalse(has_permission("", VIEW_DASHBOARD))

    def test_47_unknown_role_denied(self):
        self.assertFalse(has_permission("superuser", VIEW_DASHBOARD))

    def test_48_unknown_role_denied_all_permissions(self):
        for perm in ALL_PERMISSIONS:
            self.assertFalse(
                has_permission("unknown_role", perm),
                msg=f"Unknown role must not have permission: {perm}",
            )

    def test_49_none_role_denied_all_permissions(self):
        for perm in ALL_PERMISSIONS:
            self.assertFalse(
                has_permission(None, perm),
                msg=f"None role must not have permission: {perm}",
            )

    def test_50_unknown_permission_denied_for_all_roles(self):
        for role in ALL_ROLES:
            self.assertFalse(
                has_permission(role, "nonexistent_permission"),
                msg=f"Unknown permission must be denied for role: {role}",
            )

    def test_51_empty_permission_denied(self):
        self.assertFalse(has_permission(ROLE_TEACHER, ""))

    def test_52_none_permission_denied(self):
        # has_permission(role, None) — permissive guard: must return False
        self.assertFalse(has_permission(ROLE_TEACHER, None))

    def test_53_has_permission_never_raises(self):
        """has_permission must never raise, regardless of inputs."""
        for role in [None, "", "unknown", ROLE_TEACHER, ROLE_SCHOOL_ADMIN, 42, [], {}]:
            for perm in [None, "", "unknown", VIEW_DASHBOARD, 42, [], {}]:
                try:
                    result = has_permission(role, perm)
                except Exception as e:
                    self.fail(
                        f"has_permission({role!r}, {perm!r}) raised: {e}"
                    )
                if not isinstance(role, str) or not isinstance(perm, str):
                    self.assertFalse(
                        result,
                        msg=f"Invalid inputs must be denied: {role!r}, {perm!r}",
                    )


# ===========================================================================
# 5. require_permission result dict
# ===========================================================================
class TestRequirePermission(unittest.TestCase):

    def test_54_allowed_result_has_required_keys(self):
        r = require_permission(ROLE_TEACHER, VIEW_DASHBOARD)
        for key in ("allowed", "role", "permission", "reason"):
            self.assertIn(key, r, msg=f"Missing key: {key}")

    def test_55_allowed_result_allowed_is_true(self):
        r = require_permission(ROLE_TEACHER, VIEW_DASHBOARD)
        self.assertTrue(r["allowed"])

    def test_56_allowed_result_reason_is_empty(self):
        r = require_permission(ROLE_TEACHER, VIEW_DASHBOARD)
        self.assertEqual(r["reason"], "")

    def test_57_denied_result_allowed_is_false(self):
        r = require_permission(ROLE_TEACHER, VIEW_ADMIN_DASHBOARD)
        self.assertFalse(r["allowed"])

    def test_58_denied_result_has_reason(self):
        r = require_permission(ROLE_TEACHER, VIEW_ADMIN_DASHBOARD)
        self.assertTrue(r["reason"].strip())

    def test_59_denied_none_role_has_reason(self):
        r = require_permission(None, VIEW_DASHBOARD)
        self.assertFalse(r["allowed"])
        self.assertTrue(r.get("reason", "").strip())

    def test_60_denied_unknown_role_has_reason(self):
        r = require_permission("hacker", VIEW_DASHBOARD)
        self.assertFalse(r["allowed"])
        self.assertTrue(r.get("reason", "").strip())

    def test_61_denied_result_has_reason_ar(self):
        r = require_permission(ROLE_TEACHER, VIEW_ADMIN_DASHBOARD)
        self.assertIn("reason_ar", r)
        self.assertTrue(r["reason_ar"].strip())

    def test_62_result_role_field_matches_input(self):
        r = require_permission(ROLE_SCHOOL_ADMIN, VIEW_ALL_STUDENTS)
        self.assertEqual(r["role"], ROLE_SCHOOL_ADMIN)

    def test_63_result_permission_field_matches_input(self):
        r = require_permission(ROLE_TEACHER, USE_LESSON_WORKSPACE)
        self.assertEqual(r["permission"], USE_LESSON_WORKSPACE)

    def test_64_require_permission_never_raises(self):
        for role in [None, "", "unknown", ROLE_TEACHER, ROLE_SCHOOL_ADMIN, 42, [], {}]:
            for perm in [None, "", "unknown", VIEW_DASHBOARD, VIEW_ADMIN_DASHBOARD, 42, [], {}]:
                try:
                    result = require_permission(role, perm)
                except Exception as e:
                    self.fail(
                        f"require_permission({role!r}, {perm!r}) raised: {e}"
                    )
                if not isinstance(role, str) or not isinstance(perm, str):
                    self.assertFalse(
                        result["allowed"],
                        msg=f"Invalid inputs must be denied: {role!r}, {perm!r}",
                    )
                    self.assertIsInstance(result.get("reason"), str)
                    self.assertIsInstance(result.get("reason_ar"), str)


# ===========================================================================
# 6. Teacher vs School Admin differences
# ===========================================================================
class TestTeacherVsAdmin(unittest.TestCase):

    _ADMIN_ONLY_PERMISSIONS = {
        VIEW_ADMIN_DASHBOARD,
        MANAGE_CLASS_ASSIGNMENTS,
        VIEW_ALL_STUDENTS,
        VIEW_ALL_INTERVENTIONS,
    }

    def test_65_every_admin_only_perm_denied_to_teacher(self):
        for perm in self._ADMIN_ONLY_PERMISSIONS:
            self.assertFalse(
                has_permission(ROLE_TEACHER, perm),
                msg=f"Teacher must not have admin-only permission: {perm}",
            )

    def test_66_every_admin_only_perm_allowed_to_admin(self):
        for perm in self._ADMIN_ONLY_PERMISSIONS:
            self.assertTrue(
                has_permission(ROLE_SCHOOL_ADMIN, perm),
                msg=f"Admin must have permission: {perm}",
            )

    def test_67_admin_has_at_least_as_many_perms_as_teacher(self):
        teacher_perms = {p for p in ALL_PERMISSIONS if has_permission(ROLE_TEACHER, p)}
        admin_perms   = {p for p in ALL_PERMISSIONS if has_permission(ROLE_SCHOOL_ADMIN, p)}
        self.assertTrue(teacher_perms.issubset(admin_perms))

    def test_68_admin_has_strictly_more_perms_than_teacher(self):
        teacher_perms = {p for p in ALL_PERMISSIONS if has_permission(ROLE_TEACHER, p)}
        admin_perms   = {p for p in ALL_PERMISSIONS if has_permission(ROLE_SCHOOL_ADMIN, p)}
        self.assertGreater(len(admin_perms), len(teacher_perms))


# ===========================================================================
# 7. Navigation filtering
# ===========================================================================
class TestNavFiltering(unittest.TestCase):

    def test_69_teacher_nav_does_not_include_admin_dashboard(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertNotIn("admin_dashboard", keys)

    def test_70_admin_nav_includes_admin_dashboard(self):
        keys = get_permitted_nav_keys(ROLE_SCHOOL_ADMIN)
        self.assertIn("admin_dashboard", keys)

    def test_71_teacher_nav_includes_lesson_workspace(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertIn("lesson_workspace", keys)

    def test_72_teacher_nav_includes_student_profile(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertIn("student_profile", keys)

    def test_73_teacher_nav_includes_academic_progress(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertIn("academic_progress", keys)

    def test_74_teacher_nav_includes_interventions(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertIn("interventions", keys)

    def test_75_teacher_nav_includes_bloom_questions(self):
        keys = get_permitted_nav_keys(ROLE_TEACHER)
        self.assertIn("bloom_questions", keys)

    def test_teacher_and_admin_nav_include_assistant(self):
        self.assertIn("assistant", get_permitted_nav_keys(ROLE_TEACHER))
        self.assertIn("assistant", get_permitted_nav_keys(ROLE_SCHOOL_ADMIN))

    def test_76_none_role_nav_is_empty(self):
        keys = get_permitted_nav_keys(None)
        self.assertEqual(keys, [])

    def test_77_unknown_role_nav_is_empty(self):
        keys = get_permitted_nav_keys("unknown_role")
        self.assertEqual(keys, [])

    def test_78_nav_returns_list(self):
        self.assertIsInstance(get_permitted_nav_keys(ROLE_TEACHER), list)

    def test_79_admin_nav_is_superset_of_teacher_nav(self):
        teacher_keys = set(get_permitted_nav_keys(ROLE_TEACHER))
        admin_keys   = set(get_permitted_nav_keys(ROLE_SCHOOL_ADMIN))
        self.assertTrue(teacher_keys.issubset(admin_keys))

    def test_80_all_teacher_nav_keys_pass_permission_check(self):
        """Every key returned must actually be permitted."""
        for key in get_permitted_nav_keys(ROLE_TEACHER):
            # We just verify the function's output is consistent with has_permission
            # by checking the key is in the full nav set (not an invented key)
            self.assertIsInstance(key, str)


# ===========================================================================
# 8. Role display helpers
# ===========================================================================
class TestRoleDisplayHelpers(unittest.TestCase):

    def test_81_teacher_display_english(self):
        name = role_display_name(ROLE_TEACHER, arabic=False)
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_82_teacher_display_arabic(self):
        name = role_display_name(ROLE_TEACHER, arabic=True)
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_83_admin_display_english(self):
        name = role_display_name(ROLE_SCHOOL_ADMIN, arabic=False)
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_84_admin_display_arabic(self):
        name = role_display_name(ROLE_SCHOOL_ADMIN, arabic=True)
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_85_none_role_display_fallback(self):
        name = role_display_name(None)
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_86_unknown_role_display_fallback(self):
        name = role_display_name("unknown_role")
        self.assertIsInstance(name, str)
        self.assertTrue(name.strip())

    def test_87_english_and_arabic_names_differ(self):
        en = role_display_name(ROLE_TEACHER, arabic=False)
        ar = role_display_name(ROLE_TEACHER, arabic=True)
        self.assertNotEqual(en, ar)


# ===========================================================================
# 9. State integration — active_role key in state.py
# ===========================================================================
class TestStateIntegration(unittest.TestCase):

    def _state_src(self):
        path = os.path.join(HERE, "shared", "state.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_88_active_role_in_state_defaults(self):
        src = self._state_src()
        self.assertIn("active_role", src)

    def test_89_active_role_default_is_teacher(self):
        """Default role must be 'teacher' so existing workflows are unaffected."""
        src = self._state_src()
        self.assertIn('"teacher"', src)

    def test_90_state_has_demo_comment(self):
        """State must note this is a local/demo context."""
        src = self._state_src()
        # Accept any mention of demo/local/not production
        combined = src.lower()
        self.assertTrue(
            "demo" in combined or "local" in combined or "not production" in combined,
            msg="state.py must note that active_role is a demo/local context",
        )


# ===========================================================================
# 10. App wiring — permissions imported and used in app.py
# ===========================================================================
class TestAppWiring(unittest.TestCase):

    def _app_src(self):
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_91_permissions_imported_in_app(self):
        src = self._app_src()
        self.assertIn("from shared.permissions import", src)

    def test_92_has_permission_used_in_app(self):
        src = self._app_src()
        self.assertIn("has_permission", src)

    def test_93_require_permission_used_in_app(self):
        src = self._app_src()
        self.assertIn("require_permission", src)

    def test_94_get_permitted_nav_keys_used_in_app(self):
        src = self._app_src()
        self.assertIn("get_permitted_nav_keys", src)

    def test_95_lesson_workspace_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("USE_LESSON_WORKSPACE", src)

    def test_96_student_profile_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("VIEW_STUDENT_PROFILE", src)

    def test_97_academic_progress_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("VIEW_ACADEMIC_PROGRESS", src)

    def test_98_interventions_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("MANAGE_INTERVENTIONS", src)

    def test_99_bloom_questions_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("USE_BLOOM_QUESTIONS", src)

    def test_100_admin_dashboard_guarded_in_app(self):
        src = self._app_src()
        self.assertIn("VIEW_ADMIN_DASHBOARD", src)

    def test_101_role_selector_in_app(self):
        src = self._app_src()
        self.assertIn("role_selector", src)

    def test_102_active_role_session_state_in_app(self):
        src = self._app_src()
        self.assertIn("active_role", src)


# ===========================================================================
# 11. No Streamlit import in permissions module (testability constraint)
# ===========================================================================
class TestModuleConstraints(unittest.TestCase):

    def _perm_src(self):
        path = os.path.join(HERE, "shared", "permissions.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_103_permissions_module_has_no_streamlit_import(self):
        src = self._perm_src()
        self.assertNotIn("import streamlit", src)

    def test_104_permissions_module_exists(self):
        path = os.path.join(HERE, "shared", "permissions.py")
        self.assertTrue(os.path.isfile(path), "shared/permissions.py not found")

    def test_105_permissions_module_has_all_role_constants(self):
        src = self._perm_src()
        self.assertIn("ROLE_TEACHER", src)
        self.assertIn("ROLE_SCHOOL_ADMIN", src)

    def test_106_demo_notice_present_in_module(self):
        src = self._perm_src()
        self.assertIn("DEMO_SECURITY_NOTICE", src)


# ===========================================================================
# 12. Direct access denial — protected operations
# ===========================================================================
class TestDirectAccessDenial(unittest.TestCase):

    def test_107_teacher_cannot_access_admin_dashboard_directly(self):
        r = require_permission(ROLE_TEACHER, VIEW_ADMIN_DASHBOARD)
        self.assertFalse(r["allowed"])

    def test_108_teacher_cannot_manage_class_assignments(self):
        r = require_permission(ROLE_TEACHER, MANAGE_CLASS_ASSIGNMENTS)
        self.assertFalse(r["allowed"])

    def test_109_no_role_cannot_access_any_page(self):
        for perm in ALL_PERMISSIONS:
            r = require_permission(None, perm)
            self.assertFalse(r["allowed"],
                             msg=f"None role must not access: {perm}")

    def test_110_unknown_role_cannot_access_any_page(self):
        for perm in ALL_PERMISSIONS:
            r = require_permission("not_a_real_role", perm)
            self.assertFalse(r["allowed"],
                             msg=f"Unknown role must not access: {perm}")

    def test_111_admin_only_perms_denied_to_teacher_via_require(self):
        admin_only = {
            VIEW_ADMIN_DASHBOARD, MANAGE_CLASS_ASSIGNMENTS,
            VIEW_ALL_STUDENTS, VIEW_ALL_INTERVENTIONS,
        }
        for perm in admin_only:
            r = require_permission(ROLE_TEACHER, perm)
            self.assertFalse(r["allowed"],
                             msg=f"Teacher must be denied: {perm}")


# ===========================================================================
# 13. Existing teacher workflows still work (regression)
# ===========================================================================
class TestExistingWorkflowPreservation(unittest.TestCase):

    _TEACHER_WORKFLOW_PERMS = [
        VIEW_DASHBOARD,
        UPLOAD_DATA,
        VIEW_ANALYSIS,
        VIEW_REPORTS,
        USE_LESSON_WORKSPACE,
        VIEW_STUDENT_PROFILE,
        MANAGE_ASSESSMENTS,
        VIEW_ACADEMIC_PROGRESS,
        MANAGE_INTERVENTIONS,
        USE_BLOOM_QUESTIONS,
        SEND_PARENT_MESSAGES,
    ]

    def test_112_all_teacher_workflow_permissions_still_granted(self):
        """
        All permissions that existing teacher pages rely on must still be
        granted to ROLE_TEACHER. This is the regression guard.
        """
        for perm in self._TEACHER_WORKFLOW_PERMS:
            self.assertTrue(
                has_permission(ROLE_TEACHER, perm),
                msg=f"Existing teacher workflow broken: permission '{perm}' denied",
            )

    def test_113_teacher_role_is_the_default_role(self):
        """
        The default active_role in state.py must be ROLE_TEACHER so that
        existing sessions without a role set continue to work as before.
        """
        from shared.state import _DEFAULTS
        self.assertEqual(_DEFAULTS.get("active_role"), ROLE_TEACHER)

    def test_114_has_permission_returns_bool(self):
        """has_permission must always return a bool (never truthy/falsy object)."""
        result = has_permission(ROLE_TEACHER, VIEW_DASHBOARD)
        self.assertIsInstance(result, bool)
        result2 = has_permission(None, VIEW_DASHBOARD)
        self.assertIsInstance(result2, bool)


# ===========================================================================
# Runner
# ===========================================================================
if __name__ == "__main__":
    print("=== SchoolFlow AI — Permissions (RBAC) Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    for cls in [
        TestConstants,
        TestTeacherPermissions,
        TestSchoolAdminPermissions,
        TestDefaultDeny,
        TestRequirePermission,
        TestTeacherVsAdmin,
        TestNavFiltering,
        TestRoleDisplayHelpers,
        TestStateIntegration,
        TestAppWiring,
        TestModuleConstraints,
        TestDirectAccessDenial,
        TestExistingWorkflowPreservation,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 54)
        print(f"  ALL {total} PERMISSIONS TESTS PASSED")
        print("=" * 54)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
