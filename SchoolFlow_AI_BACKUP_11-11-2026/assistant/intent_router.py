"""
intent_router.py
----------------
Rule-based intent detection that works 100% offline (no API needed).

When an LLM client is available it is called first; if unavailable or
failing, this module falls back to keyword/pattern matching.

Returns a structured response ready for the chat UI.
"""

from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Intent patterns
# ---------------------------------------------------------------------------
# Each entry: (intent_key, list-of-regex-patterns, extraction-group-index-or-None)
# Patterns are tried in order; first match wins.
# Extraction group 1 is used to capture student name/code or week number.

_PATTERNS: list[tuple[str, list[str], int | None]] = [
    # ── Greetings ──────────────────────────────────────────────────────────
    ("greeting", [
        r"^(مرحبا|مرحبًا|السلام|اهلا|أهلا|هلا|hi|hello|hey)\b",
        r"^(كيف حالك|كيف الحال|good morning|good afternoon|صباح الخير|مساء الخير)",
    ], None),

    # ── Class-level analysis ───────────────────────────────────────────────
    ("class_analysis", [
        r"(تحليل|ملخص|احصائيات|إحصائيات|نتائج|overview|summary|analysis)\s*(الفصل|الكلاسة|الصف|class|all students)",
        r"(كيف|ماهو|ما هو|ما هي|عرض)\s*(أداء|اداء|حال|performance)\s*(الفصل|الطلاب)",
        r"(class analysis|class summary|show stats|show overview)",
        r"^(تحليل|analyse|analyze|تقرير الفصل|class report)$",
    ], None),

    # ── At-risk students ───────────────────────────────────────────────────
    ("at_risk", [
        r"(من|طلاب|الطلاب).{0,20}(يحتاج|يحتاجون|يحتجن|متابعة|ضعيف|ضعاف|منخفض|at.?risk|follow.?up|need attention)",
        r"(at.?risk|struggling|weak students|متابعة الطلاب|طلاب بحاجة)",
        r"(من الذي|من الطالب).{0,15}(يحتاج|ضعيف|منخفض)",
    ], None),

    # ── Student report ─────────────────────────────────────────────────────
    ("student_report", [
        r"(تقرير|report|ملف|profile)\s+(طالب|student|عن|for|about)?\s*[:\-]?\s*(.+)",
        r"(أرني|عرض|show|get|اعطني|معلومات|info).{0,10}(عن|about|طالب)\s+(.+)",
        r"(تقرير|report)\s+(.+)",
    ], 3),

    # ── Student weekly record ──────────────────────────────────────────────
    ("student_weekly", [
        r"(سجل|اسبوعي|weekly|record|سجلات|تفاصيل)\s*(أسبوعي|اسبوعي|weekly)?\s*(ل|for|عن|about)?\s*(.+)",
        r"(أسابيع|أداء أسبوعي|weekly performance|تاريخ)\s*(طالب)?\s*(.+)",
    ], 4),

    # ── Parent message in English — must come BEFORE the generic parent_message ─
    ("parent_message_en", [
        r"(رسالة|message)\s*(إنجليزي|انجليزي|بالإنجليزية|english|in\s+english)\s*(ل|for|عن)?\s*(.+)",
        r"(english message|رسالة بالإنجليزية)\s*(ل|for)?\s*(.+)",
    ], 4),

    # ── Parent message (Arabic / default) ─────────────────────────────────
    ("parent_message", [
        r"(رسالة|message|راسل|مراسلة)\s*(ولي|وليّ|parent|guardian|أهل)?\s*(أمر|امر)?\s*(ل|of|for|عن|about)?\s*(.+)",
        r"(draft|prepare|جهّز|اعداد)\s*(رسالة|message)\s*(ل|for|about|عن)?\s*(.+)",
        r"(parent\s+message|رسالة ولي الأمر)\s*(ل|for|about)?\s*(.+)",
    ], 5),

    # ── Data quality ───────────────────────────────────────────────────────
    ("data_issues", [
        r"(مشكلات|مشاكل|اخطاء|أخطاء|issues|errors|problems|quality)\s*(البيانات|data|في البيانات)?",
        r"(جودة البيانات|data quality|بيانات مفقودة|missing data|ما المشكلات)",
        r"(فحص|تحقق|check|verify)\s*(البيانات|data)",
    ], None),

    # ── Specific week summary ──────────────────────────────────────────────
    ("week_summary", [
        r"(ملخص|تقرير|summary|نتائج|stats)\s*(الأسبوع|أسبوع|week)\s*(\d+)",
        r"(الأسبوع|أسبوع|week)\s*(\d+)\s*(ملخص|summary|نتائج|تقرير|stats)?",
    ], None),    # week number extracted separately below

    # ── List students ──────────────────────────────────────────────────────
    ("list_students", [
        r"(قائمة|اسماء|أسماء|list|show|عرض)\s*(الطلاب|طلاب|students|all students)",
        r"(كم|عدد|how many)\s*(طالب|students)",
        r"^(الطلاب|students|طلاب|list students)$",
    ], None),

    # ── Excel download ─────────────────────────────────────────────────────
    ("excel_download", [
        r"(تنزيل|تحميل|تصدير|download|export)\s*(excel|ملف|تقرير|report|xlsx)?",
        r"(ملف excel|excel file|download report|تقرير excel)",
    ], None),

    # ── Explain results ────────────────────────────────────────────────────
    ("explain_results", [
        r"(اشرح|explain|فسّر|وضّح|ماذا تعني|what do)\s*(النتائج|نتائج|results|التحليل|analysis)",
        r"(ما معنى|ما تفسير|interpret|help me understand)\s*(النتائج|التحليل|results)",
        r"^(شرح|explain|تفسير|تحليل|interpret)$",
    ], None),

    # ── Help ───────────────────────────────────────────────────────────────
    ("help", [
        r"^(مساعدة|مساعده|help|ماذا تستطيع|ماذا تعرف|what can you do|commands|أوامر)$",
        r"(كيف أستخدم|how to use|ما الأوامر|available commands)",
    ], None),
]


