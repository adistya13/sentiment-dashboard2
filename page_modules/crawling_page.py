import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from page_modules.table_utils import render_standard_table
from database import engine
from timezone_utils import (
    parse_dt_with_tz,
    parse_dt_with_source_tz,
    get_timezone_label,
    get_timezone_name,
)
from crawler import (
    get_auto_crawl_logs,
    get_crawler_state,
    AUTO_CRAWL_INTERVAL_HOURS,
    NRT_INTERVAL_MINUTES,
    auto_crawl_job,
    activate_nrt_scheduler,
    deactivate_nrt_scheduler,
    is_nrt_enabled,
    ensure_scheduler_running,
)


# ═══════════════════════════════════════════════════════════
#  TIMEZONE & DATETIME HELPERS
# ═══════════════════════════════════════════════════════════

def parse_dt(series):
    return parse_dt_with_tz(
        series,
        st.session_state.get("user_timezone", "WIB (UTC+7)")
    )


def parse_crawled_dt(series):
    return parse_dt_with_source_tz(
        series,
        st.session_state.get("user_timezone", "WIB (UTC+7)"),
        os.getenv("APP_TIMEZONE", "Asia/Jakarta")
    )


def format_dt(value):
    if value is None or pd.isna(value):
        return "Belum ada"
    try:
        if not hasattr(value, "strftime"):
            value = parse_dt(pd.Series([value])).iloc[0]
        if value is None or pd.isna(value):
            return "Belum ada"
        tz_label = get_timezone_label(st.session_state.get("user_timezone", "WIB (UTC+7)"))
        return f"{value.strftime('%d/%m/%Y %H:%M')} {tz_label}"
    except Exception:
        return "Belum ada"


def user_now():
    timezone_choice = st.session_state.get("user_timezone", "WIB (UTC+7)")
    return pd.Timestamp.now(tz=get_timezone_name(timezone_choice)).tz_localize(None)


def user_today():
    return user_now().date()


def format_countdown(delta):
    total_seconds = max(0, int(delta.total_seconds()))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def parse_log_time(value):
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(os.getenv("APP_TIMEZONE", "Asia/Jakarta"))
    return parsed.tz_convert("UTC").to_pydatetime()


def to_user_local_datetime(value):
    if value is None or pd.isna(value):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        return parsed.to_pydatetime() if hasattr(parsed, "to_pydatetime") else parsed
    converted = parse_dt(pd.Series([parsed])).iloc[0]
    if converted is None or pd.isna(converted):
        return None
    return converted.to_pydatetime() if hasattr(converted, "to_pydatetime") else converted


def get_visible_crawl_logs(logs):
    started_at = st.session_state.get("crawl_history_started_at")
    if started_at is None:
        return logs
    started_at = parse_log_time(started_at.isoformat())
    visible = []
    for log in logs:
        log_dt = parse_log_time(log.get("timestamp"))
        if log_dt is not None and log_dt >= started_at:
            visible.append(log)
    return visible


def is_crawler_running():
    state = get_crawler_state()
    updated_at = _parse_state_datetime(state.get("updated_at"))
    if updated_at is None:
        return False
    return (
        state.get("is_running", False)
        and datetime.now(timezone.utc) - updated_at <= _crawler_state_threshold()
    )


def _parse_state_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = pd.Timestamp(parsed).tz_localize(
            os.getenv("APP_TIMEZONE", "Asia/Jakarta")
        ).to_pydatetime()
    return parsed.astimezone(timezone.utc)


def _crawler_state_threshold():
    return timedelta(minutes=max((NRT_INTERVAL_MINUTES * 2) + 1, 3))


def is_crawler_service_active(logs=None):
    state = get_crawler_state()
    threshold = _crawler_state_threshold()
    now = datetime.now(timezone.utc)

    if not state:
        return False

    if is_crawler_running():
        return True

    heartbeat_at = _parse_state_datetime(state.get("heartbeat_at"))
    if (
        state.get("service_active", False)
        and heartbeat_at is not None
        and now - heartbeat_at <= threshold
    ):
        return True

    return False


# ═══════════════════════════════════════════════════════════
#  UI HELPERS
# ═══════════════════════════════════════════════════════════

def _render_crawling_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

.block-container {
    padding-top: 1rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}

.stApp {
    background:
        radial-gradient(circle at top left, #eef4ff 0%, transparent 25%),
        radial-gradient(circle at top right, #f0fdf4 0%, transparent 20%),
        #f8fafc;
}

[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }
header[data-testid="stHeader"] { height: 0 !important; min-height: 0 !important; overflow: visible !important; }

section[data-testid="stMain"] * {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

.crawl-card {
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(226,232,240,0.7);
    border-radius: 20px;
    padding: 1.35rem 1.45rem;
    box-shadow: 0 4px 20px rgba(15,23,42,0.05), 0 1px 3px rgba(15,23,42,0.04);
    margin-bottom: 1.15rem;
    transition: all 0.22s ease;
}

.crawl-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 28px rgba(15,23,42,0.08), 0 2px 8px rgba(15,23,42,0.05);
}

.mode-card {
    transition: all 0.22s ease;
    cursor: pointer;
    backdrop-filter: blur(8px);
}

.mode-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 24px rgba(15,23,42,0.08) !important;
}

.metric-pill {
    border-radius: 14px;
    padding: 1rem 0.9rem;
    text-align: center;
    transition: transform 0.18s ease;
    margin-bottom: 1.2rem;
}
.metric-pill:hover { transform: translateY(-2px); }

.stButton > button {
    border-radius: 12px !important;
    font-weight: 700 !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    border: 1px solid #dbe4f0 !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0.01em !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(59,108,247,0.15) !important;
}

.page-header-card { animation: fadeSlideIn 0.45s ease both; }
@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(-10px); }
    to   { opacity: 1; transform: translateY(0); }
}

@keyframes pulse-green {
    0%,100% { box-shadow: 0 0 0 0 rgba(22,163,74,0.45); }
    50%      { box-shadow: 0 0 0 7px rgba(22,163,74,0); }
}
@keyframes pulse-blue {
    0%,100% { box-shadow: 0 0 0 0 rgba(59,108,247,0.45); }
    50%      { box-shadow: 0 0 0 7px rgba(59,108,247,0); }
}
@keyframes pulse-orange {
    0%,100% { box-shadow: 0 0 0 0 rgba(234,88,12,0.45); }
    50%      { box-shadow: 0 0 0 7px rgba(234,88,12,0); }
}
.pulse-dot-green  { animation: pulse-green  2s ease infinite; }
.pulse-dot-blue   { animation: pulse-blue   2s ease infinite; }
.pulse-dot-orange { animation: pulse-orange 2s ease infinite; }

.monitor-row {
    display: flex; justify-content: space-between;
    align-items: center; gap: 0.75rem;
    padding: 0.65rem 0; border-bottom: 1px solid #f1f5f9;
}
.monitor-row:last-child { border-bottom: none; }
.monitor-label { font-size: 0.78rem; color: #64748b; font-weight: 500; }
.monitor-value { font-size: 0.8rem; font-weight: 700; text-align: right; flex-shrink: 0; }

@keyframes countUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
.stat-num { animation: countUp 0.6s ease both; }

.st-key-custom_date_panel {
    background: #ffffff !important;
    border: 1px solid #e8edf5 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 4px rgba(15,23,42,0.05) !important;
    padding: 1rem 1.15rem 0.95rem !important;
    margin-bottom: 1.15rem !important;
}
.st-key-custom_date_panel [data-testid="stDateInput"] label p {
    color: #64748b !important;
    font-size: 0.7rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.06em !important;
    margin-bottom: 0.35rem !important;
    text-transform: uppercase !important;
}
.st-key-custom_date_panel [data-testid="stDateInput"] input,
.st-key-custom_date_panel [data-baseweb="input"],
.st-key-custom_date_panel [data-baseweb="input"] input {
    background: #f8fafc !important;
    border-color: #e8edf5 !important;
    border-radius: 9px !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    min-height: 44px !important;
}
.st-key-custom_date_panel .stButton > button {
    min-height: 44px !important;
    margin-bottom: 0 !important;
}

.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #e2e8f0 30%, #e2e8f0 70%, transparent);
    margin: 1.5rem 0;
}

