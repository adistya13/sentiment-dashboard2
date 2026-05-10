from datetime import datetime, timezone
from html import escape
import os
import time

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from database import init_db, get_latest_crawl_time
from timezone_utils import (
    INDONESIA_TIMEZONES,
    browser_offset_to_choice,
    browser_timezone_to_choice,
    get_default_timezone,
    get_timezone_label,
    get_timezone_name,
    parse_dt_with_source_tz,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

init_db()

st.set_page_config(
    page_title="Dashboard Sentimen Twitter",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded"
)

# Initialize timezone selection in session state
if "user_timezone" not in st.session_state:
    st.session_state.user_timezone = get_default_timezone()

if "follow_device_timezone" not in st.session_state:
    st.session_state.follow_device_timezone = True


def _get_query_param(name):
    try:
        value = st.query_params.get(name)
    except Exception:
        value = None

    if isinstance(value, list):
        return value[0] if value else None

    return value


def _get_context_timezone():
    try:
        return st.context.timezone
    except Exception:
        return None


def _get_context_offset():
    try:
        offset = st.context.timezone_offset
    except Exception:
        return None

    if offset is None:
        return None

    try:
        # st.context.timezone_offset follows JavaScript getTimezoneOffset:
        # UTC+8 is -480. The app mapping uses UTC offset minutes: UTC+8 is 480.
        return str(-int(offset))
    except (TypeError, ValueError):
        return None


def _sync_timezone_from_browser():
    browser_timezone = _get_context_timezone() or _get_query_param("browser_tz")
    browser_offset = _get_context_offset() or _get_query_param("browser_offset")
    mapped_timezone = (
        browser_timezone_to_choice(browser_timezone)
        or browser_offset_to_choice(browser_offset)
    )

    st.session_state.browser_timezone = browser_timezone
    st.session_state.browser_offset = browser_offset

    if st.session_state.get("follow_device_timezone", True):
        timezone_choice = mapped_timezone or get_default_timezone()

        if st.session_state.user_timezone != timezone_choice:
            st.session_state.user_timezone = timezone_choice


_sync_timezone_from_browser()

# Determine refresh interval berdasarkan aktivitas crawler
def get_refresh_interval():
    """Refresh lebih cepat jika ada data baru dari crawler"""
    try:
        latest_crawl = get_latest_crawl_time()
        if latest_crawl:
            timezone_choice = st.session_state.get("user_timezone", get_default_timezone())
            latest_time = parse_dt_with_source_tz(
                [latest_crawl],
                timezone_choice,
                os.getenv("APP_TIMEZONE", "Asia/Makassar")
            ).iloc[0]
            now = pd.Timestamp.now(tz=get_timezone_name(timezone_choice)).tz_localize(None)
            time_diff = (now - latest_time).total_seconds()
            # Jika data baru < 5 menit, refresh setiap 30 detik, jika tidak setiap 60 detik
            return 30000 if time_diff < 300 else 60000
    except Exception:
        pass
    return 60000

refresh_interval = get_refresh_interval()

st_autorefresh(
    interval=refresh_interval,
    key="auto_refresh_dashboard"
)


def _check_crawler_alive():
    from datetime import datetime, timedelta, timezone
    from crawler import NRT_INTERVAL_MINUTES, get_crawler_state

    threshold = timedelta(minutes=max((NRT_INTERVAL_MINUTES * 2) + 1, 3))

    def parse_dt(value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    state = get_crawler_state()
    if not state:
        return False

    updated_at = parse_dt(state.get("updated_at"))
    heartbeat_at = parse_dt(state.get("heartbeat_at"))
    now = datetime.now(timezone.utc)

    if (
        state.get("is_running", False)
        and updated_at is not None
        and now - updated_at <= threshold
    ):
        return True

    return (
        state.get("service_active", False)
        and heartbeat_at is not None
        and now - heartbeat_at <= threshold
    )


st.session_state._scheduler_started = _check_crawler_alive()

try:
    from crawler import NRT_INTERVAL_MINUTES
    st.session_state._scheduler_interval = NRT_INTERVAL_MINUTES
except Exception:
    st.session_state._scheduler_interval = 0


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

:root {
    --blue-primary: #3b6cf7;
    --blue-light: #eef2ff;
    --green: #16a34a;
    --red: #ef4444;
    --text: #0f172a;
    --text-secondary: #475569;
    --text-tertiary: #64748b;
    --border: #e2e8f0;
    --bg: #f8fafc;
    --card: #ffffff;
}

/* =========================
   GLOBAL STYLING
========================= */

* {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    box-sizing: border-box;
}

[data-testid="stIconMaterial"],
[data-testid="stIconMaterial"] *,
.material-icons,
.material-symbols-rounded,
.material-symbols-outlined,
.material-symbols-sharp {
    font-family: "Material Symbols Rounded", "Material Icons" !important;
    font-weight: normal !important;
    font-style: normal !important;
    line-height: 1 !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: "liga" !important;
    -webkit-font-smoothing: antialiased !important;
    font-feature-settings: "liga" !important;
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text) !important;
}

[data-testid="stMain"] {
    background: var(--bg) !important;
}

.main > div {
    padding: 1.5rem 2rem !important;
}

/* =========================
   SIDEBAR
========================= */

[data-testid="stSidebar"] {
    background: var(--card) !important;
    box-shadow: 2px 0 8px rgba(15,23,42,0.08) !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding: 1.5rem 1.25rem !important;
}

[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

/* =========================
   BUTTONS & NAVIGATION
========================= */

.stButton > button {
    background: var(--card) !important;
    color: var(--text-tertiary) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 0.75rem 1.25rem !important;
    font-weight: 600 !important;
    font-size: 0.9375rem !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin-bottom: 0.5rem !important;
}

[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    justify-content: flex-start !important;
}

.stButton > button *,
[data-testid="stDownloadButton"] button * {
    color: inherit !important;
    line-height: 1.25 !important;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] * {
    color: #ffffff !important;
}

.stButton > button:hover {
    background: var(--blue-light) !important;
    color: var(--blue-primary) !important;
    border-color: var(--blue-primary) !important;
    box-shadow: 0 4px 12px rgba(59, 108, 247, 0.1) !important;
}

.stButton > button[kind="primary"] {
    background: var(--blue-primary) !important;
    color: #ffffff !important;
    border-color: var(--blue-primary) !important;
    font-weight: 700 !important;
}

.stButton > button[kind="primary"]:hover {
    background: #2d59d1 !important;
    box-shadow: 0 4px 12px rgba(59, 108, 247, 0.2) !important;
}

.stButton > button:disabled,
.stButton > button:disabled * {
    background: #e2e8f0 !important;
    color: var(--text-secondary) !important;
    border-color: #cbd5e1 !important;
    opacity: 1 !important;
}

/* =========================
   HEADERS & TITLES
========================= */

.top-header {
    background: var(--card);
    padding: 1.5rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 8px rgba(15,23,42,0.06);
    display: flex;
    align-items: center;
    gap: 1rem;
}

.top-header * {
    color: var(--text) !important;
}

.page-title {
    font-size: 1.875rem !important;
    font-weight: 800 !important;
    color: var(--text) !important;
    margin: 0 !important;
    line-height: 1.2;
}

h1, h2, h3, h4, h5, h6 {
    color: var(--text) !important;
}

/* =========================
   CARDS & CONTAINERS
========================= */

.card {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(15,23,42,0.06);
    margin-bottom: 1.25rem;
}

.section-header {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 2px 6px rgba(15,23,42,0.07);
}

.section-header-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text) !important;
}

