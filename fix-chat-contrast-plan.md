# SchoolFlow AI — Chat Contrast Fix Plan

## Overview

**Goal:** Fix low-contrast / unreadable text in the SchoolFlow AI chat interface and across the general UI,
particularly assistant message responses appearing pale on light or white backgrounds.

**Scope:** CSS-only additions to `SchoolFlow_AI_MVP/app.py`. No logic, no structure, no refactor.

**Non-goals:** Changing Excel analysis logic, rebuilding any Python functions, altering project structure.

---

## Root Cause Diagnosis

### Primary Cause — No Custom Styling for Streamlit Chat Messages

`st.chat_message()` renders inside Streamlit's internal component DOM, which is **not** covered by any
CSS rule in the current CSS block (lines 22–397 of `app.py`). The text inside chat bubbles inherits
Streamlit's default theme color.

When Streamlit's built-in light theme is active (default), the chat message backgrounds are white/light-gray
and the text color is a **dark** `#262730`. However, with the app background forced to `#F5F6FA` via
`.stApp { background-color: #F5F6FA; }` and no explicit color override for the chat container,
**theme color inheritance can break** — especially if Streamlit injects its own `--text-color` CSS variable
as a light shade (e.g. `rgba(250,250,250,0.6)`) in some rendering contexts.

The `[class*="css"]` rule applies the font but **does not set a text color**, meaning text color is fully
delegated to Streamlit's variable-driven theme engine, which can render pale text on the light background.

### Secondary Causes — Low-Contrast General UI Elements

Several CSS classes use `#9CA3AF` (contrast ratio ~2.9:1 on white) and `#6B7280` (ratio ~4.6:1) which
fail WCAG AA at small font sizes (< 14px):

| CSS Rule | Color Used | Affected Element |
|---|---|---|
| `.sf-metric-label` | `#9CA3AF` | Card labels in metric cards |
| `.sf-quick-sub` | `#9CA3AF` | Quick action card subtitles |
| `.stCaption` | `#9CA3AF` | Chat timestamps |
| `.sf-obs-empty` | `#6B7280` | Observation list placeholder |
| `.sf-topbar-date` | `#6B7280` | Top bar date text |
| `.sf-quick-label` color via quick chips | `#1A2B3C` | (OK, but rendered inside quick-command chip buttons) |

### The `[class*="css"] *` Side-Effect

The CSS rule `[data-testid="stSidebar"] * { color: #ffffff !important; }` forcefully sets ALL sidebar
children to white. This is intentional for the dark-green sidebar, but the broad `*` selector with
`!important` can cascade in unexpected ways in Streamlit's virtual DOM — **overriding descendant text
even in non-sidebar containers** when Streamlit reuses class names.

---

## Sub-Tasks

---

### Sub-Task 1 — Add Chat Message CSS Overrides

**Status:** `[ ] pending`

**Intent:**
Target Streamlit's native chat message containers using their `data-testid` attributes to explicitly set:
- User messages: white background, dark text (`#1A2B3C`)
- Assistant messages: dark green background (`#1B5E4A`), white text (`#FFFFFF`)

This removes the dependency on Streamlit's inherited theme variables for chat content.

**Expected Outcomes:**
- Assistant message bubbles display with a dark green background and clearly readable white text
- User message bubbles display with a white background and dark `#1A2B3C` text
- No regression on the rest of the layout

**Todo List:**
1. Append CSS rules to the existing `<style>` block in `app.py` (before the closing `</style>` tag at line 396)
2. Target `[data-testid="stChatMessage"]` for the container
3. Target assistant role specifically with `[data-testid="stChatMessage"][data-testid*="assistant"]`
   or the attribute `[data-testid="stChatMessage"]:has(img[src*="assistant"])` (check actual DOM attribute)
4. Override `p`, `li`, `strong`, `em`, `code` text colors inside chat containers
5. Ensure `st.caption` timestamps inside assistant bubbles are also readable

**Relevant Context:**
- CSS block: `app.py` lines 22–397 (closing `</style>` at line 396)
- Chat rendering: `app.py` lines 1158–1183 (uses `st.chat_message()`)
- Streamlit's chat DOM attribute: `data-testid="stChatMessageContent"`
- Streamlit role attribute pattern: `[data-testid="stChatMessage"] [class*="assistant"]`

---

### Sub-Task 2 — Fix Low-Contrast Secondary UI Text

**Status:** `[ ] pending`

**Intent:**
Improve contrast for 4 specific CSS classes that use `#9CA3AF` or `#6B7280` at small font sizes,
replacing them with darker values that maintain the visual hierarchy but pass WCAG AA.

**Expected Outcomes:**
- Metric card labels, quick-action subtitles, topbar dates, and empty observation text are all readable
- Visual style remains light/secondary, just with stronger contrast
- No change to primary headings, icons, or structural layout

**Todo List:**
1. In the CSS block, change `.sf-metric-label` color from `#9CA3AF` to `#6B7280`
2. Change `.sf-quick-sub` color from `#9CA3AF` to `#6B7280`
3. Change `.stCaption` forced color from `#9CA3AF` to `#6B7280`
4. Change `.sf-obs-empty` from `#6B7280` to `#4B5563` (darker gray, still secondary)
5. Change `.sf-topbar-date` from `#6B7280` to `#4B5563`

