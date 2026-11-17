"""School-admin-only audit log view for the current Streamlit session."""

from __future__ import annotations

from datetime import date
import json

import pandas as pd
import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

from shared.audit import (
    ACTION_PAGE_ACCESS,
    ACTION_PERMISSION_CHECK,
    ALL_ACTIONS,
    ALL_STATUSES,
    ENTITY_PAGE,
    STATUS_FAILURE,
    audit_summary_stats,
    get_audit_events,
    log_event,
)
from shared.i18n import T, is_arabic, text_dir
from shared.streamlit_compat import full_width
from shared.permissions import (
    DEMO_SECURITY_NOTICE,
    DEMO_SECURITY_NOTICE_AR,
    ROLE_SCHOOL_ADMIN,
    ROLE_TEACHER,
    ROLE_DEMO_REVIEWER,
    VIEW_AUDIT_LOG,
    require_permission,
)
from shared.time_utils import format_timestamp_riyadh

_ACTION_LABELS = {
    "assessment_created": ("Assessment created", "إنشاء تقييم"),
    "assessment_updated": ("Assessment updated", "تحديث تقييم"),
    "checkpoint_added": ("Intervention checkpoint added", "إضافة نقطة تقدم"),
    "data_import": ("Data import completed", "اكتمال استيراد البيانات"),
    "intervention_created": ("Intervention created", "إنشاء تدخل"),
    "intervention_updated": ("Intervention updated", "تحديث تدخل"),
    "lesson_ended": ("Lesson ended", "إنهاء حصة"),
    "lesson_plan_updated": ("Lesson plan updated", "تحديث خطة الحصة"),
    "lesson_started": ("Lesson started", "بدء حصة"),
    "page_access": ("Audit log page accessed", "عرض سجل التدقيق"),
    "participation_logged": ("Participation recorded", "تسجيل مشاركة"),
    "permission_check": ("Permission check denied", "رفض فحص صلاحية"),
    "profile_viewed": ("Student profile viewed", "عرض ملف طالب"),
    "report_downloaded": ("Report downloaded", "تنزيل تقرير"),
    "report_generated": ("Report generated", "إنشاء تقرير"),
    "role_changed": ("Demo role changed", "تغيير الدور التجريبي"),
    "skill_created": ("Skill created", "إنشاء مهارة"),
    "skill_removed": ("Skill removed", "حذف مهارة"),
}
def _safe_role(value: object) -> str:
    if isinstance(value, str) and value in {ROLE_TEACHER, ROLE_SCHOOL_ADMIN, ROLE_DEMO_REVIEWER}:
        return value
    return "unknown"


def _public_events(events: list[dict], arabic: bool = False) -> list[dict]:
    """Expose only validated, non-personal audit fields for display."""
    rows = []
    for event in events:
        action = event.get("action")
        role = event.get("actor_role")
        status = event.get("status")
        safe_action = action if isinstance(action, str) and action in ALL_ACTIONS else "unknown"
        rows.append({
            "timestamp": format_timestamp_riyadh(event["timestamp"]),
            "actor_role": _safe_role(role),
            "action": safe_action,
            "status": status if isinstance(status, str) and status in ALL_STATUSES else "unknown",
            "summary": _ACTION_LABELS.get(safe_action, ("Unknown", "غير معروف"))[1 if arabic else 0],
        })
    return rows