.section-header-subtitle {
    font-size: 0.78rem;
    color: var(--text-tertiary) !important;
    margin-top: 3px;
}

/* =========================
   METRICS & PILLS
========================= */

[data-testid="stMetric"] {
    background: var(--card) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 14px !important;
    padding: 1.25rem !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.05) !important;
}

[data-testid="stMetric"] label,
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] * {
    color: var(--text-secondary) !important;
    font-weight: 700 !important;
    font-size: 0.7875rem !important;
}

[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
    color: var(--text) !important;
    font-weight: 900 !important;
    font-size: 1.75rem !important;
}

/* =========================
   TEXT & CONTENT
========================= */

.stMarkdown {
    color: var(--text) !important;
}

p:not([style]), li:not([style]) {
    color: var(--text-secondary) !important;
    line-height: 1.6 !important;
}

span:not([style]) {
    color: inherit !important;
    line-height: 1.6 !important;
}

.stMarkdown p:not([style]),
.stMarkdown li:not([style]) {
    color: var(--text-secondary) !important;
}

.stMarkdown span:not([style]) {
    color: inherit !important;
}

.stButton > button p,
.stButton > button span,
[data-testid="stDownloadButton"] button p,
[data-testid="stDownloadButton"] button span {
    color: inherit !important;
    line-height: 1.25 !important;
}