---

### Sub-Task 3 — Validate and Report Changes

**Status:** `[ ] pending`

**Intent:**
Confirm no regressions have been introduced by running the test suite and performing a visual inspection
of the CSS changes. Produce a brief change report.

**Expected Outcomes:**
- All existing tests still pass
- A summary table of changed lines/classes is written back into this plan file

**Todo List:**
1. Run `python -m pytest SchoolFlow_AI_MVP/test_app_logic.py -v` and confirm all tests pass
2. Verify the CSS lines changed in Sub-Task 1 and Sub-Task 2 using a quick `grep` check
3. Update Sub-Task statuses in this plan file to `[x] done`
4. Write the final change report table at the bottom of this file

---

### Sub-Task 4 — Create .streamlit/config.toml to Lock Light Theme

**Status:** `[ ] pending`

**Intent:**
Create a Streamlit theme config file that forces the light theme and sets the primary/text colors
explicitly. This prevents Streamlit from auto-switching to dark mode (which would cause white text on
white background) and ensures CSS variable values are predictable for the chat message overrides.

**Expected Outcomes:**
- `.streamlit/config.toml` exists and contains `[theme]` section with `base = "light"`
- Primary color set to `#1B5E4A`, text color to `#1A2B3C`, background to `#FFFFFF`
- Streamlit's `--text-color` and other CSS variables resolve to dark values consistently

**Todo List:**
1. Create `.streamlit/config.toml` (the template already exists at `.streamlit/secrets.toml.template`)
2. Add `[theme]` section with `base = "light"`, `primaryColor = "#1B5E4A"`, `textColor = "#1A2B3C"`,
   `backgroundColor = "#FFFFFF"`, `secondaryBackgroundColor = "#F5F6FA"`
3. Confirm file is placed at the correct path (workspace root `.streamlit/` directory)

**Relevant Context:**
- Template exists at `.streamlit/secrets.toml.template` — confirms directory exists
- Streamlit reads config.toml from `.streamlit/config.toml` relative to the working directory

---

## Files That Will Change

| File | Lines Affected | Nature of Change |
|---|---|---|
| `SchoolFlow_AI_MVP/app.py` | ~22–397 (CSS block) | Add chat message selectors + fix secondary colors |
| `.streamlit/config.toml` | New file | Lock light theme, set primary/text colors |

**Files NOT touched:** `app_logic.py`, `assistant/*.py`, any test files, project structure.

---

## Change Report

### Files Changed

| File | Change |
|---|---|
| `SchoolFlow_AI_MVP/app.py` | CSS additions + color value updates |
| `.streamlit/config.toml` | New file — light theme lock |

### CSS Lines Modified in `app.py`

| Line | Class / Selector | Before | After | Reason |
|---|---|---|---|---|
| 59 | `.sf-topbar-date` | `#6B7280` | `#4B5563` | Improve contrast on white topbar |
| 177 | `.sf-metric-label` | `#9CA3AF` | `#6B7280` | Fails WCAG AA at 0.76rem on white |
| 251 | `.sf-obs-empty` | `#6B7280` | `#4B5563` | Slightly darker for small text |
| 283 | `.sf-quick-sub` | `#9CA3AF` | `#6B7280` | Fails WCAG AA at 0.72rem on #F5F6FA |
| 388 | `.stCaption` | `#9CA3AF` | `#6B7280` | Chat timestamps were barely visible |
| 400–452 | NEW: Chat message selectors | _(absent)_ | See below | Root cause fix |

### New CSS Block Added (lines 398–453)

- `[data-testid="stChatMessage"]` — universal base: rounded corners, bottom margin
- All `p, li, span, strong, em, a` inside chat: force `#1A2B3C` text (dark, high contrast)
- **User bubble** (`:has([data-testid="stChatMessageAvatarUser"])`): white bg `#ffffff`, dark border
- **Assistant bubble** (`:has([data-testid="stChatMessageAvatarAssistant"])`): dark green bg `#1B5E4A`, white text `#ffffff`
- Assistant `code` spans: semi-transparent bg + gold `#D4A017` text
- Assistant `.stCaption` (timestamp): `rgba(255,255,255,0.70)` — readable on dark green
- Fallback rule for older Streamlit builds: `div[class*="stChatMessage"] { color: #1A2B3C }`

### Root Cause Summary

The `st.chat_message()` component renders inside Streamlit's internal DOM under
`[data-testid="stChatMessage"]` — a container that was not targeted by any of the
existing 375-line CSS block. Text color was inherited from Streamlit's `--text-color`
CSS variable, which in certain rendering contexts resolves to a pale shade when the
app background is overridden to `#F5F6FA` without an explicit `textColor` in the theme
config. Additionally, **no `.streamlit/config.toml`** existed, so Streamlit could freely
switch between light and dark theme, causing `--text-color` to be unpredictable.

### All Tests: PASSED ✅

18 logic tests in `test_app_logic.py` all pass. No code/logic was changed.
