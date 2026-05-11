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
)


def parse_dt(series):
    return parse_dt_with_tz(
        series,
        st.session_state.get("user_timezone", "WIB (UTC+7)")
    )


def parse_crawled_dt(series):
    return parse_dt_with_source_tz(
        series,
        st.session_state.get("user_timezone", "WIB (UTC+7)"),
        os.getenv("APP_TIMEZONE", "Asia/Makassar")
    )


def format_dt(value):
    if value is None or pd.isna(value):
        return "Belum ada"

    try:
        if not hasattr(value, "strftime"):
            value = parse_dt(pd.Series([value])).iloc[0]

        if value is None or pd.isna(value):
            return "Belum ada"

        tz_label = get_timezone_label(
            st.session_state.get("user_timezone", "WIB (UTC+7)")
        )
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
        parsed = parsed.tz_localize(os.getenv("APP_TIMEZONE", "Asia/Makassar"))

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
        state.get   ("is_running", False)
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
            os.getenv("APP_TIMEZONE", "Asia/Makassar")
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


def _section_header(title, subtitle=""):
    """Render consistent section header card"""
    sub_html = (
        f'<div style="font-size:0.78rem;color:#64748b;margin-top:4px;line-height:1.5;">{subtitle}</div>'
        if subtitle else ""
    )

    st.markdown(f"""
<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1rem 1.25rem;margin-bottom:1rem;
            box-shadow:0 2px 6px rgba(15,23,42,0.06);">
    <div style="font-size:0.95rem;font-weight:700;color:#0f172a;letter-spacing:0.02em;">{title}</div>
    {sub_html}
</div>
""", unsafe_allow_html=True)


def _captured_section_gap(size="md"):
    heights = {
        "sm": 12,
        "md": 20,
        "lg": 28,
    }
    height = heights.get(size, heights["md"])

    st.markdown(
        f'<div style="height:{height}px;"></div>',
        unsafe_allow_html=True
    )


def _render_crawling_styles():
    st.markdown("""
<style>
.st-key-custom_date_panel {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.06) !important;
    padding: 1rem 1.15rem 0.95rem !important;
    margin-bottom: 1.15rem !important;
}

.st-key-custom_date_panel [data-testid="stDateInput"] label p {
    color: #334155 !important;
    font-size: 0.72rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.04em !important;
    margin-bottom: 0.35rem !important;
    text-transform: uppercase !important;
}

.st-key-custom_date_panel [data-testid="stDateInput"] input,
.st-key-custom_date_panel [data-baseweb="input"],
.st-key-custom_date_panel [data-baseweb="input"] input {
    background: #ffffff !important;
    border-color: #e2e8f0 !important;
    border-radius: 10px !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    min-height: 46px !important;
}

.st-key-custom_date_panel .stButton > button {
    min-height: 46px !important;
    margin-bottom: 0 !important;
}

.st-key-bot_control_panel {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.06) !important;
    margin: 1.35rem 0 1.75rem !important;
    padding: 1.05rem 1.15rem !important;
}

.st-key-bot_control_panel .stButton > button {
    min-height: 46px !important;
    margin-bottom: 0 !important;
}

.st-key-bot_control_panel [data-testid="stAlert"] {
    margin-bottom: 0 !important;
}

.st-key-bot_control_panel [data-testid="stHorizontalBlock"] {
    gap: 1rem !important;
}

.st-key-bot_control_panel [data-testid="stMarkdownContainer"] p {
    margin-bottom: 0 !important;
}
</style>
""", unsafe_allow_html=True)


def _render_metrics(total, days, earliest, latest, filter_label, basis_label):
    st.markdown(f"""
<div style="font-size:0.82rem;color:#64748b;line-height:1.5;margin:0.25rem 0 1.25rem;">
    🔄 Data aktif: {filter_label} · {basis_label}
</div>
""", unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)

    pills = [
        (
            c1,
            "📊",
            "#eef2ff",
            "#3b6cf7",
            "#1e3a8a",
            "Total Tweet",
            f"{total:,}",
            "Terkumpul dalam periode ini"
        ),
        (
            c2,
            "📅",
            "#f0fdf4",
            "#16a34a",
            "#14532d",
            "Rentang Waktu Data",
            f"{days} Hari",
            basis_label
        ),
        (
            c3,
            "🗓️",
            "#fff7ed",
            "#ea580c",
            "#7c2d12",
            "Mulai Dari",
            earliest,
            "Tanggal awal periode"
        ),
        (
            c4,
            "📆",
            "#fefce8",
            "#ca8a04",
            "#713f12",
            "Sampai Dengan",
            latest,
            "Tanggal akhir periode"
        ),
    ]

    for col, icon, bg, color, dark, label, val, sub in pills:
        with col:
            fs = "1.05rem" if len(str(val)) > 10 else "1.55rem"

            st.markdown(f"""
<div style="background:{bg};border:1.5px solid {color}44;border-radius:16px;
            padding:1.25rem 1rem;text-align:center;
            box-shadow:0 3px 10px {color}22;margin-bottom:1.75rem;">
    <div style="width:40px;height:40px;background:{color};border-radius:10px;
                display:flex;align-items:center;justify-content:center;
                font-size:1.1rem;margin:0 auto 0.625rem;color:white;">{icon}</div>
    <div style="font-size:0.7rem;font-weight:700;color:{dark};
                text-transform:uppercase;letter-spacing:0.05em;
                margin-bottom:0.3rem;">{label}</div>
    <div style="font-size:{fs};font-weight:800;color:{dark};line-height:1.2;">{val}</div>
    <div style="font-size:0.7rem;color:{color};font-weight:600;margin-top:0.25rem;">{sub}</div>
</div>
""", unsafe_allow_html=True)