/* =========================
   EXPANDERS
========================= */

[data-testid="stExpander"] {
    background: var(--card) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.05) !important;
    overflow: hidden !important;
}

[data-testid="stExpander"] details {
    border: 0 !important;
}

[data-testid="stExpander"] summary {
    background: var(--card) !important;
    min-height: 48px !important;
    padding: 0.75rem 1rem !important;
}

[data-testid="stExpander"] summary:hover {
    background: #f8fafc !important;
}

[data-testid="stExpander"] summary *,
[data-testid="stExpander"] [data-testid="stIconMaterial"] {
    color: var(--text) !important;
}

.stCaption, .stCaptionContainer, .stCaptionContainer * {
    color: var(--text-tertiary) !important;
    font-size: 0.8125rem !important;
}

/* =========================
   DATA & TABLES
========================= */

[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    border: 1px solid var(--border) !important;
    overflow: hidden !important;
}

[data-testid="stDataFrame"] * {
    color: var(--text) !important;
}

/* =========================
   ALERTS & WARNINGS
========================= */

.stAlert {
    border-radius: 12px !important;
    margin-bottom: 1rem !important;
}

.stWarning {
    background-color: #fffbeb !important;
    border-color: #fcd34d !important;
    color: #78350f !important;
}

.stSuccess {
    background-color: #f0fdf4 !important;
    border-color: #86efac !important;
    color: #14532d !important;
}

.stError {
    background-color: #fef2f2 !important;
    border-color: #fecaca !important;
    color: #7f1d1d !important;
}

.stInfo {
    background-color: #f0f9ff !important;
    border-color: #bae6fd !important;
    color: #0c4a6e !important;
}

/* =========================
   FORM ELEMENTS
========================= */

.stTextInput input,
.stDateInput input,
.stSelectbox select,
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input,
[data-baseweb="input"] input {
    background: #ffffff !important;
    border-radius: 10px !important;
    border: 1.5px solid var(--border) !important;
    padding: 0.75rem !important;
    font-size: 0.9375rem !important;
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    caret-color: var(--text) !important;
}

.stTextInput input::placeholder,
.stDateInput input::placeholder,
[data-testid="stTextInput"] input::placeholder,
[data-testid="stDateInput"] input::placeholder {
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
    opacity: 1 !important;
}

[data-baseweb="input"],
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: var(--border) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
}

[data-baseweb="select"] span,
[data-baseweb="select"] div,
[data-baseweb="input"] div {
    color: var(--text) !important;
}

.stTextInput input:focus,
.stSelectbox select:focus,
.stDateInput input:focus,
[data-testid="stTextInput"] input:focus,
[data-testid="stDateInput"] input:focus {
    border-color: var(--blue-primary) !important;
    box-shadow: 0 0 0 3px rgba(59, 108, 247, 0.1) !important;
}

[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] > div > div,
[data-baseweb="popover"] [role="dialog"],
[data-baseweb="menu"],
[data-baseweb="calendar"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: var(--text) !important;
}

[data-baseweb="menu"] *,
[data-baseweb="calendar"] * {
    color: var(--text) !important;
}

[data-baseweb="popover"] * {
    background-color: #ffffff !important;
    color: var(--text) !important;
}

