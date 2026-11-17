"""School administrator controls for the reviewed structure schema."""

import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

from httpx import HTTPError
from postgrest.exceptions import APIError

from shared.i18n import T
from shared.permissions import VIEW_ADMIN_DASHBOARD, require_permission
from shared.supabase_backend import (
    assign_student_to_class,
    classify_legacy_class,
    load_school_structure,
    remove_teaching_assignment,
    save_school_structure_name,
    save_teaching_assignment,
)


def _apply(action, notice):
    try:
        action()
    except (APIError, HTTPError, ValueError) as error:
        st.error(T(f"Operation failed: {error}", f"تعذّر تنفيذ العملية: {error}"))
    else:
        st.session_state["_structure_notice"] = notice
        st.rerun()


def render(client, school_id):
    access = require_permission(st.session_state.get("active_role"), VIEW_ADMIN_DASHBOARD)
    if not access["allowed"]:
        st.error(T(access["reason"], access["reason_ar"]))
        return

    data = load_school_structure(client, school_id)
    notice = st.session_state.pop("_structure_notice", None)
    if notice:
        st.success(notice)
    st.warning(T(
        "Structure management is available, but the educational workspace is not "
        "yet scoped by assignment. Do not use real student data.",
        "إدارة الهيكل متاحة، لكن مساحة العمل التعليمية لم تُعزل حسب التكليف بعد. "
        "لا تستخدم بيانات طلاب حقيقية.",
    ))
    stages = {row["stage_id"]: row["stage_name"] for row in data["stages"]}
    grades = {row["grade_id"]: row for row in data["grades"]}
    classes = {row["class_id"]: row for row in data["classes"]}
    subjects = {row["subject_id"]: row["subject_name"] for row in data["subjects"]}
    teachers = [
        row["user_id"] for row in data["memberships"]
        if row.get("role") == "teacher" and row.get("is_active") is True
    ]

    def grade_label(key):
        grade = grades[key]
        return f"{stages.get(grade['stage_id'], grade['stage_id'])} / {grade['grade_name']}"

    def class_label(key):
        row = classes[key]
        grade_id = row.get("grade_id")
        prefix = grade_label(grade_id) if grade_id in grades else T("Unclassified", "غير مصنف")
        return f"{prefix} / {row['class_name']}"

    labels = {
        "stage": T("Stage", "المرحلة"),
        "grade": T("Grade", "الصف"),
        "class": T("Class", "الفصل"),
        "subject": T("Subject", "المادة"),
    }
    st.subheader(T("School structure", "هيكل المدرسة"))
    kind = st.selectbox(T("Structure type", "نوع العنصر"), list(labels), format_func=labels.get)
    with st.form("structure_create"):
        name = st.text_input(T("New name", "الاسم الجديد"))
        parent = None
        if kind == "grade" and stages:
            parent = st.selectbox(T("Stage", "المرحلة"), list(stages), format_func=stages.get)
        if kind == "class" and grades:
            parent = st.selectbox(T("Grade", "الصف"), list(grades), format_func=grade_label)
        create = st.form_submit_button(T("Create", "إنشاء"))
    if create:
        _apply(
            lambda: save_school_structure_name(client, school_id, kind, name, parent_id=parent),
            T("Created.", "تم الإنشاء."),
        )

    choices = {"stage": stages, "grade": grades, "class": classes, "subject": subjects}[kind]
    if choices and kind != "class":
        formatters = {
            "stage": stages.get, "grade": grade_label,
            "class": class_label, "subject": subjects.get,
        }
        with st.form("structure_rename"):
            record_id = st.selectbox(
                T("Existing item", "العنصر الحالي"), list(choices), format_func=formatters[kind]
            )
            new_name = st.text_input(T("Updated name", "الاسم المعدّل"))
            rename = st.form_submit_button(T("Rename", "تعديل الاسم"))
        if rename:
            _apply(
                lambda: save_school_structure_name(
                    client, school_id, kind, new_name, record_id=record_id
                ),
                T("Name updated.", "تم تعديل الاسم."),
            )
    elif kind == "class":
        st.caption(T(
            "Class renaming is unavailable until the educational workspace uses class IDs.",
            "تعديل اسم الفصل غير متاح حتى تعتمد مساحة العمل التعليمية معرّف الفصل.",
        ))

    unclassified_classes = [key for key, row in classes.items() if not row.get("grade_id")]
    if unclassified_classes and grades:
        with st.form("structure_classify_class"):
            old_class = st.selectbox(
                T("Class needing review", "الفصل الذي يحتاج مراجعة"),
                unclassified_classes, format_func=class_label,
            )
            reviewed_grade = st.selectbox(
                T("Reviewed grade", "الصف بعد المراجعة"), list(grades), format_func=grade_label
            )
            classify = st.form_submit_button(T("Classify class", "تصنيف الفصل"))
        if classify:
            _apply(
                lambda: classify_legacy_class(client, school_id, old_class, reviewed_grade),
                T("Class classified.", "تم تصنيف الفصل."),
            )

    st.subheader(T("Teacher assignments", "تكليفات المعلمين"))
    assignments = [
        (row["class_id"], row["subject_id"], row["teacher_id"])
        for row in data["assignments"]
    ]

    def assignment_label(item):
        class_id, subject_id, teacher_id = item
        return f"{class_label(class_id)} / {subjects.get(subject_id, subject_id)} / {teacher_id}"

    if assignments:
        st.dataframe(
            [{"assignment": assignment_label(item)} for item in assignments],
            hide_index=True,
        )
    classified = [key for key, row in classes.items() if row.get("grade_id") in grades]
    if classified and subjects and teachers:
        previous = st.selectbox(
            T("Assignment to edit", "التكليف المراد تعديله"),
            [None, *assignments],
            format_func=lambda item: (
                T("New assignment", "تكليف جديد") if item is None
                else assignment_label(item)
            ),
        )
        class_index = classified.index(previous[0]) if previous and previous[0] in classified else 0
        subject_ids = list(subjects)
        subject_index = subject_ids.index(previous[1]) if previous and previous[1] in subjects else 0
        teacher_index = teachers.index(previous[2]) if previous and previous[2] in teachers else 0
        with st.form("structure_assignment"):
            selected_class = st.selectbox(
                T("Class", "الفصل"), classified, index=class_index, format_func=class_label
            )
            selected_subject = st.selectbox(
                T("Subject", "المادة"), subject_ids, index=subject_index, format_func=subjects.get
            )
            selected_teacher = st.selectbox(
                T("Teacher ID", "معرّف المعلم"), teachers, index=teacher_index
            )
            save = st.form_submit_button(T("Save assignment", "حفظ التكليف"))
        if save:
            _apply(
                lambda: save_teaching_assignment(
                    client, school_id, selected_class, selected_subject, selected_teacher,
                    previous=previous,
                ),
                T("Assignment saved.", "تم حفظ التكليف."),
            )
    else:
        st.info(T(
            "Add a classified class, subject and active teacher to create assignments.",
            "أضف فصلًا مصنفًا ومادة ومعلمًا نشطًا لإنشاء تكليف.",
        ))
    if assignments:
        with st.form("structure_remove_assignment"):
            removed = st.selectbox(
                T("Assignment to remove", "التكليف المراد إلغاؤه"),
                assignments, format_func=assignment_label,
            )
            remove = st.form_submit_button(T("Remove assignment", "إلغاء التكليف"))
        if remove:
            _apply(
                lambda: remove_teaching_assignment(client, school_id, *removed),
                T("Assignment removed.", "تم إلغاء التكليف."),
            )

    unclassified = [row for row in data["students"] if not row.get("class_id")]
    st.subheader(T("Unclassified students", "الطلاب غير المصنفين"))
    if not unclassified:
        st.info(T("No unclassified students.", "لا يوجد طلاب غير مصنفين."))
    else:
        st.dataframe(unclassified, hide_index=True)
        if classified:
            by_code = {row["student_code"]: row for row in unclassified}
            with st.form("structure_assign_student"):
                code = st.selectbox(T("Student code", "رمز الطالب"), list(by_code))
                student_class = st.selectbox(
                    T("Reviewed class", "الفصل بعد المراجعة"), classified, format_func=class_label
                )
                assign = st.form_submit_button(T("Assign student", "إسناد الطالب"))
            if assign:
                _apply(
                    lambda: assign_student_to_class(
                        client, school_id, code, student_class, only_unclassified=True
                    ),
                    T("Student assigned.", "تم إسناد الطالب."),
                )