# ---------------------------------------------------------------------------
# Extractor helpers
# ---------------------------------------------------------------------------

def _extract_week(text: str) -> int | None:
    m = re.search(r"\b(\d+)\b", text)
    return int(m.group(1)) if m else None


def _extract_student(text: str, intent: str) -> str:
    """
    Strip intent keywords to isolate the student identifier.
    Returns whatever remains after removing known keywords.
    """
    stopwords = [
        "تقرير", "report", "رسالة", "message", "ولي", "أمر", "امر", "parent",
        "guardian", "سجل", "weekly", "record", "أسبوعي", "اسبوعي", "عن",
        "for", "about", "ل", "طالب", "student", "اعطني", "أرني", "عرض",
        "show", "get", "معلومات", "info", "draft", "prepare", "جهّز", "اعداد",
        "إنجليزي", "انجليزي", "english", "in", "بالإنجليزية", "تفاصيل",
        "أداء", "اداء", "أسبوعي", "أسابيع", "تاريخ", "ملف", "profile",
    ]
    result = text.strip()
    for w in stopwords:
        result = re.sub(rf"\b{re.escape(w)}\b", "", result, flags=re.IGNORECASE)
    return result.strip(" :-،,.")


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def route(user_input: str, lang: str = "ar") -> dict:
    """
    Detect intent from user_input and dispatch to the correct tool function.

    Parameters
    ----------
    user_input : str
        Raw text from the teacher.
    lang : str
        UI language — "en" for English, "ar" (default) for Arabic.
        Controls the language of all response strings.

    Returns
    -------
    dict  {"intent": str, "response": str, "data": any, "ok": bool}
    """
    from assistant.tool_functions import (
        get_class_analysis, find_at_risk_students, get_student_report,
        get_student_weekly, draft_parent_message, get_data_issues,
        get_week_summary, list_students, trigger_excel_download, explain_results,
    )

    text = user_input.strip()
    text_lower = text.lower()

    matched_intent = None
    student_arg    = None
    week_arg       = None

    for intent_key, patterns, _grp in _PATTERNS:
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                matched_intent = intent_key
                if intent_key in (
                    "student_report", "student_weekly",
                    "parent_message", "parent_message_en",
                ):
                    student_arg = _extract_student(text, intent_key)
                if intent_key == "week_summary":
                    week_arg = _extract_week(text)
                break
        if matched_intent:
            break

    # ── Dispatch ──────────────────────────────────────────────────────────
    if matched_intent == "greeting":
        if lang == "en":
            result = {
                "ok": True,
                "message": (
                    "Hello! I'm the SchoolFlow AI Assistant 🎓\n\n"
                    "I can help you with:\n"
                    "- Class performance analysis\n"
                    "- Individual student report\n"
                    "- At-risk students\n"
                    "- Parent message draft\n"
                    "- Data quality issues\n"
                    "- Weekly class summary\n\n"
                    "Type **help** to see all available commands."
                ),
            }
        else:
            result = {
                "ok": True,
                "message": (
                    "مرحبًا! أنا مساعد SchoolFlow AI 🎓\n\n"
                    "يمكنني مساعدتك في:\n"
                    "- تحليل أداء الفصل\n"
                    "- تقرير طالب محدد\n"
                    "- من يحتاج متابعة\n"
                    "- رسالة لولي الأمر\n"
                    "- مشكلات البيانات\n"
                    "- ملخص أسبوع محدد\n\n"
                    "اكتب «مساعدة» لعرض جميع الأوامر."
                ),
            }

    elif matched_intent == "help":
        if lang == "en":
            result = {
                "ok": True,
                "message": (
                    "📖 **Available Commands:**\n\n"
                    "| Command | Example |\n"
                    "|---|---|\n"
                    "| Class analysis | `class analysis` |\n"
                    "| At-risk students | `at-risk students` |\n"
                    "| Student report | `report S01` or `report Ahmed` |\n"
                    "| Weekly record | `weekly S02` |\n"
                    "| Parent message (Arabic) | `رسالة ولي أمر S03` |\n"
                    "| Parent message (English) | `رسالة إنجليزي S01` |\n"
                    "| Data issues | `data issues` |\n"
                    "| Week summary | `week 2 summary` |\n"
                    "| List students | `list students` |\n"
                    "| Download Excel | `download Excel` |\n"
                    "| Explain results | `explain results` |"
                ),
            }
        else:
            result = {
                "ok": True,
                "message": (
                    "📖 **الأوامر المتاحة:**\n\n"
                    "| الأمر | مثال |\n"
                    "|---|---|\n"
                    "| تحليل الفصل | `تحليل الفصل` |\n"
                    "| من يحتاج متابعة | `من يحتاج متابعة؟` |\n"
                    "| تقرير طالب | `تقرير S01` أو `تقرير Ahmed` |\n"
                    "| السجل الأسبوعي | `سجل S02` |\n"
                    "| رسالة ولي الأمر | `رسالة ولي أمر S03` |\n"
                    "| رسالة بالإنجليزية | `رسالة إنجليزي S01` |\n"
                    "| مشكلات البيانات | `مشكلات البيانات` |\n"
                    "| ملخص أسبوع | `ملخص الأسبوع 2` |\n"
                    "| قائمة الطلاب | `قائمة الطلاب` |\n"
                    "| تنزيل Excel | `تنزيل Excel` |\n"
                    "| شرح النتائج | `اشرح النتائج` |"
                ),
            }

    elif matched_intent == "class_analysis":
        result = get_class_analysis(lang=lang)

    elif matched_intent == "at_risk":
        result = find_at_risk_students(lang=lang)

    elif matched_intent == "student_report":
        if not student_arg:
            result = {
                "ok": False,
                "message": (
                    "Please specify the student name or code. Example: `report S01`"
                    if lang == "en" else
                    "يرجى تحديد اسم الطالب أو رمزه. مثال: `تقرير S01`"
                ),
            }
        else:
            result = get_student_report(student_arg, lang=lang)

    elif matched_intent == "student_weekly":
        if not student_arg:
            result = {
                "ok": False,
                "message": (
                    "Please specify the student name or code. Example: `weekly S02`"
                    if lang == "en" else
                    "يرجى تحديد اسم الطالب أو رمزه. مثال: `سجل S02`"
                ),
            }
        else:
            result = get_student_weekly(student_arg, lang=lang)

    elif matched_intent == "parent_message":
        if not student_arg:
            result = {
                "ok": False,
                "message": (
                    "Please specify the student name or code. Example: `رسالة ولي أمر S01`"
                    if lang == "en" else
                    "يرجى تحديد اسم الطالب أو رمزه. مثال: `رسالة ولي أمر S01`"
                ),
            }
        else:
            result = draft_parent_message(student_arg, "العربية", lang=lang)

    elif matched_intent == "parent_message_en":
        if not student_arg:
            result = {
                "ok": False,
                "message": (
                    "Please specify the student name or code. Example: `رسالة إنجليزي S01`"
                    if lang == "en" else
                    "يرجى تحديد اسم الطالب أو رمزه. مثال: `رسالة إنجليزي S01`"
                ),
            }
        else:
            result = draft_parent_message(student_arg, "English", lang=lang)

    elif matched_intent == "data_issues":
        result = get_data_issues(lang=lang)

    elif matched_intent == "week_summary":
        if week_arg is None:
            result = {
                "ok": False,
                "message": (
                    "Please specify a week number. Example: `week 3 summary`"
                    if lang == "en" else
                    "يرجى تحديد رقم الأسبوع. مثال: `ملخص الأسبوع 3`"
                ),
            }
        else:
            result = get_week_summary(week_arg, lang=lang)

    elif matched_intent == "list_students":
        result = list_students(lang=lang)

    elif matched_intent == "excel_download":
        result = trigger_excel_download(lang=lang)

    elif matched_intent == "explain_results":
        result = explain_results(lang=lang)

    else:
        # Unknown intent — never fabricate an answer
        if lang == "en":
            result = {
                "ok": False,
                "message": (
                    "I didn't understand that request 🤔\n\n"
                    "This operation is not currently supported.\n\n"
                    "Try one of these:\n"
                    "- `class analysis`\n"
                    "- `at-risk students`\n"
                    "- `report S01`\n"
                    "- **help** — to see all available commands"
                ),
            }
        else:
            result = {
                "ok": False,
                "message": (
                    "لم أفهم طلبك بدقة 🤔\n\n"
                    "هذه العملية غير مدعومة حالياً.\n\n"
                    "جرّب أحد هذه الأوامر:\n"
                    "- `تحليل الفصل`\n"
                    "- `من يحتاج متابعة؟`\n"
                    "- `تقرير S01`\n"
                    "- `مساعدة` — لعرض جميع الأوامر"
                ),
            }

    return {
        "intent": matched_intent or "unknown",
        "response": result.get("message", ""),
        "data": result.get("data"),
        "ok": result.get("ok", False),
    }