[data-baseweb="popover"] [role="dialog"],
[data-baseweb="popover"] [role="dialog"] > div,
[data-baseweb="popover"] [role="dialog"] > div > div,
[data-baseweb="popover"] [role="grid"],
[data-baseweb="popover"] [role="row"],
[data-baseweb="popover"] [role="gridcell"],
[data-baseweb="popover"] [role="columnheader"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: var(--text) !important;
}

[data-baseweb="calendar"],
[data-baseweb="calendar"] > div,
[data-baseweb="calendar"] div,
[data-baseweb="calendar"] [role="grid"],
[data-baseweb="calendar"] [role="row"],
[data-baseweb="calendar"] [role="columnheader"],
[data-baseweb="calendar"] [role="gridcell"],
[data-baseweb="popover"] [data-baseweb="calendar"],
[data-baseweb="popover"] [data-baseweb="calendar"] div {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: var(--text) !important;
}

[data-baseweb="calendar"] [role="columnheader"],
[data-baseweb="calendar"] [aria-label="Sunday"],
[data-baseweb="calendar"] [aria-label="Monday"],
[data-baseweb="calendar"] [aria-label="Tuesday"],
[data-baseweb="calendar"] [aria-label="Wednesday"],
[data-baseweb="calendar"] [aria-label="Thursday"],
[data-baseweb="calendar"] [aria-label="Friday"],
[data-baseweb="calendar"] [aria-label="Saturday"] {
    color: var(--text-secondary) !important;
    font-weight: 700 !important;
}