/* ── Page Header ph-* classes ── */
.ph-card {
    background: rgba(255,255,255,0.95);
    border: 1px solid #e8edf5;
    border-radius: 20px;
    padding: 1.6rem 1.8rem 1.4rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 2px 12px rgba(15,23,42,0.05);
}
.ph-top {
    display: flex;
    align-items: flex-start;
    gap: 1.1rem;
    margin-bottom: 1.2rem;
}
.ph-icon {
    width: 50px; height: 50px; flex-shrink: 0;
    background: linear-gradient(135deg,#3b6cf7,#6366f1);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem;
    box-shadow: 0 4px 14px rgba(59,108,247,0.25);
}
.ph-title {
    font-size: 1.25rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.02em;
    line-height: 1.3;
}
.ph-desc {
    font-size: 0.82rem;
    color: #64748b;
    line-height: 1.75;
    max-width: 860px;
    margin: 0.4rem 0 0;
}
.ph-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 0.75rem;
}
.ph-tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 999px;
    font-size: 0.71rem;
    font-weight: 700;
    border: 1px solid;
}
.ph-divider {
    height: 1px;
    background: #f1f5f9;
    margin: 1.1rem 0;
}
.ph-chips {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 1.1rem;
}
.ph-chip {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #f8fafc;
    border: 1px solid #e8edf5;
    border-radius: 12px;
    padding: 10px 12px;
}
.ph-chip-icon { font-size: 1.1rem; flex-shrink: 0; }
.ph-chip-label {
    font-size: 0.6rem;
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 2px;
}
.ph-chip-value { font-size: 0.8rem; font-weight: 700; color: #1e293b; }

/* ── Activation Gate ── */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
.activation-panel { animation: fadeIn 0.4s ease both; }

/* ── Active Strip ── */
.active-strip {
    background: linear-gradient(135deg, #f0fdf4, #dcfce7);
    border: 1px solid #86efac;
    border-radius: 14px;
    padding: 0.85rem 1.15rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 8px rgba(22,163,74,0.08);
}
</style>
""", unsafe_allow_html=True)


def _gap(size="md"):
    heights = {"xs": 6, "sm": 12, "md": 20, "lg": 32}
    h = heights.get(size, 20)
    st.markdown(f'<div style="height:{h}px;"></div>', unsafe_allow_html=True)


def _divider():
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def _section_header(title, subtitle=""):
    sub_html = (
        f'<p style="font-size:0.74rem;color:#64748b;margin:3px 0 0;line-height:1.5;">{subtitle}</p>'
        if subtitle else ""
    )
    st.markdown(f"""
<div style="background:rgba(255,255,255,0.85);backdrop-filter:blur(10px);
border:1px solid #e8edf5;border-radius:16px;padding:0.9rem 1.2rem;
margin-bottom:1rem;box-shadow:0 2px 10px rgba(15,23,42,0.04);">
    <p style="font-size:0.95rem;font-weight:800;color:#0f172a;margin:0;">{title}</p>
    {sub_html}
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  PAGE HEADER
# ═══════════════════════════════════════════════════════════

def _render_page_header():
    nrt = str(NRT_INTERVAL_MINUTES)

    st.markdown(f"""
<div class="ph-card">
<div class="ph-top">
<div class="ph-icon">&#128038;</div>
<div style="flex:1;min-width:0;">
<div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.45rem;">
<span class="ph-title">Crawling Data Twitter &mdash; Komdigi &amp; Isu Ongkir</span>
<span style="background:#dcfce7;border:1px solid #86efac;border-radius:999px;padding:4px 12px;font-size:0.68rem;font-weight:700;color:#15803d;display:inline-flex;align-items:center;gap:5px;white-space:nowrap;"><span class="pulse-dot-green" style="width:7px;height:7px;border-radius:50%;background:#16a34a;display:inline-block;"></span>Live Monitor</span>
</div>
<p class="ph-desc">Sistem ini memantau opini masyarakat Twitter/X mengenai <strong style="color:#334155;">kebijakan pembatasan gratis ongkir</strong> oleh <strong style="color:#334155;">Komdigi</strong>. Tweet dikumpulkan otomatis, dibersihkan melalui preprocessing Bahasa Indonesia, lalu dianalisis menggunakan model <strong style="color:#334155;">Naive Bayes</strong> untuk menentukan sentimen (<em>positif, negatif, atau netral</em>) secara near-realtime.</p>
<div class="ph-tags" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:0.75rem;">
<span class="ph-tag" style="background:#eef2ff;color:#3b6cf7;border-color:#c7d2fe;">&#128225; Auto Crawling</span>
<span class="ph-tag" style="background:#f0fdf4;color:#15803d;border-color:#bbf7d0;">&#129302; Naive Bayes</span>
<span class="ph-tag" style="background:#fff7ed;color:#c2410c;border-color:#fdba74;">&#9889; Near Realtime</span>
<span class="ph-tag" style="background:#f5f3ff;color:#7c3aed;border-color:#ddd6fe;">&#128202; Dashboard Monitoring</span>
</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

    st.markdown(f"""
<div class="ph-card" style="margin-top:-0.8rem;">
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
<div class="ph-chip"><span class="ph-chip-icon">&#128260;</span><div><div class="ph-chip-label">Interval Crawling</div><div class="ph-chip-value">Setiap {nrt} menit</div></div></div>
<div class="ph-chip"><span class="ph-chip-icon">&#128197;</span><div><div class="ph-chip-label">Jangkauan Data</div><div class="ph-chip-value">7 hari terakhir</div></div></div>
<div class="ph-chip"><span class="ph-chip-icon">&#128451;</span><div><div class="ph-chip-label">Penyimpanan</div><div class="ph-chip-value">Database lokal</div></div></div>
<div class="ph-chip"><span class="ph-chip-icon">&#129302;</span><div><div class="ph-chip-label">Model Prediksi</div><div class="ph-chip-value">Naive Bayes</div></div></div>
</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="ph-card" style="margin-top:-0.8rem;">
<div style="display:flex;flex-direction:column;align-items:center;gap:10px;">
<div style="display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;">
<span style="font-size:0.62rem;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:0.07em;margin-right:4px;">&#128269; Query</span>
<span style="background:#eef2ff;color:#3b6cf7;border:1px solid #c7d2fe;border-radius:999px;padding:4px 13px;font-size:0.72rem;font-weight:700;">komdigi</span>
<span style="background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;border-radius:999px;padding:4px 13px;font-size:0.72rem;font-weight:700;">gratis ongkir</span>
<span style="background:#fef3c7;color:#b45309;border:1px solid #fde68a;border-radius:999px;padding:4px 13px;font-size:0.72rem;font-weight:700;">free ongkir</span>
<span style="background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;border-radius:999px;padding:4px 13px;font-size:0.72rem;font-weight:700;">pembatasan ongkir</span>
</div>
<div style="display:flex;align-items:center;justify-content:center;gap:4px;flex-wrap:wrap;">
<span style="font-size:0.62rem;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:0.07em;margin-right:4px;">&#9881; Alur kerja</span>
<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:5px 12px;font-size:0.71rem;color:#475569;font-weight:600;white-space:nowrap;">&#128038; Crawling tweet</span>
<span style="color:#cbd5e1;font-size:0.8rem;">&#8594;</span>
<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:5px 12px;font-size:0.71rem;color:#475569;font-weight:600;white-space:nowrap;">&#128451; Simpan ke database</span>
<span style="color:#cbd5e1;font-size:0.8rem;">&#8594;</span>
<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:5px 12px;font-size:0.71rem;color:#475569;font-weight:600;white-space:nowrap;">&#9985; Preprocessing teks</span>
<span style="color:#cbd5e1;font-size:0.8rem;">&#8594;</span>
<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:5px 12px;font-size:0.71rem;color:#475569;font-weight:600;white-space:nowrap;">&#129302; Prediksi sentimen</span>
<span style="color:#cbd5e1;font-size:0.8rem;">&#8594;</span>
<span style="display:inline-flex;align-items:center;gap:4px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:5px 12px;font-size:0.71rem;color:#475569;font-weight:600;white-space:nowrap;">&#128202; Visualisasi hasil</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  NRT ACTIVATION GATE
# ═══════════════════════════════════════════════════════════
def _render_activation_gate():
    items = [
        f'Scheduler berjalan setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong> di background',
        'Mencakup tweet dalam <strong>7 hari terakhir</strong>',
        'Tweet baru otomatis tersimpan ke database lokal',
        'Crawl pertama dimulai <strong>segera</strong> setelah tombol diklik',
    ]

    grid_rows = ""
    for item in items:
        grid_rows += (
            '<div style="display:flex;align-items:flex-start;gap:0.5rem;">'
            '<span style="color:#16a34a;font-weight:700;flex-shrink:0;margin-top:1px;">\u2713</span>'
            f'<span style="font-size:0.74rem;color:#44403c;line-height:1.55;">{item}</span>'
            '</div>'
        )

    html = (
        '<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border:1.5px solid #fde68a;border-radius:20px;padding:2rem 2rem 1.6rem;margin-bottom:1rem;box-shadow:0 4px 24px rgba(234,179,8,0.1);">'
        '<div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.4rem;">'
        '<div style="width:48px;height:48px;background:linear-gradient(135deg,#f59e0b,#d97706);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;flex-shrink:0;box-shadow:0 4px 14px rgba(245,158,11,0.3);">\u26a1</div>'
        '<div>'
        '<div style="font-size:1rem;font-weight:800;color:#78350f;letter-spacing:-0.01em;">Pengambilan Data Otomatis Belum Aktif</div>'
        f'<div style="font-size:0.75rem;color:#92400e;font-weight:500;margin-top:3px;line-height:1.5;">Aktifkan untuk mulai crawling tweet secara near-realtime setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong>.</div>'
        '</div>'
        '</div>'
        '<div style="background:rgba(255,255,255,0.65);border:1px solid #fde68a;border-radius:12px;padding:1rem 1.15rem;margin-bottom:1.25rem;">'
        '<div style="font-size:0.67rem;font-weight:800;color:#b45309;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.75rem;">Yang akan terjadi setelah aktivasi</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.55rem 1.5rem;">'
        + grid_rows +
        '</div>'
        '</div>'
        '<div style="background:rgba(255,255,255,0.45);border:1px dashed #fbbf24;border-radius:10px;padding:0.65rem 1rem;">'
        '<span style="font-size:0.7rem;color:#78350f;font-weight:500;line-height:1.65;">'
        '\U0001f4a1 <strong>Catatan:</strong> Crawling aktif selama sesi aplikasi berjalan. '
        'Data historis tetap tersimpan dan bisa dilihat di mode <em>7 Hari</em> atau <em>30 Hari</em> tanpa perlu mengaktifkan crawling.'
        '</span>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    col_l, col_btn, col_r = st.columns([1, 2, 1])
    with col_btn:
        if st.button(
            "\u26a1 Aktifkan Pengambilan Data Secara Otomatis",
            type="primary",
            use_container_width=True,
            key="btn_activate_nrt",
        ):
            st.session_state.nrt_activated = True
            st.session_state.nrt_explicitly_deactivated = False   # ← RESET FLAG
            st.session_state.crawl_history_started_at = datetime.now(tz=timezone.utc)
            activate_nrt_scheduler()
            st.success("\u2705 Crawling otomatis berhasil diaktifkan! Crawl pertama akan segera dimulai.")
            time.sleep(1.0)
            st.rerun()

    _gap("md")


# ═══════════════════════════════════════════════════════════
#  ACTIVE STRIP (setelah diaktifkan)
# ═══════════════════════════════════════════════════════════
def _render_active_strip():
    col_info, col_btn = st.columns([3, 1], gap="medium")

    with col_info:
        st.markdown(f"""
<div class="active-strip">
    <div class="pulse-dot-green"
         style="width:10px;height:10px;background:#16a34a;border-radius:50%;flex-shrink:0;"></div>
    <div>
        <span style="font-size:0.8rem;font-weight:700;color:#15803d;">
            Crawling Otomatis Aktif
        </span>
        <span style="font-size:0.7rem;color:#166534;margin-left:0.5rem;">
            &mdash; berjalan setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong> di background
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

    with col_btn:
        _gap("xs")
        if st.button(
            "⏹ Nonaktifkan",
            type="secondary",
            use_container_width=True,
            key="btn_deactivate_nrt",
        ):
            # Set semua flag nonaktif
            st.session_state.nrt_activated = False
            st.session_state.nrt_explicitly_deactivated = True   # ← FLAG BARU
            st.session_state.pop("crawl_history_started_at", None)
            deactivate_nrt_scheduler()
            st.warning("⏹ Crawling otomatis dihentikan untuk sesi ini.")
            time.sleep(0.9)
            st.rerun()
# ═══════════════════════════════════════════════════════════
#  NRT STATUS BANNER
# ═══════════════════════════════════════════════════════════

def _render_nrt_status_banner(sched_ok):
    if sched_ok:
        bg        = "linear-gradient(135deg,#f0fdf4,#dcfce7)"
        bdr       = "#86efac"
        dot_cls   = "pulse-dot-green"
        dot_color = "#16a34a"
        badge_bg  = "#dcfce7"
        badge_c   = "#15803d"
        title     = "Crawler Service Aktif"
        desc      = (
            f"Sistem berjalan otomatis di background setiap "
            f"<strong>{NRT_INTERVAL_MINUTES} menit</strong>. "
            f"Data mencakup <strong>7 hari terakhir</strong> berdasarkan tanggal asli tweet."
        )
        badge = "&#9679; LIVE"
    else:
        bg        = "linear-gradient(135deg,#eff6ff,#dbeafe)"
        bdr       = "#93c5fd"
        dot_cls   = "pulse-dot-blue"
        dot_color = "#3b6cf7"
        badge_bg  = "#dbeafe"
        badge_c   = "#1d4ed8"
        title     = "Crawler Siap Dijalankan"
        desc      = (
            f"Scheduler otomatis aktif setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong> "
            f"sejak diaktifkan &mdash; tidak perlu terminal terpisah."
        )
        badge = "&#9900; STANDBY"

    st.markdown(f"""
<div style="background:{bg};border:1px solid {bdr};border-radius:14px;
            padding:1rem 1.3rem;margin-bottom:1rem;
            display:flex;align-items:center;gap:1rem;
            box-shadow:0 2px 8px rgba(15,23,42,0.04);">
    <div class="{dot_cls}"
         style="width:12px;height:12px;background:{dot_color};
                border-radius:50%;flex-shrink:0;"></div>
    <div style="flex:1;">
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem;">
            <span style="font-size:0.85rem;font-weight:700;color:#0f172a;">{title}</span>
            <span style="background:{badge_bg};color:{badge_c};font-size:0.62rem;
                         font-weight:800;padding:0.18rem 0.55rem;border-radius:999px;
                         letter-spacing:0.06em;">{badge}</span>
        </div>
        <div style="font-size:0.76rem;color:#475569;line-height:1.6;">{desc}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  MONITORING PANEL
# ═══════════════════════════════════════════════════════════

def _render_monitoring_panel(last_log, last_dt, sched_ok):
    now = user_now()

    try:
        df_stats = pd.read_sql("SELECT crawled_at FROM tweets", engine)
        if not df_stats.empty:
            df_stats["crawled_at"] = parse_crawled_dt(df_stats["crawled_at"])
        total_db    = len(df_stats)
        today_start = pd.Timestamp(now.date())
        tweet_today = (
            len(df_stats[df_stats["crawled_at"] >= today_start])
            if not df_stats.empty else 0
        )
        latest_crawled = df_stats["crawled_at"].max() if not df_stats.empty else None
    except Exception:
        total_db       = 0
        tweet_today    = 0
        latest_crawled = None

    last_log_dt = last_dt
    if last_log_dt is None and last_log:
        last_log_dt = parse_log_time(last_log.get("timestamp"))

    final_last_dt = to_user_local_datetime(last_log_dt)
    if final_last_dt is None:
        final_last_dt = to_user_local_datetime(latest_crawled)

    last_crawl_str      = "Belum pernah"
    next_crawl_str      = "Belum terjadwal"
    countdown_str       = "Menunggu crawl pertama..."
    monitoring_time_str = format_dt(now)

    if final_last_dt is not None:
        next_dt   = final_last_dt + timedelta(minutes=NRT_INTERVAL_MINUTES)
        remaining = next_dt - now
        last_crawl_str = format_dt(final_last_dt)
        next_crawl_str = format_dt(next_dt)
        if remaining.total_seconds() > 0:
            countdown_str = format_countdown(remaining)
        elif is_crawler_running():
            countdown_str = "Sedang crawling..."
        else:
            countdown_str = "Segera diperbarui..."

    status_text  = "Aktif Otomatis" if sched_ok else "Standby"
    status_color = "#16a34a"        if sched_ok else "#3b6cf7"
    status_bg    = "#dcfce7"        if sched_ok else "#dbeafe"

    note_text   = f"{tweet_today:,} tweet masuk hari ini" if tweet_today > 0 else "Belum ada tweet baru hari ini"
    note_bg     = "#f0fdf4" if tweet_today > 0 else "#f8fafc"
    note_border = "#bbf7d0" if tweet_today > 0 else "#e8edf5"
    note_color  = "#166534" if tweet_today > 0 else "#64748b"

    _section_header("&#128225; Status Monitoring Sistem", "Pembaruan data near-realtime &middot; interval otomatis")

    col_a, col_b = st.columns(2, gap="medium")

    left_rows = [
        ("Interval crawling",  f"{NRT_INTERVAL_MINUTES} menit", "#3b6cf7"),
        ("Jangkauan data",     "7 hari terakhir",                "#3b6cf7"),
        ("Waktu monitoring",   monitoring_time_str,              "#64748b"),
        ("Last crawl",         last_crawl_str,                   "#0f172a"),
        ("Next crawl",         next_crawl_str,                   "#0f172a"),
        ("Countdown",          countdown_str,                    "#16a34a"),
    ]

    rows_html_a = ""
    for i, (label, value, vc) in enumerate(left_rows):
        border = "none" if i == len(left_rows) - 1 else "1px solid #f1f5f9"
        rows_html_a += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:0.6rem 0;border-bottom:{border};">'
            f'<span style="font-size:0.77rem;color:#64748b;font-weight:500;">{label}</span>'
            f'<span style="font-size:0.78rem;font-weight:700;color:{vc};'
            f'text-align:right;flex-shrink:0;max-width:58%;">{value}</span>'
            f'</div>'
        )

    with col_a:
        st.markdown(
            f'<div class="crawl-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.9rem;">'
            f'<span style="font-size:0.71rem;font-weight:800;color:#94a3b8;'
            f'letter-spacing:0.07em;text-transform:uppercase;">Sistem Crawling</span>'
            f'<span style="background:{status_bg};color:{status_color};font-size:0.68rem;'
            f'font-weight:700;padding:0.22rem 0.7rem;border-radius:999px;">{status_text}</span>'
            f'</div>'
            f'{rows_html_a}'
            f'</div>',
            unsafe_allow_html=True,
        )

    right_rows = [
        ("Update terakhir",      last_crawl_str,           "#0f172a"),
        ("Countdown berikutnya", countdown_str,             "#16a34a"),
        ("Tweet masuk hari ini", f"{tweet_today:,} tweet",  "#3b6cf7"),
        ("Total dataset",        f"{total_db:,} tweet",     "#0f172a"),
    ]

    rows_html_b = ""
    for i, (label, value, vc) in enumerate(right_rows):
        border = "none" if i == len(right_rows) - 1 else "1px solid #f1f5f9"
        rows_html_b += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:0.6rem 0;border-bottom:{border};">'
            f'<span style="font-size:0.77rem;color:#64748b;font-weight:500;">{label}</span>'
            f'<span style="font-size:0.78rem;font-weight:700;color:{vc};'
            f'text-align:right;flex-shrink:0;max-width:58%;">{value}</span>'
            f'</div>'
        )

    with col_b:
        st.markdown(
            f'<div class="crawl-card">'
            f'<div style="font-size:0.71rem;font-weight:800;color:#94a3b8;'
            f'letter-spacing:0.07em;text-transform:uppercase;margin-bottom:0.9rem;">'
            f'Ringkasan Dataset</div>'
            f'{rows_html_b}'
            f'<div style="margin-top:0.9rem;background:{note_bg};border:1px solid {note_border};'
            f'border-radius:10px;padding:0.7rem 0.85rem;font-size:0.76rem;'
            f'font-weight:700;color:{note_color};">{note_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════
#  METRICS ROW
# ═══════════════════════════════════════════════════════════

def _render_metrics(total, days, earliest, latest, filter_label, basis_label):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.5rem;margin:0.2rem 0 1.1rem;">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:20px;height:20px;background:#eef2ff;border-radius:5px;font-size:0.75rem;">&#128260;</span>'
        f'<span style="font-size:0.78rem;color:#64748b;">'
        f'Data aktif: <strong style="color:#334155;">{filter_label}</strong>'
        f'&nbsp;&middot;&nbsp; {basis_label}'
        f'</span></div>',
        unsafe_allow_html=True,
    )

    pills = [
        ("&#128202;", "linear-gradient(135deg,#eef2ff,#e0e7ff)", "#3b6cf7", "#1e3a8a", "#dbeafe",
         "Total Tweet", f"{total:,}", "Terkumpul periode ini"),
        ("&#128197;", "linear-gradient(135deg,#f0fdf4,#dcfce7)", "#16a34a", "#14532d", "#bbf7d0",
         "Rentang Waktu", f"{days} Hari", basis_label),
        ("&#128199;", "linear-gradient(135deg,#fff7ed,#ffedd5)", "#ea580c", "#7c2d12", "#fed7aa",
         "Mulai Dari", earliest, "Tanggal awal"),
        ("&#128198;", "linear-gradient(135deg,#fefce8,#fef9c3)", "#ca8a04", "#713f12", "#fde68a",
         "Sampai Dengan", latest, "Tanggal akhir"),
    ]

    c1, c2, c3, c4 = st.columns(4)
    for col, (icon, bg, color, dark, border_c, label, val, sub) in zip([c1, c2, c3, c4], pills):
        with col:
            fs = "1.45rem" if len(str(val)) > 10 else "2rem"
            st.markdown(
                f'<div class="metric-pill" style="background:{bg};border:1px solid {border_c};'
                f'box-shadow:0 2px 10px {color}18;">'
                f'<div style="width:36px;height:36px;background:{color};border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:0.95rem;margin:0 auto 0.65rem;'
                f'box-shadow:0 4px 10px {color}44;">{icon}</div>'
                f'<div style="font-size:0.62rem;font-weight:800;color:{color};'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.3rem;">{label}</div>'
                f'<div class="stat-num" style="font-size:{fs};font-weight:800;color:{dark};'
                f'line-height:1.15;margin-bottom:0.25rem;">{val}</div>'
                f'<div style="font-size:0.66rem;color:{color};font-weight:600;opacity:0.85;">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════
#  CHARTS
# ═══════════════════════════════════════════════════════════

def _render_charts(df, filter_label, date_col, chart_label, dt_start, dt_end):
    df_tl = df.copy().dropna(subset=[date_col])
    if df_tl.empty:
        st.info("Belum ada data valid untuk grafik.")
        return

    df_tl["date_key"] = df_tl[date_col].dt.strftime("%Y-%m-%d")
    actual_daily = (
        df_tl.groupby("date_key").size().reset_index(name="count").sort_values("date_key")
    )

    date_range = pd.date_range(
        pd.Timestamp(dt_start).date(),
        pd.Timestamp(dt_end).date(),
        freq="D"
    )
    daily = pd.DataFrame({
        "date_key": date_range.strftime("%Y-%m-%d"),
        "date_str": date_range.strftime("%d %b"),
    }).merge(actual_daily, on="date_key", how="left")
    daily["count"] = daily["count"].fillna(0).astype(int)

    ordered    = daily["date_str"].tolist()
    counts_day = daily["count"].tolist()
    active_days   = int((daily["count"] > 0).sum())
    inactive_days = len(daily) - active_days
    total_days    = len(daily)
    total_tweets  = int(daily["count"].sum())

    max_cnt = int(daily["count"].max()) if daily["count"].max() > 0 else 0
    nonzero = daily[daily["count"] > 0]
    min_cnt = int(nonzero["count"].min()) if not nonzero.empty else 0

    busiest_list  = daily[daily["count"] == max_cnt]["date_str"].tolist() if max_cnt > 0 else []
    quietest_list = nonzero[nonzero["count"] == min_cnt]["date_str"].tolist() if min_cnt > 0 else []

    bar_colors = []
    for c in counts_day:
        if c == 0:
            bar_colors.append("#e2e8f0")
        elif max_cnt > 0 and c == max_cnt:
            bar_colors.append("#1d4ed8")
        elif min_cnt > 0 and c == min_cnt and min_cnt != max_cnt:
            bar_colors.append("#a78bfa")
        else:
            bar_colors.append("#3b6cf7")

    max_y       = max(counts_day) if any(c > 0 for c in counts_day) else 1
    y_range_top = max_y * 1.3

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=ordered, y=counts_day,
        marker=dict(color=bar_colors, opacity=0.10, line=dict(width=0), cornerradius=8),
        width=0.68, showlegend=False, hoverinfo="skip",
    ))
    fig_bar.add_trace(go.Bar(
        x=ordered, y=counts_day,
        marker=dict(color=bar_colors, opacity=0.93, line=dict(width=0), cornerradius=8),
        width=0.46,
        hovertemplate="<b>%{x}</b><br><b>%{y:,}</b> tweet<extra></extra>",
        text=[f"<b>{c}</b>" if c > 0 else "" for c in counts_day],
        textposition="outside",
        textfont=dict(size=10, color="#475569"),
        cliponaxis=False, showlegend=False,
    ))
    fig_bar.update_layout(
        height=280, barmode="overlay",
        margin=dict(l=0, r=4, t=8, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            type="category", categoryorder="array", categoryarray=ordered,
            tickfont=dict(size=10, color="#94a3b8"),
            showgrid=False, zeroline=False, showline=False,
            fixedrange=True, tickangle=-35 if total_days > 14 else 0,
        ),
        yaxis=dict(
            tickfont=dict(size=9, color="#cbd5e1"),
            showgrid=True, gridcolor="rgba(226,232,240,0.45)",
            griddash="dot", gridwidth=1,
            zeroline=False, showline=False,
            fixedrange=True, range=[0, y_range_top],
        ),
        showlegend=False, hovermode="x unified",
        hoverlabel=dict(bgcolor="#1e293b", font=dict(color="white", size=12), bordercolor="#334155"),
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    legend_items = [("#1d4ed8", "Tertinggi"), ("#3b6cf7", "Normal")]
    if min_cnt > 0 and min_cnt != max_cnt:
        legend_items.insert(1, ("#a78bfa", "Terendah"))
    if any(c == 0 for c in counts_day):
        legend_items.append(("#cbd5e1", "Tidak ada data"))

    legend_html = "".join([
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;">'
        f'<span style="width:10px;height:10px;border-radius:3px;background:{clr};display:inline-block;"></span>'
        f'<span style="font-size:0.67rem;color:#64748b;font-weight:500;">{lbl}</span></span>'
        for clr, lbl in legend_items
    ])
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin:-4px 0 14px 2px;">{legend_html}</div>',
        unsafe_allow_html=True
    )

    pc1, pc2, pc3 = st.columns(3, gap="small")

    def _date_pills(days_list, color, max_show=4):
        if not days_list:
            return '<span style="font-size:0.72rem;color:#94a3b8;">&#8212;</span>'
        pills = ""
        for d in days_list[:max_show]:
            pills += (
                f'<span style="display:inline-block;background:{color}22;color:{color};'
                f'border:1px solid {color}44;border-radius:5px;padding:1px 7px;font-size:0.67rem;'
                f'font-weight:700;margin:2px 2px 0 0;">{d}</span>'
            )
        if len(days_list) > max_show:
            pills += (
                f'<span style="font-size:0.65rem;color:#94a3b8;margin-left:2px;">'
                f'+{len(days_list)-max_show} lainnya</span>'
            )
        return pills

    if not busiest_list:
        busy_main, busy_count, busy_pills = "&#8212;", "Belum ada data", ""
    elif len(busiest_list) == 1:
        busy_main, busy_count, busy_pills = busiest_list[0], f"{max_cnt:,} tweet", ""
    else:
        busy_main  = f"{len(busiest_list)} hari tertinggi"
        busy_count = f"masing-masing {max_cnt:,} tweet"
        busy_pills = _date_pills(busiest_list, "#ea580c")

    if not quietest_list:
        quiet_main, quiet_count, quiet_pills = "&#8212;", "Belum ada data aktif", ""
    elif len(quietest_list) == 1:
        quiet_main, quiet_count, quiet_pills = quietest_list[0], f"{min_cnt:,} tweet", ""
    else:
        quiet_main  = f"{len(quietest_list)} hari terendah"
        quiet_count = f"masing-masing {min_cnt:,} tweet"
        quiet_pills = _date_pills(quietest_list, "#7c3aed")

    pct_active = round(active_days / total_days * 100) if total_days > 0 else 0
    if active_days == 0:
        aktif_main, aktif_count, aktif_pills = "0 Hari Aktif", f"Dari {total_days} hari, belum ada data", ""
    elif active_days == total_days:
        aktif_main  = f"{active_days} / {total_days} Hari"
        aktif_count = f"100% hari ada tweet &middot; total {total_tweets:,} tweet"
        aktif_pills = ""
    else:
        aktif_main  = f"{active_days} / {total_days} Hari"
        aktif_count = f"{pct_active}% hari aktif &middot; {inactive_days} hari kosong"
        aktif_pills = ""

    def _insight_card(col, icon, bg, color, dark, border_c, title, main, count_txt, pills_html):
        with col:
            pills_block = (
                f'<div style="margin-top:0.4rem;line-height:1.8;">{pills_html}</div>'
                if pills_html else ""
            )
            st.markdown(
                f'<div class="mode-card" style="background:{bg};border:1px solid {border_c};'
                f'border-radius:14px;padding:0.9rem 1rem 0.95rem;'
                f'box-shadow:0 3px 12px {color}12;min-height:106px;">'
                f'<div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.55rem;">'
                f'<div style="width:30px;height:30px;background:{color};border-radius:8px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:0.85rem;flex-shrink:0;box-shadow:0 3px 7px {color}38;">{icon}</div>'
                f'<span style="font-size:0.58rem;font-weight:800;color:{color};'
                f'text-transform:uppercase;letter-spacing:0.08em;">{title}</span>'
                f'</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:{dark};'
                f'line-height:1.25;margin-bottom:0.15rem;">{main}</div>'
                f'<div style="font-size:0.67rem;color:{color};font-weight:500;'
                f'opacity:0.9;line-height:1.45;">{count_txt}</div>'
                f'{pills_block}'
                f'</div>',
                unsafe_allow_html=True,
            )

    _insight_card(pc1, "&#128293;", "linear-gradient(135deg,#fff7ed,#ffedd5)",
                  "#ea580c", "#7c2d12", "#fed7aa",
                  "Hari Paling Ramai", busy_main, busy_count, busy_pills)
    _insight_card(pc2, "&#127769;", "linear-gradient(135deg,#f5f3ff,#ede9fe)",
                  "#7c3aed", "#3b0764", "#ddd6fe",
                  "Hari Paling Sepi", quiet_main, quiet_count, quiet_pills)
    _insight_card(pc3, "&#128198;", "linear-gradient(135deg,#f0fdf4,#dcfce7)",
                  "#16a34a", "#14532d", "#bbf7d0",
                  "Hari Aktif", aktif_main, aktif_count, aktif_pills)


# ═══════════════════════════════════════════════════════════
#  FILTER DATA
# ═══════════════════════════════════════════════════════════

def get_filtered_data(df_all):
    now   = user_now()
    today = now.date()
    mode  = st.session_state.analysis_mode

    if mode == "realtime":
        mode_display = "Tweet Terkini &mdash; 7 Hari Terakhir"
        mode_color   = "#16a34a"
        mode_icon    = "&#128225;"
        date_col     = "created_at"
        basis_label  = "Berdasarkan tanggal asli tweet"
        chart_label  = "tanggal asli tweet"
        dt_start     = datetime.combine(today - timedelta(days=6), datetime.min.time())
        dt_end       = datetime.combine(today, datetime.max.time().replace(microsecond=0))

    elif mode == "30days":
        mode_display = "30 Hari Terakhir"
        mode_color   = "#3b6cf7"
        mode_icon    = "&#128197;"
        date_col     = "created_at"
        basis_label  = "Berdasarkan tanggal asli tweet"
        chart_label  = "tanggal asli tweet"
        dt_start     = datetime.combine(today - timedelta(days=29), datetime.min.time())
        dt_end       = datetime.combine(today, datetime.max.time().replace(microsecond=0))

    elif mode == "captured":
        mode_display = "Tweet Hari Ini"
        mode_color   = "#0284c7"
        mode_icon    = "&#128198;"
        date_col     = "created_at"
        basis_label  = "Berdasarkan tanggal asli tweet"
        chart_label  = "tanggal asli tweet"
        dt_start     = datetime.combine(today, datetime.min.time())
        dt_end       = datetime.combine(today, datetime.max.time().replace(microsecond=0))

    else:
        start_date   = st.session_state.get("custom_start_date", today)
        end_date     = st.session_state.get("custom_end_date", today)
        mode_display = "Periode Historis Pilihan"
        mode_color   = "#d97706"
        mode_icon    = "&#128269;"
        date_col     = "created_at"
        basis_label  = "Berdasarkan tanggal asli tweet"
        chart_label  = "tanggal asli tweet"
        dt_start     = datetime.combine(start_date, datetime.min.time())
        dt_end       = datetime.combine(end_date, datetime.max.time().replace(microsecond=0))

    df_source = df_all.dropna(subset=[date_col]).copy()
    df = df_source[
        (df_source[date_col] >= pd.Timestamp(dt_start)) &
        (df_source[date_col] <= pd.Timestamp(dt_end))
    ].copy()

    filter_label = f"{dt_start.strftime('%d/%m/%Y')} s/d {dt_end.strftime('%d/%m/%Y')}"

    return {
        "df":           df,
        "date_col":     date_col,
        "mode_display": mode_display,
        "mode_color":   mode_color,
        "mode_icon":    mode_icon,
        "filter_label": filter_label,
        "dt_start":     dt_start,
        "dt_end":       dt_end,
        "basis_label":  basis_label,
        "chart_label":  chart_label,
    }


# ═══════════════════════════════════════════════════════════
#  MAIN PAGE
# ═══════════════════════════════════════════════════════════

def show():
    today       = user_today()
    last_7_days = today - timedelta(days=6)

    _render_crawling_styles()

    if "filter_start_date" not in st.session_state:
        st.session_state.filter_start_date = last_7_days
    if "filter_end_date" not in st.session_state:
        st.session_state.filter_end_date = today

    # ── State aktivasi NRT ─────────────────────────────────────────────────
    from crawler import load_nrt_activation, ensure_scheduler_running as _ensure_sched

    # Inisialisasi pertama kali sesi dimulai
    if "nrt_activated" not in st.session_state:
        was_activated = load_nrt_activation()
        # Jika file persist bilang aktif tapi user sudah eksplisit nonaktifkan → ikut flag
        explicitly_off_init = st.session_state.get("nrt_explicitly_deactivated", False)
        if was_activated and not explicitly_off_init:
            st.session_state.nrt_activated = True
            from crawler import activate_nrt_scheduler as _activate
            _activate()
        else:
            st.session_state.nrt_activated = False

    # Sinkronisasi: _scheduler_started sudah dijaga oleh app.py (False jika explicitly_off)
    # Cukup mirror nilainya — tidak perlu logika tambahan
    explicitly_off = st.session_state.get("nrt_explicitly_deactivated", False)
    if explicitly_off:
        st.session_state.nrt_activated = False
    elif st.session_state.get("_scheduler_started", False):
        if not st.session_state.get("nrt_activated", False):
            st.session_state.nrt_activated = True
            if "crawl_history_started_at" not in st.session_state:
                st.session_state.crawl_history_started_at = datetime.now(tz=timezone.utc)

    # ── Page Header ───────────────────────────────────────────────
    _render_page_header()

    # ── Mode Selector ─────────────────────────────────────────────
    if "analysis_mode" not in st.session_state:
        st.session_state.analysis_mode = "realtime"

    col1, col2, col3, col4 = st.columns(4, gap="small")

    MODE_CFG = {
        "captured": {
            "col": col1, "key": "btn_captured", "label": "Hari Ini",
            "title": "Tweet Hari Ini", "icon": "&#128198;",
            "desc": "Tanggal asli <strong>hari ini</strong>",
            "gradient": "linear-gradient(135deg,#eff6ff,#dbeafe)",
            "border": "#bfdbfe", "color": "#1d4ed8", "dark": "#1e3a8a",
        },
        "realtime": {
            "col": col2, "key": "btn_realtime", "label": "7 Hari",
            "title": "Terkini (7 Hari)", "icon": "&#128225;",
            "desc": "<strong>7 hari terakhir</strong>",
            "gradient": "linear-gradient(135deg,#f0fdf4,#dcfce7)",
            "border": "#86efac", "color": "#16a34a", "dark": "#14532d",
        },
        "30days": {
            "col": col3, "key": "btn_30days", "label": "30 Hari",
            "title": "30 Hari Terakhir", "icon": "&#128197;",
            "desc": "<strong>30 hari terakhir</strong>",
            "gradient": "linear-gradient(135deg,#eef2ff,#e0e7ff)",
            "border": "#a5b4fc", "color": "#3b6cf7", "dark": "#1e3a8a",
        },
        "custom": {
            "col": col4, "key": "btn_custom", "label": "Pilih Tanggal",
            "title": "Pilih Tanggal", "icon": "&#128269;",
            "desc": "Historis <strong>custom</strong>",
            "gradient": "linear-gradient(135deg,#fefce8,#fef9c3)",
            "border": "#fde68a", "color": "#d97706", "dark": "#713f12",
        },
    }

    for mode_key, cfg in MODE_CFG.items():
        active = st.session_state.analysis_mode == mode_key
        with cfg["col"]:
            if st.button(
                cfg["label"], use_container_width=True,
                type="primary" if active else "secondary",
                key=cfg["key"]
            ):
                st.session_state.analysis_mode = mode_key
                st.rerun()

            bg           = cfg["gradient"] if active else "#ffffff"
            color        = cfg["color"]    if active else "#94a3b8"
            dark         = cfg["dark"]     if active else "#475569"
            shadow       = f"0 4px 16px {cfg['border']}55" if active else "0 1px 4px rgba(15,23,42,0.04)"
            border_style = f"2px solid {cfg['color']}" if active else "1.5px solid #e8edf5"
            icon_shadow  = f"0 4px 10px {cfg['border']}88" if active else "none"
            icon_bg      = "white" if active else "#f1f5f9"
            underline    = (
                f'<div style="width:22px;height:3px;background:{cfg["color"]};'
                f'border-radius:2px;margin:0.5rem auto 0;"></div>'
                if active else ""
            )

            st.markdown(
                f'<div class="mode-card" style="background:{bg};border:{border_style};'
                f'border-radius:14px;padding:1rem 0.85rem;margin-top:0.3rem;'
                f'text-align:center;box-shadow:{shadow};">'
                f'<div style="width:38px;height:38px;background:{icon_bg};border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:1.1rem;margin:0 auto 0.55rem;'
                f'box-shadow:{icon_shadow};">{cfg["icon"]}</div>'
                f'<div style="font-size:0.8rem;font-weight:700;color:{dark};margin-bottom:0.22rem;">'
                f'{cfg["title"]}</div>'
                f'<div style="font-size:0.68rem;color:{color};line-height:1.45;">{cfg["desc"]}</div>'
                f'{underline}'
                f'</div>',
                unsafe_allow_html=True,
            )

    _gap("md")

    # ── Load data ──────────────────────────────────────────────────
    try:
        df_all = pd.read_sql("SELECT * FROM tweets ORDER BY created_at DESC", engine)
    except Exception as e:
        st.error(f"Gagal membaca database: {str(e)}")
        return

    if len(df_all) == 0:
        st.warning("Belum ada data di database.")
        return

    df_all["created_at"] = parse_dt(df_all["created_at"])
    df_all["crawled_at"] = parse_crawled_dt(df_all["crawled_at"])

    # ── Custom Date Picker ─────────────────────────────────────────
    if st.session_state.analysis_mode == "custom":
        df_check = df_all.dropna(subset=["created_at"]).copy()
        if not df_check.empty:
            min_db = df_check["created_at"].min().date()
            max_db = df_check["created_at"].max().date()

            st.markdown(
                '<div class="crawl-card" style="margin-bottom:1rem;">'
                '<p style="font-size:0.875rem;font-weight:700;color:#0f172a;margin:0 0 0.25rem;">'
                '&#128197; Pilih Rentang Tanggal Tweet Historis</p>'
                f'<p style="font-size:0.775rem;color:#64748b;margin:0;line-height:1.6;">'
                f'Data tersedia dari '
                f'<strong style="color:#0f172a;">{min_db.strftime("%d/%m/%Y")}</strong>'
                f' hingga '
                f'<strong style="color:#0f172a;">{max_db.strftime("%d/%m/%Y")}</strong>'
                f'</p>'
                '</div>',
                unsafe_allow_html=True,
            )

            with st.container():
                c1, c2, c3 = st.columns([2, 2, 1], gap="medium")

                try:
                    start_value = pd.to_datetime(st.session_state.get("custom_start_date", min_db)).date()
                except Exception:
                    start_value = min_db
                try:
                    end_value = pd.to_datetime(st.session_state.get("custom_end_date", max_db)).date()
                except Exception:
                    end_value = max_db

                if start_value < min_db or start_value > max_db:
                    start_value = min_db
                if end_value < min_db or end_value > max_db:
                    end_value = max_db
                if end_value < start_value:
                    end_value = start_value

                with c1:
                    cs = st.date_input("Dari Tanggal", value=start_value,
                                       min_value=min_db, max_value=max_db,
                                       key="custom_start_input")
                    st.session_state.custom_start_date = cs
                with c2:
                    ce = st.date_input("Sampai Tanggal", value=end_value,
                                       min_value=min_db, max_value=max_db,
                                       key="custom_end_input")
                    st.session_state.custom_end_date = ce
                with c3:
                    if st.button("Terapkan", type="primary", use_container_width=True):
                        st.success("Periode diterapkan!")
                        time.sleep(0.8)
                        st.rerun()

    # ═══════════════════════════════════════════════════════════
    #  MODE: HARI INI (captured)
    # ═══════════════════════════════════════════════════════════
    if st.session_state.analysis_mode == "captured":

        nrt_activated = st.session_state.get("nrt_activated", False)

        if not nrt_activated:
            # ── Belum diaktifkan: tampilkan activation gate ───────
            _render_activation_gate()

        else:
            # ── Sudah diaktifkan: pastikan thread scheduler hidup ─
            if is_nrt_enabled():
                ensure_scheduler_running()

            # Auto-refresh setiap 1 detik untuk countdown live
            st_autorefresh(interval=1000, key="crawler_monitor_refresh")

            logs     = get_auto_crawl_logs(5)
            last_log = logs[0] if logs else None
            sched_ok = is_crawler_service_active(logs)
            last_dt  = parse_log_time(last_log.get("timestamp")) if last_log else None

            # Strip status aktif + tombol nonaktifkan
            _render_active_strip()

            # Banner status crawler
            _render_nrt_status_banner(sched_ok)
            _gap("sm")

            # Panel monitoring
            _render_monitoring_panel(last_log, last_dt, sched_ok)
            _gap("md")

            # Riwayat crawl
            visible_logs = get_visible_crawl_logs(logs)
            if visible_logs:
                rows = []
                for idx, log in enumerate(visible_logs, start=1):
                    status      = log.get("status", "")
                    total_saved = int(log.get("total_saved") or 0)
                    error_msg   = log.get("error")
                    try:
                        crawl_time = format_dt(
                            parse_dt(pd.Series([parse_log_time(log.get("timestamp"))])).iloc[0]
                        )
                    except Exception:
                        crawl_time = log.get("timestamp", "-") or "-"

                    if status == "success":
                        status_label = "Berhasil"
                        note = (
                            f"{total_saved:,} tweet baru tersimpan"
                            if total_saved > 0
                            else "Crawling berhasil, tidak ada tweet baru"
                        )
                    else:
                        status_label = "Gagal"
                        note = error_msg or "Terjadi kesalahan saat crawling"

                    rows.append({
                        "No":          idx,
                        "Waktu Crawl": crawl_time,
                        "Status":      status_label,
                        "Tweet Baru":  total_saved,
                        "Keterangan":  note,
                    })

                _section_header(
                    "&#128336; Riwayat Crawling Otomatis",
                    f"{len(rows)} aktivitas terbaru &middot; interval {NRT_INTERVAL_MINUTES} menit"
                )
                _gap("xs")
                render_standard_table(
                    pd.DataFrame(rows),
                    height=300, min_width=760,
                    right_align=["Tweet Baru"],
                    badge_columns=["Status"],
                    nowrap=["No", "Waktu Crawl", "Status"],
                    wide_columns=["Keterangan"],
                    column_widths={
                        "No": "56px", "Waktu Crawl": "160px",
                        "Status": "138px", "Tweet Baru": "118px", "Keterangan": "320px",
                    },
                )
            else:
                st.markdown(
                    '<div class="crawl-card" style="text-align:center;padding:2rem;">'
                    '<div style="font-size:2rem;margin-bottom:0.75rem;">&#9203;</div>'
                    '<div style="font-size:0.88rem;font-weight:700;color:#334155;margin-bottom:0.3rem;">'
                    'Menunggu Crawl Pertama</div>'
                    f'<div style="font-size:0.77rem;color:#64748b;">'
                    f'Riwayat akan muncul setelah crawl otomatis pertama selesai '
                    f'(maks. {NRT_INTERVAL_MINUTES} menit sejak aktivasi)'
                    f'</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            _gap("lg")

            # Tweet yang diambil bot hari ini
            today_start = datetime.combine(today, datetime.min.time())
            today_end   = datetime.combine(today, datetime.max.time().replace(microsecond=0))

            bot_df = df_all.copy()
            if "crawl_type" in bot_df.columns:
                bot_df = bot_df[bot_df["crawl_type"].fillna("").str.lower().eq("realtime")].copy()

            bot_df = bot_df.dropna(subset=["crawled_at"])
            bot_df = bot_df[
                (bot_df["crawled_at"] >= pd.Timestamp(today_start)) &
                (bot_df["crawled_at"] <= pd.Timestamp(today_end))
            ].sort_values("crawled_at", ascending=False)

            _section_header(
                "&#129302; Tweet yang Diambil Bot Hari Ini",
                "Semua tweet yang berhasil disimpan crawler hari ini"
            )
            _gap("xs")

            if bot_df.empty:
                st.markdown(
                    '<div class="crawl-card" style="text-align:center;padding:2rem;">'
                    '<div style="font-size:2rem;margin-bottom:0.75rem;">&#128038;</div>'
                    '<div style="font-size:0.88rem;font-weight:700;color:#334155;margin-bottom:0.3rem;">'
                    'Belum Ada Tweet Hari Ini</div>'
                    '<div style="font-size:0.77rem;color:#64748b;">'
                    'Tweet baru akan muncul setelah crawl berikutnya selesai'
                    '</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                bot_disp = bot_df.head(100).copy()
                bot_disp["Tanggal Tweet"]   = bot_disp["created_at"].apply(format_dt)
                bot_disp["Waktu Bot Ambil"] = bot_disp["crawled_at"].apply(format_dt)
                render_standard_table(
                    bot_disp[["tweet_id", "text", "Tanggal Tweet", "Waktu Bot Ambil"]].rename(
                        columns={"tweet_id": "ID Tweet", "text": "Isi Tweet"}
                    ),
                    height=340, min_width=920,
                    nowrap=["ID Tweet", "Tanggal Tweet", "Waktu Bot Ambil"],
                    wide_columns=["Isi Tweet"],
                    column_widths={
                        "ID Tweet": "170px", "Isi Tweet": "430px",
                        "Tanggal Tweet": "150px", "Waktu Bot Ambil": "160px",
                    },
                )
                st.caption(
                    f"Menampilkan {len(bot_disp):,} dari {len(bot_df):,} tweet yang disimpan bot hari ini"
                )

    # ═══════════════════════════════════════════════════════════
    #  FILTERED DATA — tampil di semua mode
    # ═══════════════════════════════════════════════════════════
    result       = get_filtered_data(df_all)
    df           = result["df"]
    date_col     = result["date_col"]
    mode_display = result["mode_display"]
    mode_color   = result["mode_color"]
    mode_icon    = result["mode_icon"]
    filter_label = result["filter_label"]
    dt_start     = result["dt_start"]
    dt_end       = result["dt_end"]
    basis_label  = result["basis_label"]
    chart_label  = result["chart_label"]

    st.session_state.filter_start_date  = dt_start
    st.session_state.filter_end_date    = dt_end
    st.session_state.filter_label       = filter_label
    st.session_state.mode_display       = mode_display
    st.session_state.filter_date_column = date_col

    _divider()

    total = len(df)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.9rem;'
        f'background:#ffffff;'
        f'border-left:4px solid {mode_color};'
        f'border-top:1px solid #e8edf5;'
        f'border-right:1px solid #e8edf5;'
        f'border-bottom:1px solid #e8edf5;'
        f'border-radius:0 14px 14px 0;'
        f'padding:0.75rem 1.3rem;margin-bottom:1rem;'
        f'box-shadow:0 2px 8px rgba(15,23,42,0.04);">'
        f'<span style="font-size:1.45rem;">{mode_icon}</span>'
        f'<div style="flex:1;">'
        f'<p style="font-size:0.88rem;font-weight:700;color:#0f172a;margin:0 0 2px;">{mode_display}</p>'
        f'<p style="font-size:0.74rem;color:#64748b;margin:0;">'
        f'Periode aktif: <strong style="color:{mode_color};">{filter_label}</strong>'
        f'&nbsp;&middot;&nbsp; {basis_label}'
        f'</p>'
        f'</div>'
        f'<div style="margin-left:auto;background:{mode_color}14;color:{mode_color};'
        f'border:1px solid {mode_color}33;'
        f'font-size:0.7rem;font-weight:800;padding:0.3rem 0.8rem;'
        f'border-radius:999px;letter-spacing:0.04em;white-space:nowrap;">'
        f'{total:,} tweet'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    days     = (pd.Timestamp(dt_end).date() - pd.Timestamp(dt_start).date()).days + 1
    earliest = pd.Timestamp(dt_start).strftime("%d/%m/%Y")
    latest   = pd.Timestamp(dt_end).strftime("%d/%m/%Y")

    _render_metrics(total, days, earliest, latest, filter_label, basis_label)

    if total == 0:
        _section_header("&#128203; Daftar Tweet yang Terkumpul", f"0 tweet &middot; {filter_label}")
        st.markdown(
            '<div class="crawl-card" style="text-align:center;padding:2rem;">'
            '<div style="font-size:2rem;margin-bottom:0.75rem;">&#128269;</div>'
            '<div style="font-size:0.88rem;font-weight:700;color:#334155;margin-bottom:0.3rem;">'
            'Tidak Ada Data</div>'
            '<div style="font-size:0.77rem;color:#64748b;">'
            'Belum ada tweet dengan tanggal asli pada periode ini'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="crawl-card" style="padding-bottom:0.4rem;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.1rem;">'
        f'<p style="font-size:0.87rem;font-weight:700;color:#0f172a;margin:0;">'
        f'&#128202; Distribusi Tweet Per Hari</p>'
        f'<span style="font-size:0.67rem;font-weight:600;color:#94a3b8;'
        f'background:#f8fafc;border:1px solid #e8edf5;'
        f'border-radius:6px;padding:0.18rem 0.55rem;">{filter_label}</span>'
        f'</div>'
        f'<p style="font-size:0.69rem;color:#94a3b8;margin:2px 0 0;">'
        f'Berdasarkan {chart_label}'
        f'</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _render_charts(df, filter_label, date_col, chart_label, dt_start, dt_end)

    display_limit = 100
    _section_header(
        "&#128203; Daftar Tweet yang Terkumpul",
        f"Menampilkan hingga {display_limit} tweet terbaru &middot; {filter_label}"
    )
    _gap("xs")

    df_disp = df.sort_values(date_col, ascending=False).head(display_limit).copy()
    df_disp["Tanggal Tweet"]  = df_disp["created_at"].apply(format_dt)
    df_disp["Masuk Database"] = df_disp["crawled_at"].apply(format_dt)

    render_standard_table(
        df_disp[["tweet_id", "text", "Tanggal Tweet", "Masuk Database"]].rename(
            columns={"tweet_id": "ID Tweet", "text": "Isi Tweet"}
        ),
        height=380, min_width=840,
        nowrap=["ID Tweet", "Tanggal Tweet", "Masuk Database"],
        wide_columns=["Isi Tweet"],
        column_widths={
            "ID Tweet": "180px", "Isi Tweet": "420px",
            "Tanggal Tweet": "150px", "Masuk Database": "155px",
        },
    )
    st.caption(f"Menampilkan {len(df_disp):,} dari {total:,} tweet")
    _gap("sm")

    c_dl, c_nav = st.columns(2)
    with c_dl:
        st.download_button(
            f"Unduh Semua Data ({total:,} tweet)",
            df.to_csv(index=False).encode("utf-8"),
            f"data_twitter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            use_container_width=True
        )
    with c_nav:
        if st.button(
            "Lanjut ke Bersihkan Data",
            type="primary",
            use_container_width=True,
            key="btn_go_preprocessing"
        ):
            st.session_state.page = "preprocessing"
            st.rerun()

    _gap("sm")