def render(
    database_events: list[dict] | None = None,
    database_managed: bool = False,
) -> None:
    """Render the audit log after enforcing server-side role authorization."""
    _is_ar = is_arabic()
    _dir = text_dir()
    role = st.session_state.get("active_role")
    access = require_permission(role, VIEW_AUDIT_LOG)
    if not access["allowed"]:
        attempt = f"{role!s}:{st.session_state.get('page', '')}"
        if st.session_state.get("_audit_denied_attempt") != attempt:
            st.session_state["audit_log"] = log_event(
                st.session_state.get("audit_log", []),
                action=ACTION_PERMISSION_CHECK,
                actor_role=_safe_role(role),
                entity_type=ENTITY_PAGE,
                status=STATUS_FAILURE,
            )
            st.session_state["_audit_denied_attempt"] = attempt
        st.error(T(access["reason"], access["reason_ar"]))
        return

    if not st.session_state.get("_audit_log_page_access_logged"):
        st.session_state["audit_log"] = log_event(
            st.session_state.get("audit_log", []),
            action=ACTION_PAGE_ACCESS,
            actor_role=_safe_role(role),
            entity_type=ENTITY_PAGE,
        )
        st.session_state["_audit_log_page_access_logged"] = True

    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_dir};">
          <div class="sf-section-num">🧾</div>
          <div class="sf-section-title">{T("Audit Log", "سجل التدقيق")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if database_events is not None:
        st.markdown(f"**{T('Database events', 'أحداث قاعدة البيانات')}**")
        st.caption(T(
            "Only database-generated events are verified. Earlier client-submitted "
            "events are unverified. Reads and failed attempts are not included.",
            "الأحداث التي أنشأتها قاعدة البيانات فقط موثوقة. الأحداث السابقة المرسلة "
            "من العميل غير موثوقة. لا يشمل السجل القراءة أو المحاولات الفاشلة.",
        ))
        database_rows = []
        for event in database_events:
            is_generated = database_managed and event.get("database_generated") is True
            data = event.get("record_data")
            entity_key = data.get("entity_key") if is_generated and isinstance(data, dict) else None
            database_rows.append({
                T("Time", "الوقت"): format_timestamp_riyadh(event["occurred_at"]),
                T("Actor ID", "معرّف المنفذ"): event.get("actor_user_id", ""),
                T("Role", "الدور"): _safe_role(event.get("actor_role")),
                T("Operation", "العملية"): event.get("action", ""),
                T("Entity", "نوع السجل"): event.get("entity_type", ""),
                T("Record key", "معرّف السجل"): (
                    json.dumps(entity_key, ensure_ascii=False, sort_keys=True)
                    if isinstance(entity_key, dict) else ""
                ),
                T("Status", "الحالة"): event.get("status", ""),
                T("Source", "المصدر"): (
                    T("Database", "قاعدة البيانات") if is_generated
                    else T("Unverified", "غير موثوق")
                ),
            })
        st.dataframe(pd.DataFrame(database_rows), **full_width(), hide_index=True)

    st.warning(T(DEMO_SECURITY_NOTICE, DEMO_SECURITY_NOTICE_AR))
    if database_events is None:
        st.caption(T(
            "Demo log is session-only and is not tamper-proof.",
            "السجل التجريبي محفوظ للجلسة فقط وليس محميًا من التلاعب.",
        ))
    else:
        st.caption(T(
            "The activity log below includes unverified session or legacy events.",
            "سجل الأنشطة أدناه يتضمن أحداث الجلسة أو أحداثًا قديمة غير موثوقة.",
        ))

    events = st.session_state.get("audit_log", [])
    normalized_events = get_audit_events(events)
    safe_events = _public_events(normalized_events, _is_ar)
    stats = audit_summary_stats(events)
    event_days = [
        date.fromisoformat(event["timestamp"][:10])
        for event in normalized_events
        if len(event.get("timestamp", "")) >= 10
    ]
    default_date_range = (
        (min(event_days), max(event_days))
        if event_days
        else (date.today(), date.today())
    )

    metric_cols = st.columns(3)
    metric_cols[0].metric(T("Operations", "العمليات"), stats["total"])
    metric_cols[1].metric(T("Success", "نجاح"), stats["success"])
    metric_cols[2].metric(T("Failure", "فشل"), stats["failure"])

    st.markdown(
        f"**{T('Operations by type', 'العمليات حسب النوع')}**",
        unsafe_allow_html=False,
    )
    action_rows = [
        {
            T("Operation", "العملية"): _ACTION_LABELS.get(action, ("Unknown", "غير معروف"))[1 if _is_ar else 0],
            T("Count", "العدد"): count,
        }
        for action, count in sorted(stats["by_action"].items())
    ]
    st.dataframe(pd.DataFrame(action_rows), **full_width(), hide_index=True)

    st.markdown(f"**{T('Filters', 'المرشحات')}**")
    date_range = st.date_input(
        T("Date range (UTC)", "النطاق الزمني (UTC)"),
        value=default_date_range,
        key="audit_date_range",
    )
    filter_cols = st.columns(3)
    with filter_cols[0]:
        role_options = {
            T("All roles", "كل الأدوار"): None,
            T("Teacher", "معلم"): ROLE_TEACHER,
            T("School Admin", "مدير المدرسة"): ROLE_SCHOOL_ADMIN,
            T("Demo Reviewer", "مراجع تجريبي"): ROLE_DEMO_REVIEWER,
        }
        selected_role = st.selectbox(
            T("Role", "الدور"), list(role_options), key="audit_role_filter"
        )
    with filter_cols[1]:
        action_labels = {
            T("All operations", "كل العمليات"): None,
            **{
                _ACTION_LABELS[action][1 if _is_ar else 0]: action
                for action in sorted(ALL_ACTIONS)
            },
        }
        selected_action = st.selectbox(
            T("Operation", "العملية"), list(action_labels), key="audit_action_filter"
        )
    with filter_cols[2]:
        status_labels = {
            T("All statuses", "كل الحالات"): None,
            T("Success", "نجاح"): "success",
            T("Failure", "فشل"): "failure",
        }
        selected_status = st.selectbox(
            T("Status", "الحالة"), list(status_labels), key="audit_status_filter"
        )

    date_from = date_range[0].isoformat() if isinstance(date_range, tuple) and date_range else None
    date_to = date_range[1].isoformat() if isinstance(date_range, tuple) and len(date_range) == 2 else None
    filtered = get_audit_events(
        events,
        actor_role=role_options[selected_role],
        action=action_labels[selected_action],
        status=status_labels[selected_status],
        date_from=date_from,
        date_to=date_to,
    )
    display_rows = list(reversed(_public_events(filtered, _is_ar)))
    st.caption(T(f"{len(display_rows)} matching event(s)", f"{len(display_rows)} حدث مطابق"))
    st.dataframe(
        pd.DataFrame(display_rows),
        **full_width(),
        hide_index=True,
    )