[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover {
    background: var(--blue-light) !important;
    color: var(--blue-primary) !important;
}

[data-baseweb="calendar"] button,
[data-baseweb="calendar"] [role="button"],
[data-baseweb="popover"] button,
[data-baseweb="popover"] select {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: var(--text) !important;
}

[data-baseweb="calendar"] [aria-disabled="true"],
[data-baseweb="calendar"] [aria-disabled="true"] * {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}

[data-baseweb="calendar"] [role="gridcell"]:hover,
[data-baseweb="calendar"] button:hover {
    background: var(--blue-light) !important;
    background-color: var(--blue-light) !important;
    color: var(--blue-primary) !important;
}

[data-baseweb="calendar"] [aria-selected="true"],
[data-baseweb="calendar"] [aria-selected="true"] *,
[data-baseweb="calendar"] button[aria-selected="true"],
[data-baseweb="calendar"] button[aria-selected="true"] * {
    background: var(--blue-primary) !important;
    background-color: var(--blue-primary) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* =========================
   PILLS & CUSTOM ELEMENTS
========================= */

.pill-container {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1.25rem;
}

.pill {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 14px;
    padding: 1.25rem;
    text-align: center;
    flex: 1;
    min-width: 200px;
    box-shadow: 0 2px 6px rgba(15,23,42,0.05);
}

/* =========================
   LAYOUT FIX
========================= */

#MainMenu, footer, header {
    visibility: hidden !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

[data-testid="stDownloadButton"] button {
    background: var(--card) !important;
    color: var(--blue-primary) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

[data-testid="stDownloadButton"] button:hover {
    background: var(--blue-light) !important;
    border-color: var(--blue-primary) !important;
}

</style>
""", unsafe_allow_html=True)


if "page" not in st.session_state:
    st.session_state.page = "crawling"

if st.session_state.get("current_page"):
    st.session_state.page = st.session_state.current_page
    st.session_state.scroll_to_top = True
    del st.session_state["current_page"]

if (
    st.session_state.get("scroll_to_top")
    or st.session_state.get("_last_rendered_page") != st.session_state.page
):
    st.session_state.scroll_to_top = False
    st.session_state._last_rendered_page = st.session_state.page


with st.sidebar:

    st.markdown("""
    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.5rem 0.5rem 1.5rem;">
        <div style="width:38px;height:38px;background:linear-gradient(135deg,#3b6cf7,#6389f8);
                    border-radius:10px;display:flex;align-items:center;justify-content:center;
                    font-size:1.1rem;flex-shrink:0;color:white;">📊</div>
        <div>
            <div style="font-size:1rem;font-weight:800;color:#0f172a;line-height:1.2;">SentimenX</div>
            <div style="font-size:0.7rem;color:#94a3b8;font-weight:500;">Twitter Analytics</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sched_ok = st.session_state.get("_scheduler_started", False)
    sched_interval = st.session_state.get("_scheduler_interval", 0)

    sched_color = "#16a34a" if sched_ok else "#f59e0b"

    sched_label = (
        f"Aktif — diperbarui tiap {sched_interval} menit"
        if sched_ok
        else "Nonaktif — jalankan: python3 crawler.py"
    )

    sched_dot = "●" if sched_ok else "○"

    st.markdown(f"""
    <div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:10px;
                padding:0.625rem 0.75rem;margin-bottom:1.25rem;">
        <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:2px;">
            <span style="color:{sched_color};font-size:0.9rem;">{sched_dot}</span>
            <span style="font-size:0.75rem;font-weight:700;color:#334155;">Crawler Service</span>
        </div>
        <div style="font-size:0.7rem;color:#64748b;line-height:1.5;">{sched_label}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tampilkan waktu update terakhir data
    try:
        latest_crawl = get_latest_crawl_time()
        if latest_crawl:
            crawl_dt = parse_dt_with_source_tz(
                [latest_crawl],
                st.session_state.user_timezone,
                os.getenv("APP_TIMEZONE", "Asia/Makassar")
            ).iloc[0]
            tz_label = get_timezone_label(st.session_state.user_timezone)
            update_date = crawl_dt.strftime("%d/%m/%Y")
            update_time = f"{crawl_dt.strftime('%H:%M:%S')} {tz_label}"
            st.markdown(f"""
            <div style="background:#eef2ff;border:1.5px solid #c7d2fe;border-radius:10px;
                        padding:0.625rem 0.75rem;margin-bottom:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#1e3a8a;margin-bottom:2px;">
                    🔄 Update Terbaru</div>
                <div style="font-size:0.7rem;color:#1e40af;line-height:1.5;">
                    {update_date}<br/>{update_time}</div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown("""
    <div style="font-size:0.65rem;font-weight:700;color:#94a3b8;
                letter-spacing:0.08em;text-transform:uppercase;
                padding:0 0.5rem;margin-bottom:0.5rem;">MENU UTAMA</div>
    """, unsafe_allow_html=True)

    current_page = st.session_state.get("page", "crawling")

    nav_items = [
        ("crawling", "🔄  Ambil Data Twitter"),
        ("preprocessing", "🧹  Bersihkan Data"),
        ("sentiment", "📈  Analisis Sentimen"),
    ]

    for page_key, label in nav_items:
        is_active = current_page == page_key

        if st.button(
            label,
            width="stretch",
            type="primary" if is_active else "secondary",
            key=f"nav_{page_key}"
        ):
            st.session_state.page = page_key
            st.session_state.scroll_to_top = True
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Timezone selector
    st.markdown("""
    <div style="font-size:0.65rem;font-weight:700;color:#94a3b8;
                letter-spacing:0.08em;text-transform:uppercase;
                padding:0 0.5rem;margin-bottom:0.5rem;">⏰ ZONA WAKTU</div>
    """, unsafe_allow_html=True)

    follow_device = st.toggle(
        "Ikuti timezone device",
        value=st.session_state.get("follow_device_timezone", True),
        key="follow_device_timezone_toggle",
        help="Jika aktif, dashboard membaca zona waktu dari browser/device."
    )

    if follow_device != st.session_state.follow_device_timezone:
        st.session_state.follow_device_timezone = follow_device

        if follow_device:
            mapped_timezone = (
                browser_timezone_to_choice(
                    st.session_state.get("browser_timezone")
                )
                or browser_offset_to_choice(st.session_state.get("browser_offset"))
            )
            st.session_state.user_timezone = mapped_timezone or get_default_timezone()

        st.rerun()

    timezone_options = list(INDONESIA_TIMEZONES.keys())

    if (
        not st.session_state.follow_device_timezone
        and st.session_state.user_timezone not in timezone_options
    ):
        st.session_state.user_timezone = get_default_timezone()

    if st.session_state.follow_device_timezone:
        raw_detected_tz = st.session_state.get("browser_timezone")
        detected_offset = st.session_state.get("browser_offset")
        detected_tz = raw_detected_tz or (
            "Timezone dari offset browser" if detected_offset else "Belum terdeteksi"
        )
        mapped_timezone = (
            browser_timezone_to_choice(raw_detected_tz)
            or browser_offset_to_choice(detected_offset)
        )
        active_label = mapped_timezone or get_default_timezone()
        st.session_state.user_timezone = active_label
        try:
            offset_minutes = int(detected_offset)
            sign = "+" if offset_minutes >= 0 else "-"
            abs_minutes = abs(offset_minutes)
            offset_label = f"UTC{sign}{abs_minutes // 60:02d}:{abs_minutes % 60:02d}"
        except (TypeError, ValueError):
            offset_label = "offset belum terdeteksi"
        st.caption(f"Device: {detected_tz} · {offset_label} · Aktif: {active_label}")
    else:
        selected_tz = st.selectbox(
            "Pilih zona waktu Indonesia",
            timezone_options,
            index=timezone_options.index(st.session_state.user_timezone),
            label_visibility="collapsed",
            key="tz_selector"
        )

        if selected_tz != st.session_state.user_timezone:
            st.session_state.user_timezone = selected_tz
            st.rerun()

    active_tz_name = get_timezone_name(st.session_state.user_timezone)
    active_now = pd.Timestamp.now(tz=active_tz_name)
    active_clock = active_now.strftime("%d/%m/%Y %H:%M:%S")
    st.markdown(
        f"""
        <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:10px;
                    padding:0.625rem 0.75rem;margin:0.6rem 0 1.25rem;
                    font-family:'Plus Jakarta Sans',sans-serif;">
            <div style="font-size:0.7rem;font-weight:800;color:#334155;margin-bottom:2px;">
                Jam Aktif
            </div>
            <div style="font-size:0.82rem;font-weight:800;color:#0f172a;line-height:1.5;">
                {active_clock}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if (
        st.session_state.follow_device_timezone
        and (
            browser_timezone_to_choice(st.session_state.get("browser_timezone"))
            or browser_offset_to_choice(st.session_state.get("browser_offset"))
        ) is None
        and st.session_state.get("browser_timezone")
    ):
        st.caption("Timezone device belum valid dari browser, memakai default aplikasi.")

    if not st.session_state.follow_device_timezone and selected_tz != st.session_state.user_timezone:
        st.session_state.user_timezone = selected_tz
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    crawler_query = os.getenv(
        "QUERY",
        'komdigi (ongkir OR "gratis ongkir" OR "free ongkir") OR "pembatasan gratis ongkir" OR "gratis ongkir dibatasi"'
    )

    query_terms = [
        term.strip().strip('"')
        for term in crawler_query.split(" OR ")
        if term.strip()
    ]

    query_html = "<br/>".join(
        f"• {escape(term)}" for term in query_terms
    ) or f"• {escape(crawler_query)}"

    st.markdown(f"""
    <div style="background:#f0f4fb;border-radius:12px;padding:1rem;margin-top:auto;">
        <div style="font-size:0.7rem;font-weight:700;color:#0f172a;text-transform:uppercase;
                    letter-spacing:0.06em;margin-bottom:0.625rem;">🔍 Query Crawler Aktif</div>
        <div style="font-size:0.78rem;color:#475569;line-height:1.9;">
            {query_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="font-size:0.68rem;color:#94a3b8;text-align:center;margin-top:1.5rem;
                padding-top:1rem;border-top:1px solid #e2e8f0;line-height:1.6;">
        Data bersumber dari X (Twitter)<br/>via tweet-harvest
    </div>
    """, unsafe_allow_html=True)


from page_modules import crawling_page, preprocessing_page, sentiment_page

if st.session_state.page == "crawling":
    crawling_page.show()

elif st.session_state.page == "preprocessing":
    preprocessing_page.show()

elif st.session_state.page == "sentiment":
    sentiment_page.show()
