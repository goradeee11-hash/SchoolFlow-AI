"""Shared CSS injection for the SchoolFlow AI Streamlit interface."""

PRIMARY_NAVY = "#102B4E"
ACCENT_LIME = "#B7D957"
WHITE = "#FFFFFF"


def inject_css() -> None:
    """Inject the shared SchoolFlow AI stylesheet into the Streamlit page."""
    import streamlit as st

    st.markdown(_CSS, unsafe_allow_html=True)
    direction = "rtl" if st.session_state.get("ui_lang") == "ar" else "ltr"
    st.markdown(
        f"""
        <style>
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {{
            direction: {direction};
            text-align: start;
            line-height: 1.7;
        }}
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {{
            margin-bottom: 0.65em;
        }}
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:last-child {{
            margin-bottom: 0;
        }}
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code {{
            direction: ltr;
            unicode-bidi: isolate;
        }}
        [data-testid="stChatInputTextArea"] {{
            direction: {direction};
            text-align: start;
        }}
        [data-testid="stDataFrame"] {{
            direction: {direction};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# CSS — Dashboard Design
# Palette: navy, light sky blue, muted lime, and blue-grey borders.
# This module is the source of truth for shared page styling.
# ===========================================================================
_CSS = """
<style>
/* ── Fonts ───────────────────────────────────────────────────────────── */
:root {
    --sf-primary-navy: #102B4E;
    --sf-accent-lime: #B7D957;
    --sf-white: #FFFFFF;
    --sf-surface: #D7E8F2;
    --sf-surface-raised: #C8DFEC;
    --sf-logo-panel: #EAF4FA;
    --sf-border: #A9C0D5;
    --sf-muted: #405D75;
    --sf-font-stack: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, system-ui, sans-serif;
}
html, body, [class*="css"] {
    font-family: var(--sf-font-stack);
}

/* ── App background ──────────────────────────────────────────────────── */
.stApp { background-color: #EAF4FA !important; color: #102B4E; }
[data-testid="stAppViewContainer"],
main#stMain,
section.main,
section.main > div.block-container {
    background: #EAF4FA !important;
    color: #102B4E;
}

/* ── Hide Streamlit chrome ───────────────────────────────────────────── */
#MainMenu, footer { visibility: hidden; }
.stDeployButton, [data-testid="stAppDeployButton"] { display: none; }

/* ── Sidebar — primary navy ─────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #102B4E !important;
    border-inline-end: 2px solid var(--sf-border) !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] [data-testid="stImage"] {
    background: var(--sf-logo-panel);
    border-radius: 10px;
    box-sizing: border-box;
    margin: 1rem auto 0.6rem;
    padding: 5px;
}
[data-testid="stSidebar"] [data-testid="stImage"] img {
    display: block;
    height: auto;
    object-fit: contain;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] * {
    color: #FFFFFF !important;
}
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stSidebar"] div.stButton > button {
    background: #102B4E !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255,255,255,0.28) !important;
    padding: 0.5rem 0.4rem !important;
    justify-content: flex-start !important;
}
[data-testid="stSidebar"] div.stButton > button p,
[data-testid="stSidebar"] div.stButton > button svg {
    color: inherit !important;
    fill: currentColor !important;
}
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
    background: #B7D957 !important;
    color: #102B4E !important;
    border-color: #B7D957 !important;
}
[data-testid="stSidebar"] div.stButton > button[kind="primary"] p {
    color: #102B4E !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background: #1A3A61 !important;
    border-color: var(--sf-border) !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"],
[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
[data-testid="stSidebar"] [data-testid="stSelectbox"] button {
    background: #1A3A61 !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"],
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"] *,
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg {
    color: #FFFFFF !important;
    fill: currentColor !important;
}

/* ── Top bar ─────────────────────────────────────────────────────────── */
.sf-topbar {
    background: var(--sf-surface);
    border-bottom: 1px solid var(--sf-border);
    padding: 0.5rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.2rem;
    /* direction set inline by Python (_topbar_dir) */
}
.sf-topbar-date {
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.82rem; color: var(--sf-muted); font-weight: 500;
}
.sf-topbar-actions {
    display: flex; align-items: center; gap: 0.6rem;
}
.sf-topbar-icon {
    width: 32px; height: 32px;
    border-radius: 8px; border: 1px solid var(--sf-border);
    background: var(--sf-surface-raised);
    color: #102B4E;
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
    background: var(--sf-surface); color: #102B4E;
    border: 1px solid var(--sf-border);
    margin-right: 4px;
}

/* ── Hero banner ─────────────────────────────────────────────────────── */
.sf-hero {
    background: #102B4E;
    border-radius: 16px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    /* direction set inline by Python (_hero_dir) */
    position: relative;
    overflow: hidden;
}
.sf-hero-logo {
    background: var(--sf-logo-panel);
    border-radius: 12px;
    box-sizing: border-box;
    flex: 0 0 180px;
    max-width: 32%;
    padding: 6px;
    position: relative;
    z-index: 2;
}
.sf-hero-logo img {
    display: block;
    height: auto;
    width: 100%;
}
.sf-hero::before {
    content: '';
    position: absolute;
    top: -40px; left: -40px;
    width: 200px; height: 200px;
    background: rgba(183,217,87,0.08);
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
.sf-hero-text { flex: 1; min-width: 0; position: relative; z-index: 2; }
.sf-hero-greeting {
    font-size: 0.85rem; color: #B7D957;
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
    background: rgba(183,217,87,0.18);
    border: 1px solid rgba(183,217,87,0.45);
    border-radius: 12px;
    padding: 0.45rem 0.8rem;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    max-width: 100%;
    position: relative;
    z-index: 2;
}
.sf-hero-badge-icon { font-size: 1.1rem; }
.sf-hero-badge-text {
    font-size: 0.75rem; color: #B7D957;
    font-weight: 600; margin-top: 0.3rem;
}
.st-key-sf-login-brand [data-testid="stImage"] {
    background: transparent;
    box-sizing: border-box;
    margin: 0 auto 1rem;
    padding: 0;
}
.st-key-sf-login-brand [data-testid="stImage"] img {
    display: block;
    height: auto;
    max-width: 100%;
    object-fit: contain;
}
@media (max-width: 768px) {
    .sf-hero {
        align-items: stretch;
        flex-direction: column;
        padding: 1rem;
    }
    .sf-hero-logo {
        align-self: center;
        flex: 0 1 auto;
        max-width: min(100%, 240px);
        width: 100%;
    }
    .sf-hero-badge { align-self: flex-start; }
}

/* ── Metric cards ─────────────────────────────────────────────────────── */
.sf-metrics-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr));
    gap: 1rem;
    margin-bottom: 1.4rem;
    /* direction set inline by Python (_kpi_dir) */
}
.sf-metric-card {
    background: var(--sf-surface);
    border-radius: 14px;
    border: 1px solid var(--sf-border);
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
.sf-icon-gold   { background: rgba(183,217,87,0.18); }
.sf-icon-blue   { background: rgba(16,43,78,0.10); }
.sf-icon-purple { background: rgba(183,217,87,0.18); }
.sf-metric-body { flex: 1; }
.sf-metric-label { font-size: 0.76rem; color: var(--sf-muted); font-weight: 600; margin-bottom: 0.2rem; }
.sf-metric-value { font-size: 1.65rem; font-weight: 900; color: #102B4E; line-height: 1; }
.sf-metric-sub   { font-size: 0.75rem; color: var(--sf-muted); margin-top: 0.25rem; }
.sf-metric-badge-up   { color: #102B4E; font-weight: 700; font-size: 0.75rem; }
.sf-metric-badge-warn { color: #102B4E; font-weight: 700; font-size: 0.75rem; }

/* ── Two-column section ──────────────────────────────────────────────── */
.sf-two-col {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
    gap: 1.2rem;
    margin-bottom: 1.4rem;
}
.sf-two-col-wide { grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); }

/* ── Content cards ───────────────────────────────────────────────────── */
.sf-card {
    background: var(--sf-surface);
    border-radius: 14px;
    border: 1px solid var(--sf-border);
    padding: 1.3rem 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.18);
    /* direction set inline by Python (_dash_dir) */
}
.sf-card-header {
    display: flex; align-items: center; gap: 0.55rem;
    margin-bottom: 1rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--sf-border);
    /* direction inherited from parent .sf-card */
}
.sf-card-header-icon {
    width: 30px; height: 30px;
    border-radius: 8px;
    background: rgba(183,217,87,0.14);
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
    border-bottom: 2px solid var(--sf-border);
    /* direction set inline by Python per section */
}
.sf-section-num {
    background: #102B4E; color: #B7D957;
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
    border-bottom: 1px solid var(--sf-border);
    /* direction inherited from parent .sf-card */
}
.sf-obs-item:last-child { border-bottom: none; }
.sf-obs-code {
    background: #102B4E; color: #FFFFFF;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 8px; border-radius: 5px;
    flex-shrink: 0; margin-top: 1px;
}
.sf-obs-text { font-size: 0.82rem; color: #102B4E; line-height: 1.5; }
.sf-obs-empty { font-size: 0.85rem; color: var(--sf-muted); text-align: center; padding: 1rem 0; }

/* ── Quick actions grid ──────────────────────────────────────────────── */
.sf-quick-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
}
.sf-quick-btn {
    background: var(--sf-surface);
    border: 1px solid var(--sf-border);
    border-radius: 11px;
    padding: 0.85rem 1rem;
    display: flex; align-items: center; gap: 0.7rem;
    cursor: pointer; transition: all 0.18s ease;
    /* direction inherited from page-level direction */
    text-decoration: none;
}
.sf-quick-btn:hover { background: var(--sf-surface-raised); border-color: #B7D957; }
.sf-quick-icon {
    width: 36px; height: 36px; border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; flex-shrink: 0;
}
.sf-qi-green  { background: rgba(16,43,78,0.10); }
.sf-qi-gold   { background: rgba(183,217,87,0.18); }
.sf-qi-blue   { background: rgba(16,43,78,0.10); }
.sf-qi-purple { background: rgba(183,217,87,0.18); }
.sf-quick-label {
    font-size: 0.82rem; font-weight: 700; color: #102B4E;
    line-height: 1.3;
}

.sf-quick-sub { font-size: 0.72rem; color: var(--sf-muted); }

/* ── Upload card ─────────────────────────────────────────────────────── */
.sf-upload-area {
    background: var(--sf-surface);
    border: 2px dashed var(--sf-border);
    border-radius: 14px;
    padding: 1.5rem 1.8rem;
    text-align: center;
    transition: border-color 0.2s;
}
.sf-upload-area:hover { border-color: #B7D957; }

/* ── Status pills ────────────────────────────────────────────────────── */
.sf-pill-ok {
    background: rgba(22,163,74,0.16); color: #102B4E;
    border: 1px solid rgba(22,163,74,0.25);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}
.sf-pill-warn {
    background: rgba(212,160,23,0.16); color: #102B4E;
    border: 1px solid rgba(212,160,23,0.30);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
div.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
    background: #EAF4FA !important;
    color: #102B4E !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(0,0,0,0.18) !important;
    font-family: var(--sf-font-stack) !important;
}
div.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"]:hover {
    background: #D7E8F2 !important;
    transform: translateY(-1px) !important;
}
div.stButton > button {
    background: var(--sf-surface) !important;
    color: #102B4E !important;
    border: 1px solid var(--sf-border) !important;
    border-radius: 9px !important;
    font-family: var(--sf-font-stack) !important;
}
div.stDownloadButton > button {
    background: #EAF4FA !important;
    color: #102B4E !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(0,0,0,0.18) !important;
    font-family: var(--sf-font-stack) !important;
}
div.stDownloadButton > button:hover {
    background: #D7E8F2 !important;
    transform: translateY(-1px) !important;
}

/* ── Dataframe ───────────────────────────────────────────────────────── */
.stDataFrame {
    border-radius: 10px !important;
    border: 1px solid var(--sf-border) !important;
    background: var(--sf-surface) !important;
}

/* ── Selectbox / inputs ──────────────────────────────────────────────── */
.stSelectbox > div > div { border-radius: 9px !important; }
.stFileUploader > div   { border-radius: 9px !important; }
.stTextArea > div > div > textarea {
    border-radius: 9px !important;
    font-family: var(--sf-font-stack) !important;
    font-size: 0.87rem !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
[data-testid="stTextInputRootElement"],
div[data-baseweb="textarea"] > div,
[data-testid="stDateInput"] input,
[data-testid="stTimeInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stChatInputTextArea"] {
    background: var(--sf-surface) !important;
    border-color: var(--sf-border) !important;
    color: #FFFFFF !important;
}
[data-testid="stTextInput"] button {
    background: var(--sf-surface) !important;
    border-color: var(--sf-border) !important;
    color: #FFFFFF !important;
}
[data-testid="stTextInput"] button svg {
    fill: currentColor !important;
}
input::placeholder,
textarea::placeholder,
[data-testid="stChatInputTextArea"]::placeholder {
    color: rgba(255,255,255,0.55) !important;
}

/* ── Expander ────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--sf-surface) !important;
    border: 1px solid var(--sf-border) !important;
    border-radius: 9px !important;
    font-weight: 700 !important; color: #102B4E !important;
    font-family: var(--sf-font-stack) !important;
}
.streamlit-expanderContent {
    background: var(--sf-surface) !important;
    border: 1px solid var(--sf-border) !important;
    border-top: none !important;
    border-radius: 0 0 9px 9px !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
.sf-divider {
    height: 1px;
    background: var(--sf-border);
    margin: 1.6rem 0; border: none;
}

/* ── Footer ──────────────────────────────────────────────────────────── */
.sf-footer {
    text-align: center; padding: 1.4rem 1rem 2rem;
    margin-top: 2.5rem; border-top: 1px solid var(--sf-border);
    color: var(--sf-muted); font-size: 0.76rem;
    /* direction set inline by Python (_footer_dir equivalent) */
}
.sf-footer strong { color: #102B4E; }

/* ── Caption ─────────────────────────────────────────────────────────── */
.stCaption { color: var(--sf-muted) !important; font-size: 0.78rem !important; }

/* ── Sidebar nav item active ─────────────────────────────────────────── */
.sf-nav-item-active {
    background: #B7D957 !important;
    color: #102B4E !important;
    border-radius: 9px;
    font-weight: 700 !important;
}

/* ── Sidebar language toggle: dim the inactive button ───────────────── */
[data-testid="stSidebar"] button[kind="secondary"] {
    opacity: 1 !important;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    opacity: 0.90 !important;
}

/* ── Chat input bottom bar — reduce height, prevent content overlap ──── */
[data-testid="stBottom"] {
    padding-bottom: 0.5rem !important;
    padding-top: 0.5rem !important;
    background: #EAF4FA !important;
    border-top: 1px solid var(--sf-border) !important;
    box-shadow: 0 -2px 12px rgba(0,0,0,0.18) !important;
}
[data-testid="stBottom"] > div {
    padding-bottom: 0.25rem !important;
    max-width: 900px;
    margin: 0 auto;
}
/* Shrink the textarea inside the chat composer */
[data-testid="stChatInputTextArea"] {
    font-size: 0.92rem !important;
    font-family: var(--sf-font-stack) !important;
    min-height: 2.4rem !important;
    max-height: 6rem !important;
    resize: none !important;
    color: #102B4E !important;
}
[data-testid="stChatInputTextArea"]::placeholder {
    color: #526B80 !important;
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
    color: #FFFFFF !important;
}

/* ── USER bubble — raised navy card ─────────────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #23466D !important;
    border: 1.5px solid var(--sf-border) !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.18) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) li,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) strong,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) em,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) a,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div {
    color: #FFFFFF !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) code {
    background: rgba(255,255,255,0.12) !important;
    color: #FFFFFF !important;
    border-radius: 4px; padding: 1px 5px;
}

/* ── ASSISTANT bubble — navy background, pure white text ────────────── */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #1A3A61 !important;
    border: 1.5px solid var(--sf-border) !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2) !important;
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
    background: rgba(183,217,87,0.18) !important;
    color: #FFFFFF !important;
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
    background: #23466D !important;
    border: 1px solid var(--sf-border) !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarAssistant"])) * {
    color: #FFFFFF !important;
}

/* ── App-wide surfaces and readable Streamlit controls ──────────────── */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    background: #EAF4FA !important;
    color: #102B4E !important;
}
main#stMain h1,
main#stMain h2,
main#stMain h3,
main#stMain h4,
main#stMain p,
main#stMain label,
main#stMain legend,
main#stMain [data-testid="stWidgetLabel"],
main#stMain [data-testid="stMarkdownContainer"] {
    color: #102B4E;
}
[data-testid="stAlert"],
[data-testid="stAlertContainer"],
[data-testid="stAlertContentInfo"],
[data-testid="stExpander"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stForm"],
[data-testid="stPopover"] > div {
    background: var(--sf-surface) !important;
    border-color: var(--sf-border) !important;
    color: #102B4E !important;
}
main#stMain [data-baseweb="select"] [role="option"],
main#stMain [data-baseweb="popover"],
main#stMain [data-baseweb="menu"] {
    background: var(--sf-surface-raised) !important;
    color: #102B4E !important;
}
main#stMain [data-baseweb="select"] [aria-selected="true"],
main#stMain [data-baseweb="menu"] [aria-selected="true"] {
    background: #B7D957 !important;
    color: #102B4E !important;
}
main#stMain button[kind="secondary"] {
    background: var(--sf-surface) !important;
    border: 1px solid var(--sf-border) !important;
    color: #102B4E !important;
}
main#stMain [data-testid="stTabs"] button[aria-selected="true"] {
    color: #102B4E !important;
    border-bottom-color: #B7D957 !important;
}
main#stMain [data-testid="stFileUploader"] section {
    background: var(--sf-surface) !important;
    border-color: var(--sf-border) !important;
    color: #102B4E !important;
}
main#stMain [data-testid="stFileUploader"] button {
    background: var(--sf-surface-raised) !important;
    border-color: var(--sf-border) !important;
    color: #102B4E !important;
}
main#stMain [data-testid="stDataFrame"] {
    background: var(--sf-surface) !important;
    --gdg-bg-cell: #EAF4FA;
    --gdg-bg-cell-medium: #D7E8F2;
    --gdg-bg-header: #C8DFEC;
    --gdg-bg-header-has-focus: #C8DFEC;
    --gdg-text-dark: #102B4E;
    --gdg-text-medium: #405D75;
    --gdg-text-light: #526B80;
    --gdg-border-color: #A9C0D5;
}
main#stMain [data-testid="stDataFrame"] canvas {
    background: var(--sf-surface);
}
[data-testid="stBottom"] [data-testid="stChatInput"] {
    background: var(--sf-surface) !important;
    border-color: var(--sf-border) !important;
}
[data-testid="stBottom"] [data-testid="stChatInput"] button {
    background: #EAF4FA !important;
    color: #102B4E !important;
}
@media (max-width: 768px) {
    .sf-metrics-row,
    .sf-two-col,
    .sf-quick-grid {
        grid-template-columns: 1fr !important;
    }
    main#stMain [role="tablist"] {
        flex-wrap: wrap;
        height: auto;
    }
}