def _render_charts(df, filter_label, date_col, chart_label, dt_start, dt_end):
    df_tl = df.copy()
    df_tl = df_tl.dropna(subset=[date_col])

    if df_tl.empty:
        st.info("Belum ada data valid untuk grafik.")
        return

    is_realtime_basis = date_col == "crawled_at"
    chart_title = (
        "📅 Jumlah Data Masuk Per Hari"
        if is_realtime_basis else
        "📅 Jumlah Tweet Per Hari"
    )
    count_label = "data masuk" if is_realtime_basis else "tweet"
    avg_label = (
        "Rata-rata Data Masuk per Hari"
        if is_realtime_basis else
        "Rata-rata Tweet per Hari"
    )

    df_tl["date_key"] = df_tl[date_col].dt.strftime("%Y-%m-%d")

    actual_daily = (
        df_tl
        .groupby("date_key")
        .size()
        .reset_index(name="count")
        .sort_values("date_key")
    )

    date_range = pd.date_range(
        pd.Timestamp(dt_start).date(),
        pd.Timestamp(dt_end).date(),
        freq="D"
    )

    daily = pd.DataFrame({
        "date_key": date_range.strftime("%Y-%m-%d"),
        "date_str": date_range.strftime("%d %b"),
    }).merge(
        actual_daily,
        on="date_key",
        how="left"
    )

    daily["count"] = daily["count"].fillna(0).astype(int)

    ordered = daily["date_str"].tolist()
    counts_day = daily["count"].tolist()

    avg_per_day = round(len(df_tl) / len(daily), 1) if len(daily) > 0 else 0

    busiest_row = daily.loc[daily["count"].idxmax()] if len(daily) > 0 and daily["count"].max() > 0 else None
    busiest_day = busiest_row["date_str"] if busiest_row is not None else "-"
    busiest_cnt = int(busiest_row["count"]) if busiest_row is not None else 0

    _section_header(
        chart_title,
        f"Dihitung berdasarkan {chart_label} · {filter_label}"
    )

    bar_clrs = [
        "#1d4ed8" if c == busiest_cnt else "#3b6cf7"
        for c in counts_day
    ]

    fig_bar = go.Figure(data=[
        go.Bar(
            x=ordered,
            y=counts_day,
            marker=dict(color=bar_clrs, line=dict(width=0), opacity=0.88),
            width=0.5,
            hovertemplate=f"<b>%{{x}}</b><br>%{{y:,}} {count_label}<extra></extra>",
            text=[str(c) for c in counts_day],
            textposition="outside",
            textfont=dict(size=10, color="#475569"),
            cliponaxis=False,
        )
    ])

    fig_bar.update_layout(
        height=340,
        margin=dict(l=0, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=ordered,
            tickfont=dict(size=11, color="#334155"),
            showgrid=False,
            zeroline=False,
            showline=False,
            fixedrange=True
        ),
        yaxis=dict(
            tickfont=dict(size=10, color="#475569"),
            showgrid=True,
            gridcolor="rgba(203,213,225,0.8)",
            griddash="dot",
            gridwidth=1,
            zeroline=False,
            showline=False,
            fixedrange=True
        ),
        showlegend=False,
        hovermode="x unified",
    )

    st.plotly_chart(
        fig_bar,
        width="stretch",
        config={"displayModeBar": False}
    )

    pc1, pc2 = st.columns(2)

    with pc1:
        st.markdown(f"""
<div style="background:#eef2ff;border:1.5px solid #c7d2fe;border-radius:12px;
            padding:0.875rem 1.25rem;display:flex;align-items:center;gap:0.75rem;">
    <div style="width:36px;height:36px;background:#3b6cf7;border-radius:10px;
                display:flex;align-items:center;justify-content:center;
                font-size:1rem;flex-shrink:0;color:white;">📊</div>
    <div>
        <div style="font-size:0.7rem;font-weight:700;color:#1e40af;
                    text-transform:uppercase;letter-spacing:0.04em;">{avg_label}</div>
        <div style="font-size:1.25rem;font-weight:800;color:#1e3a8a;margin-top:2px;">
            {avg_per_day} {count_label}</div>
    </div>
</div>
""", unsafe_allow_html=True)

    with pc2:
        st.markdown(f"""
<div style="background:#fefce8;border:1.5px solid #fde68a;border-radius:12px;
            padding:0.875rem 1.25rem;display:flex;align-items:center;gap:0.75rem;">
    <div style="width:36px;height:36px;background:#ca8a04;border-radius:10px;
                display:flex;align-items:center;justify-content:center;
                font-size:1rem;flex-shrink:0;color:white;">🔥</div>
    <div>
        <div style="font-size:0.7rem;font-weight:700;color:#713f12;
                    text-transform:uppercase;letter-spacing:0.04em;">Hari {count_label.title()} Terbanyak</div>
        <div style="font-size:1.05rem;font-weight:800;color:#713f12;margin-top:2px;">
            {busiest_day}
            <span style="font-size:0.78rem;font-weight:600;color:#ca8a04;">
                ({busiest_cnt:,} {count_label})</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


def _render_nrt_status_banner(sched_ok):
    if sched_ok:
        bg = "linear-gradient(135deg,#f0fdf4,#dcfce7)"
        bdr = "#86efac"
        dot = "#16a34a"
        title = "🟢 Crawler Service Berjalan sebagai Background Job"
        desc = (
            f"Sistem <strong>crawler service</strong> berjalan di background secara otomatis "
            f"setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong>. "
            f"Panel monitoring membaca update realtime berdasarkan <strong>crawled_at</strong>."
        )
    else:
        bg = "linear-gradient(135deg,#fef9c3,#fef08a)"
        bdr = "#fcd34d"
        dot = "#f59e0b"
        title = "⚠️ Crawler Service Belum Aktif"
        desc = (
            # f"Jalankan <code>python3 crawler.py</code> di terminal terpisah "
            f"Jalankan <code>python crawler.py</code> di terminal terpisah "
            f"untuk mengaktifkan crawler otomatis setiap "
            f"<strong>{NRT_INTERVAL_MINUTES} menit</strong>."
        )

    st.markdown(f"""
<div style="background:{bg};border:1.5px solid {bdr};border-radius:14px;
            padding:1rem 1.25rem;margin-bottom:1rem;
            display:flex;align-items:flex-start;gap:0.75rem;">
    <div style="width:12px;height:12px;background:{dot};border-radius:50%;
                box-shadow:0 0 0 4px {dot}44;flex-shrink:0;margin-top:4px;"></div>
    <div style="flex:1;">
        <div style="font-size:0.875rem;font-weight:700;color:#0f172a;">{title}</div>
        <div style="font-size:0.78rem;color:#334155;margin-top:3px;line-height:1.65;">{desc}</div>
    </div>
</div>
""", unsafe_allow_html=True)


def _render_monitoring_panel(last_log, last_dt, sched_ok):
    now = user_now()

    try:
        df_stats = pd.read_sql(
            "SELECT crawled_at FROM tweets",
            engine
        )

        if not df_stats.empty:
            df_stats["crawled_at"] = parse_crawled_dt(df_stats["crawled_at"])

        total_db = len(df_stats)
        interval_start = now - timedelta(minutes=NRT_INTERVAL_MINUTES)
        tweet_interval = (
            len(df_stats[df_stats["crawled_at"] >= pd.Timestamp(interval_start)])
            if not df_stats.empty else 0
        )
        latest_crawled = (
            df_stats["crawled_at"].max()
            if not df_stats.empty else None
        )
    except Exception:
        total_db = 0
        tweet_interval = 0
        latest_crawled = None

    last_log_dt = last_dt

    if last_log_dt is None and last_log:
        last_log_dt = parse_log_time(last_log.get("timestamp"))

    final_last_dt = to_user_local_datetime(last_log_dt)

    if final_last_dt is None:
        final_last_dt = to_user_local_datetime(latest_crawled)

    last_crawl_str = "Belum pernah"
    next_crawl_str = "Belum terjadwal"
    monitoring_time_str = format_dt(now)
    countdown_str = "Belum terjadwal"

    if final_last_dt is not None:
        next_dt = final_last_dt + timedelta(minutes=NRT_INTERVAL_MINUTES)
        remaining = next_dt - now

        last_crawl_str = format_dt(final_last_dt)
        next_crawl_str = format_dt(next_dt)

        if remaining.total_seconds() > 0:
            countdown_str = format_countdown(remaining)
        elif is_crawler_running():
            countdown_str = "Sedang crawling..."
        else:
            countdown_str = "Menunggu hasil crawl terbaru..."

    status_text = "Active" if sched_ok else "Nonaktif"
    status_color = "#16a34a" if sched_ok else "#ca8a04"
    note_text = (
        "✅ Data berhasil diperbarui"
        if tweet_interval > 0 else
        "ℹ️ Tidak ada tweet baru pada periode ini"
    )
    note_bg = "#f0fdf4" if tweet_interval > 0 else "#f8fafc"
    note_border = "#bbf7d0" if tweet_interval > 0 else "#e2e8f0"
    note_color = "#166534" if tweet_interval > 0 else "#475569"

    _section_header(
        "📡 Status Monitoring Sistem",
        "Transparansi proses pengambilan data secara near real-time"
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"""
<div style="background:#f0fdf4;border:1.5px solid #bbf7d0;border-radius:14px;
            padding:1rem 1.15rem;box-shadow:0 2px 8px rgba(15,23,42,0.06);
            min-height:240px;display:flex;flex-direction:column;margin-bottom:1rem;">
    <div style="font-size:0.72rem;font-weight:800;color:#0f172a;
                text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.95rem;">
        ⚙️ STATUS SISTEM CRAWLING
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #dcfce7;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Crawler Status</span>
        <span style="font-size:0.86rem;font-weight:800;color:{status_color};">{status_text}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #dcfce7;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Interval Crawling</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;">{NRT_INTERVAL_MINUTES} menit</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #dcfce7;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Last Crawling</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">{last_crawl_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #dcfce7;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Waktu Monitoring</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">{monitoring_time_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0 0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Next Crawling</span>
        <span style="font-size:0.86rem;font-weight:800;color:#3b6cf7;text-align:right;">⏰ {next_crawl_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0 0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Countdown</span>
        <span style="font-size:0.86rem;font-weight:800;color:#16a34a;text-align:right;">{countdown_str}</span>
    </div>
</div>
""", unsafe_allow_html=True)

    with col_b:
        st.markdown(f"""
<div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1rem 1.15rem;box-shadow:0 2px 8px rgba(15,23,42,0.06);
            min-height:240px;display:flex;flex-direction:column;margin-bottom:1rem;">
    <div style="font-size:0.72rem;font-weight:800;color:#0f172a;
                text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.95rem;">
        📊 RINGKASAN UPDATE TERAKHIR
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Update terakhir</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">{last_crawl_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Waktu Monitoring</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">{monitoring_time_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Menuju Crawl Berikutnya</span>
        <span style="font-size:0.86rem;font-weight:800;color:#16a34a;text-align:right;">{countdown_str}</span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">
            Tweet baru dalam {NRT_INTERVAL_MINUTES} menit terakhir
        </span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">
            {tweet_interval:,} tweet baru
        </span>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:0.75rem;padding:0.55rem 0;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:0.82rem;font-weight:650;color:#475569;">Total dataset terkumpul</span>
        <span style="font-size:0.86rem;font-weight:800;color:#0f172a;text-align:right;">{total_db:,} tweet</span>
    </div>
    <div style="background:{note_bg};border:1px solid {note_border};border-radius:10px;
                padding:0.65rem 0.75rem;margin-top:0.8rem;
                font-size:0.82rem;font-weight:750;color:{note_color};">
        {note_text}
    </div>
</div>
""", unsafe_allow_html=True)


def get_filtered_data(df_all):
    now = user_now()
    today = now.date()
    mode = st.session_state.analysis_mode

    if mode == "realtime":
        mode_display = "Tweet Terkini — 7 Hari Terakhir"
        mode_color = "#16a34a"
        mode_icon = "📡"
        date_col = "created_at"
        basis_label = "Berdasarkan tanggal asli tweet"
        chart_label = "tanggal asli tweet"
        dt_start = datetime.combine(
            today - timedelta(days=6),
            datetime.min.time()
        )
        dt_end = datetime.combine(
            today,
            datetime.max.time().replace(microsecond=0)
        )

    elif mode == "30days":
        mode_display = "30 Hari Terakhir"
        mode_color = "#3b6cf7"
        mode_icon = "📅"
        date_col = "created_at"
        basis_label = "Berdasarkan tanggal asli tweet"
        chart_label = "tanggal asli tweet"
        dt_start = datetime.combine(
            today - timedelta(days=29),
            datetime.min.time()
        )
        dt_end = datetime.combine(
            today,
            datetime.max.time().replace(microsecond=0)
        )

    elif mode == "captured":
        mode_display = "Tweet Hari Ini"
        mode_color = "#0284c7"
        mode_icon = "📆"
        date_col = "created_at"
        basis_label = "Berdasarkan tanggal asli tweet"
        chart_label = "tanggal asli tweet"
        dt_start = datetime.combine(today, datetime.min.time())
        dt_end = datetime.combine(now.date(), datetime.max.time().replace(microsecond=0))

    else:
        start_date = st.session_state.get("custom_start_date", now.date())
        end_date = st.session_state.get("custom_end_date", now.date())

        mode_display = "Periode Historis Pilihan"
        mode_color = "#d97706"
        mode_icon = "🔍"
        date_col = "created_at"
        basis_label = "Berdasarkan tanggal asli tweet"
        chart_label = "tanggal asli tweet"
        dt_start = datetime.combine(start_date, datetime.min.time())
        dt_end = datetime.combine(end_date, datetime.max.time().replace(microsecond=0))

    df_source = df_all.dropna(subset=[date_col]).copy()

    df = df_source[
        (df_source[date_col] >= pd.Timestamp(dt_start)) &
        (df_source[date_col] <= pd.Timestamp(dt_end))
    ].copy()

    filter_label = f"{dt_start.strftime('%d/%m/%Y')} s/d {dt_end.strftime('%d/%m/%Y')}"

    return {
        "df": df,
        "date_col": date_col,
        "mode_display": mode_display,
        "mode_color": mode_color,
        "mode_icon": mode_icon,
        "filter_label": filter_label,
        "dt_start": dt_start,
        "dt_end": dt_end,
        "basis_label": basis_label,
        "chart_label": chart_label,
    }


def show():
    today = user_today()
    last_7_days = today - timedelta(days=6)

    _render_crawling_styles()

    if "filter_start_date" not in st.session_state:
        st.session_state.filter_start_date = last_7_days

    if "filter_end_date" not in st.session_state:
        st.session_state.filter_end_date = today

    st.markdown("""
<div class="top-header">
    <div style="display:flex;align-items:center;gap:0.75rem;">
        <div style="width:36px;height:36px;background:#eef2ff;border-radius:10px;
                    display:flex;align-items:center;justify-content:center;font-size:1.1rem;">
            🔄
        </div>
        <h1 class="page-title">Ambil Data Twitter</h1>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown(f"""
<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;
            padding:1.25rem 1.5rem;box-shadow:0 2px 6px rgba(15,23,42,0.07);
            margin-bottom:1.25rem;">
    <div style="font-size:1rem;font-weight:700;color:#0f172a;margin-bottom:0.5rem;">
        📖 Apa yang dilakukan halaman ini?
    </div>
    <div style="font-size:0.8375rem;color:#475569;line-height:1.75;">
        Sistem menggunakan database historis sebagai data awal, lalu crawler menambahkan data baru
        secara berkala setiap <strong>{NRT_INTERVAL_MINUTES} menit</strong>.
        Semua filter tampilan membaca <strong>created_at</strong> atau tanggal asli tweet;
        panel monitoring crawler tetap memakai <strong>crawled_at</strong>.
    </div>
</div>
""", unsafe_allow_html=True)

    if "analysis_mode" not in st.session_state:
        st.session_state.analysis_mode = "realtime"

    col1, col2, col3, col4 = st.columns(4)

    MODE_CFG = {
        "captured": {
            "col": col1,
            "key": "btn_captured",
            "label": "📆  Tweet Hari Ini",
            "title": "Tweet Hari Ini",
            "icon": "📆",
            "desc": "Tweet bertanggal asli <strong>hari ini</strong>",
            "active_bg": "linear-gradient(135deg,#f0f9ff,#dbeafe)",
            "active_border": "#0ea5e9",
            "active_tc": "#0c4a6e",
            "icon_bg": "#0284c7",
        },
        "realtime": {
            "col": col2,
            "key": "btn_realtime",
            "label": "📡  Terkini (7 Hari)",
            "title": "Tweet Terkini",
            "icon": "📡",
            "desc": "Tweet bertanggal asli dalam <strong>7 hari terakhir</strong>",
            "active_bg": "linear-gradient(135deg,#dcfce7,#bbf7d0)",
            "active_border": "#22c55e",
            "active_tc": "#14532d",
            "icon_bg": "#16a34a",
        },
        "30days": {
            "col": col3,
            "key": "btn_30days",
            "label": "📅  30 Hari Terakhir",
            "title": "30 Hari Terakhir",
            "icon": "📅",
            "desc": "Tweet bertanggal asli dalam <strong>30 hari terakhir</strong>",
            "active_bg": "linear-gradient(135deg,#eef2ff,#e0e7ff)",
            "active_border": "#3b6cf7",
            "active_tc": "#1e3a8a",
            "icon_bg": "#3b6cf7",
        },
        # "captured": {
        #     "col": col3,
        #     "key": "btn_captured",
        #     "label": "📆  Tweet Hari Ini",
        #     "title": "Tweet Hari Ini",
        #     "icon": "📆",
        #     "desc": "Tweet bertanggal asli <strong>hari ini</strong>",
        #     "active_bg": "linear-gradient(135deg,#f0f9ff,#dbeafe)",
        #     "active_border": "#0ea5e9",
        #     "active_tc": "#0c4a6e",
        #     "icon_bg": "#0284c7",
        # },
        "custom": {
            "col": col4,
            "key": "btn_custom",
            "label": "🔍  Pilih Tanggal",
            "title": "Pilih Tanggal",
            "icon": "🔍",
            "desc": "Pilih data historis berdasarkan <strong>tanggal asli tweet</strong>",
            "active_bg": "linear-gradient(135deg,#fef9c3,#fef08a)",
            "active_border": "#f59e0b",
            "active_tc": "#713f12",
            "icon_bg": "#d97706",
        },
    }

    for mode_key, cfg in MODE_CFG.items():
        active = st.session_state.analysis_mode == mode_key

        with cfg["col"]:
            if st.button(
                cfg["label"],
                width="stretch",
                type="primary" if active else "secondary",
                key=cfg["key"]
            ):
                st.session_state.analysis_mode = mode_key
                st.rerun()

            bg = cfg["active_bg"] if active else "#f8fafc"
            bdr = cfg["active_border"] if active else "#e2e8f0"
            tc = cfg["active_tc"] if active else "#475569"
            ic_bg = cfg["icon_bg"] if active else "#e2e8f0"
            ic_c = "white" if active else "#64748b"
            title_c = cfg["active_tc"] if active else "#0f172a"
            bdr_w = "2px" if active else "1.5px"

            st.markdown(f"""
<div style="background:{bg};border:{bdr_w} solid {bdr};
            border-radius:14px;padding:1rem;margin-top:0.4rem;text-align:center;">
    <div style="width:44px;height:44px;background:{ic_bg};border-radius:12px;
                display:flex;align-items:center;justify-content:center;
                font-size:1.25rem;margin:0 auto 0.625rem;color:{ic_c};">
        {cfg["icon"]}</div>
    <div style="font-size:0.9rem;font-weight:700;color:{title_c};margin-bottom:0.3rem;">
        {cfg["title"]}</div>
    <div style="font-size:0.74rem;color:{tc};line-height:1.55;">{cfg["desc"]}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    try:
        df_all = pd.read_sql(
            "SELECT * FROM tweets ORDER BY created_at DESC",
            engine
        )

    except Exception as e:
        st.error(f"❌ Gagal membaca database: {str(e)}")
        return

    if len(df_all) == 0:
        st.warning("Belum ada data di database.")
        return

    df_all["created_at"] = parse_dt(df_all["created_at"])
    df_all["crawled_at"] = parse_crawled_dt(df_all["crawled_at"])

    if st.session_state.analysis_mode == "custom":
        df_check = df_all.dropna(subset=["created_at"]).copy()

        if not df_check.empty:
            min_db = df_check["created_at"].min().date()
            max_db = df_check["created_at"].max().date()

            st.markdown(f"""
<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1.25rem 1.5rem;margin-bottom:1rem;
            box-shadow:0 2px 6px rgba(15,23,42,0.07);">
    <div style="font-size:0.95rem;font-weight:700;color:#0f172a;margin-bottom:0.35rem;">
        📅 Pilih Rentang Tanggal Tweet Historis</div>
    <div style="font-size:0.78rem;color:#475569;line-height:1.6;">
        Data tersedia dari <strong>{min_db.strftime('%d/%m/%Y')}</strong>
        hingga <strong>{max_db.strftime('%d/%m/%Y')}</strong>
    </div>
</div>
""", unsafe_allow_html=True)

            with st.container(border=True, key="custom_date_panel"):
                c1, c2, c3 = st.columns(
                    [2, 2, 1],
                    gap="medium",
                    vertical_alignment="bottom"
                )

                try:
                    start_value = pd.to_datetime(
                        st.session_state.get("custom_start_date", min_db)
                    ).date()
                except Exception:
                    start_value = min_db

                try:
                    end_value = pd.to_datetime(
                        st.session_state.get("custom_end_date", max_db)
                    ).date()
                except Exception:
                    end_value = max_db

                if start_value < min_db or start_value > max_db:
                    start_value = min_db

                if end_value < min_db or end_value > max_db:
                    end_value = max_db

                if end_value < start_value:
                    end_value = start_value

                with c1:
                    cs = st.date_input(
                        "Dari Tanggal",
                        value=start_value,
                        min_value=min_db,
                        max_value=max_db,
                        key="custom_start_input"
                    )
                    st.session_state.custom_start_date = cs

                with c2:
                    ce = st.date_input(
                        "Sampai Tanggal",
                        value=end_value,
                        min_value=min_db,
                        max_value=max_db,
                        key="custom_end_input"
                    )
                    st.session_state.custom_end_date = ce

                with c3:
                    if st.button("✅ Terapkan", type="primary", width="stretch"):
                        st.success("✅ Periode diterapkan!")
                        time.sleep(0.8)
                        st.rerun()

    if st.session_state.analysis_mode == "captured":
        st_autorefresh(
            interval=1000,
            key="crawler_monitor_refresh"
        )

        logs = get_auto_crawl_logs(5)
        last_log = logs[0] if logs else None
        sched_ok = is_crawler_service_active(logs)

        last_dt = None

        if last_log:
            last_dt = parse_log_time(last_log.get("timestamp"))

        _section_header(
            "🤖 Ambil Data dengan Bot",
            "Panel ini khusus mode Tweet Hari Ini agar status crawler tidak memenuhi tampilan Terkini"
        )
        _render_nrt_status_banner(sched_ok)
        _captured_section_gap("sm")
        _render_monitoring_panel(last_log, last_dt, sched_ok)
        crawler_running = is_crawler_running()

        with st.container(border=True, key="bot_control_panel"):
            col_status, col_refresh, col_action = st.columns(
                [2.6, 1.1, 1.5],
                gap="medium",
                vertical_alignment="center"
            )

            with col_status:
                if crawler_running:
                    st.info("⏳ Crawler sedang berjalan — tombol ambil data dinonaktifkan sementara")
                elif sched_ok:
                    st.success("✅ Crawler aktif — data diperbarui otomatis")
                else:
                    # st.info("ℹ️ Jalankan `python3 crawler.py` untuk mengaktifkan crawler")
                    st.info("ℹ️ Jalankan `python crawler.py` untuk mengaktifkan crawler")


            with col_refresh:
                previous_auto_refresh = st.session_state.get("auto_refresh_ui", False)
                auto_refresh = st.toggle(
                    "🔁 Refresh Otomatis",
                    value=previous_auto_refresh,
                    key="ar_toggle",
                    help=f"Halaman diperbarui otomatis setiap {NRT_INTERVAL_MINUTES} menit"
                )
                st.session_state.auto_refresh_ui = auto_refresh

                if auto_refresh and not previous_auto_refresh:
                    st.session_state.crawl_history_started_at = datetime.now(timezone.utc)
                    st.rerun()

            with col_action:
                if st.button(
                    "⏳ Crawler Berjalan" if crawler_running else "🔥 Ambil Data",
                    type="secondary" if crawler_running else "primary",
                    disabled=crawler_running,
                    width="stretch",
                    key="btn_manual_crawl_now"
                ):
                    st.session_state.crawl_history_started_at = datetime.now(timezone.utc)

                    with st.spinner("⏳ Mengambil tweet terbaru..."):
                        auto_crawl_job()

                    st.success("✅ Data berhasil diambil!")
                    st.rerun()

        _captured_section_gap("md")

        if st.session_state.get("auto_refresh_ui"):
            st.caption(
                "🔁 Refresh otomatis aktif. Riwayat akan ikut bertambah saat crawler menulis log baru."
            )
            _captured_section_gap("sm")
        visible_logs = get_visible_crawl_logs(logs)

        if visible_logs:
            rows = []

            for idx, log in enumerate(visible_logs, start=1):
                status = log.get("status", "")
                total_saved = int(log.get("total_saved") or 0)
                error_msg = log.get("error")

                try:
                    crawl_time = format_dt(
                        parse_dt(pd.Series([parse_log_time(log.get("timestamp"))])).iloc[0]
                    )
                except Exception:
                    crawl_time = log.get("timestamp", "-") or "-"

                if status == "success":
                    status_label = "✅ Berhasil"
                    note = (
                        f"{total_saved:,} tweet baru tersimpan"
                        if total_saved > 0 else
                        "Crawling berhasil, tidak ada tweet realtime yang cocok"
                    )
                else:
                    status_label = "❌ Gagal"
                    note = error_msg or "Terjadi kesalahan saat crawling"

                rows.append({
                    "No": idx,
                    "Waktu Crawl": crawl_time,
                    "Status": status_label,
                    "Tweet Baru": total_saved,
                    "Keterangan": note,
                })

            _section_header(
                "Riwayat Pengambilan Data",
                f"Menampilkan {len(rows)} aktivitas crawler terbaru · {NRT_INTERVAL_MINUTES} menit/interval"
            )
            _captured_section_gap("sm")

            render_standard_table(
                pd.DataFrame(rows),
                height=300,
                min_width=760,
                right_align=["Tweet Baru"],
                badge_columns=["Status"],
                nowrap=["No", "Waktu Crawl", "Status"],
                wide_columns=["Keterangan"],
                column_widths={
                    "No": "56px",
                    "Waktu Crawl": "160px",
                    "Status": "138px",
                    "Tweet Baru": "118px",
                    "Keterangan": "320px",
                },
            )
        else:
            st.info("Riwayat akan tampil setelah Anda menekan Ambil Data atau mengaktifkan Refresh Otomatis.")

        _captured_section_gap("lg")

        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(
            today,
            datetime.max.time().replace(microsecond=0)
        )
        scrape_tabs = os.getenv("SCRAPE_TABS", "LATEST,TOP")
        scrape_tabs_label = " + ".join(
            tab.strip().upper()
            for tab in scrape_tabs.split(",")
            if tab.strip()
        ) or "LATEST"

        bot_df = df_all.copy()

        if "crawl_type" in bot_df.columns:
            bot_df = bot_df[
                bot_df["crawl_type"].fillna("").str.lower().eq("realtime")
            ].copy()

        bot_df = bot_df.dropna(subset=["created_at", "crawled_at"])
        bot_df = bot_df[
            (bot_df["crawled_at"] >= pd.Timestamp(today_start)) &
            (bot_df["crawled_at"] <= pd.Timestamp(today_end)) &
            (bot_df["created_at"] >= pd.Timestamp(today_start)) &
            (bot_df["created_at"] <= pd.Timestamp(today_end))
        ].sort_values("crawled_at", ascending=False)

        bot_date_note = f"tanggal tweet hari ini ({today_start.strftime('%d/%m/%Y')})"

        _section_header(
            "🤖 Tweet yang Berhasil Diambil Bot",
            f"{len(bot_df):,} tweet baru · sumber {scrape_tabs_label} · duplikat dilewati · {bot_date_note}"
        )
        _captured_section_gap("sm")

        if bot_df.empty:
            st.info("Belum ada tweet baru yang berhasil disimpan bot hari ini.")

        else:
            bot_disp = bot_df.head(100).copy()
            bot_disp["Tanggal Tweet"] = bot_disp["created_at"].apply(format_dt)
            bot_disp["Waktu Bot Ambil"] = bot_disp["crawled_at"].apply(format_dt)

            render_standard_table(
                bot_disp[
                    [
                        "tweet_id",
                        "text",
                        "Tanggal Tweet",
                        "Waktu Bot Ambil",
                    ]
                ].rename(
                    columns={
                        "tweet_id": "ID Tweet",
                        "text": "Isi Tweet",
                    }
                ),
                height=340,
                min_width=920,
                nowrap=["ID Tweet", "Tanggal Tweet", "Waktu Bot Ambil"],
                wide_columns=["Isi Tweet"],
                column_widths={
                    "ID Tweet": "170px",
                    "Isi Tweet": "430px",
                    "Tanggal Tweet": "150px",
                    "Waktu Bot Ambil": "160px",
                },
            )

            st.caption(
                f"Menampilkan {len(bot_disp):,} dari {len(bot_df):,} tweet yang disimpan bot hari ini"
            )

    result = get_filtered_data(df_all)

    df = result["df"]
    date_col = result["date_col"]
    mode_display = result["mode_display"]
    mode_color = result["mode_color"]
    mode_icon = result["mode_icon"]
    filter_label = result["filter_label"]
    dt_start = result["dt_start"]
    dt_end = result["dt_end"]
    basis_label = result["basis_label"]
    chart_label = result["chart_label"]

    st.session_state.filter_start_date = dt_start
    st.session_state.filter_end_date = dt_end
    st.session_state.filter_label = filter_label
    st.session_state.mode_display = mode_display
    st.session_state.filter_date_column = date_col

    st.markdown(f"""
<div style="background:#fff;border-left:4px solid {mode_color};
            border-top:1.5px solid #e2e8f0;border-right:1.5px solid #e2e8f0;
            border-bottom:1.5px solid #e2e8f0;border-radius:0 12px 12px 0;
            padding:0.875rem 1.25rem;margin-bottom:1.25rem;
            box-shadow:0 2px 6px rgba(15,23,42,0.07);
            display:flex;align-items:center;gap:0.75rem;">
    <span style="font-size:1.5rem;">{mode_icon}</span>
    <div>
        <div style="font-size:0.875rem;font-weight:700;color:#0f172a;">{mode_display}</div>
        <div style="font-size:0.78rem;color:#475569;margin-top:2px;">
            Periode:
            <strong style="color:#0f172a;">{filter_label}</strong></div>
    </div>
</div>
""", unsafe_allow_html=True)

    total = len(df)
    days = (pd.Timestamp(dt_end).date() - pd.Timestamp(dt_start).date()).days + 1
    earliest = pd.Timestamp(dt_start).strftime("%d/%m/%Y")
    latest = pd.Timestamp(dt_end).strftime("%d/%m/%Y")

    _render_metrics(total, days, earliest, latest, filter_label, basis_label)
    _captured_section_gap("sm")

    if len(df) == 0:
        _section_header(
            "📋 Daftar Tweet yang Terkumpul",
            f"0 tweet · {filter_label}"
        )
        st.info("Belum ada tweet dengan tanggal asli pada periode ini.")
        return

    st.markdown("<br>", unsafe_allow_html=True)

    _render_charts(df, filter_label, date_col, chart_label, dt_start, dt_end)

    st.markdown("<br>", unsafe_allow_html=True)

    display_limit = 100

    _section_header(
        "📋 Daftar Tweet yang Terkumpul",
        f"Data dari filter aktif · {filter_label}"
    )

    df_disp = df.sort_values(date_col, ascending=False).head(display_limit).copy()
    df_disp["Tanggal Tweet"] = df_disp["created_at"].apply(format_dt)
    df_disp["Masuk Database"] = df_disp["crawled_at"].apply(format_dt)

    render_standard_table(
        df_disp[
            [
                "tweet_id",
                "text",
                "Tanggal Tweet",
                "Masuk Database"
            ]
        ].rename(
            columns={
                "tweet_id": "ID Tweet",
                "text": "Isi Tweet"
            }
        ),
        height=380,
        min_width=840,
        nowrap=["ID Tweet", "Tanggal Tweet", "Masuk Database"],
        wide_columns=["Isi Tweet"],
        column_widths={
            "ID Tweet": "180px",
            "Isi Tweet": "420px",
            "Tanggal Tweet": "150px",
            "Masuk Database": "155px",
        },
    )

    st.caption(f"Menampilkan {len(df_disp):,} dari {total:,} tweet")

    st.markdown("<br>", unsafe_allow_html=True)

    c_dl, c_nav = st.columns(2)

    with c_dl:
        st.download_button(
            f"📥 Unduh Semua Data ({total:,} tweet)",
            df.to_csv(index=False).encode("utf-8"),
            f"data_twitter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            width="stretch"
        )

    with c_nav:
        if st.button(
            "🧹 Lanjut ke Bersihkan Data →",
            type="primary",
            width="stretch",
            key="btn_go_preprocessing"
        ):
            st.session_state.current_page = "preprocessing"
            st.rerun()