/* Shared controls and overlays, including menus rendered outside stMain. */
main#stMain [data-baseweb="input"],
main#stMain [data-baseweb="base-input"],
main#stMain [data-baseweb="select"] > div,
main#stMain [data-baseweb="textarea"],
main#stMain [data-testid="stTextInputRootElement"],
main#stMain [data-testid="stSelectbox"] [role="group"],
main#stMain input,
main#stMain textarea {
    background: #EAF4FA !important;
    color: #102B4E !important;
    border-color: #A9C0D5 !important;
}
main#stMain textarea {
    border-radius: 9px !important;
}
main#stMain [data-testid="stSelectbox"] [role="group"] button {
    background: #EAF4FA !important;
    color: #102B4E !important;
}
main#stMain [data-baseweb="select"] [role="combobox"],
main#stMain [data-baseweb="select"] [role="combobox"] *,
main#stMain [data-baseweb="select"] svg,
main#stMain [data-testid="stTextInput"] button,
main#stMain [data-testid="stTextInput"] button *,
main#stMain [data-testid="stTextInput"] button svg {
    color: #102B4E !important;
    fill: currentColor;
}
main#stMain [data-testid="stTextInput"] button {
    background: #EAF4FA !important;
}
main#stMain input::placeholder,
main#stMain textarea::placeholder {
    color: #526B80 !important;
}
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"],
[role="listbox"][data-rac],
[role="listbox"][data-rac] [role="option"] {
    background: #D7E8F2 !important;
    color: #102B4E !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"],
[role="listbox"][data-rac] [role="option"][data-focused="true"],
[role="listbox"][data-rac] [role="option"][aria-selected="true"] {
    background: #A9C0D5 !important;
    color: #102B4E !important;
}
main#stMain button[kind="primary"] p,
main#stMain button[kind="primaryFormSubmit"] p,
main#stMain [data-testid="stDownloadButton"] button p {
    color: #102B4E !important;
}
main#stMain [data-testid="stDownloadButton"] button {
    background: #EAF4FA !important;
    color: #102B4E !important;
}
main#stMain [data-testid="stDownloadButton"] button:hover {
    background: #D7E8F2 !important;
}
*:focus-visible {
    outline: 2px solid #B7D957 !important;
    outline-offset: 2px;
}
* {
    scrollbar-color: #A9C0D5 #1A3A61;
    scrollbar-width: auto;
}
*::-webkit-scrollbar { width: 12px; height: 12px; }
*::-webkit-scrollbar-track { background: #1A3A61; }
*::-webkit-scrollbar-thumb {
    background: #A9C0D5;
    border: 2px solid #1A3A61;
    border-radius: 8px;
}
</style>
"""
