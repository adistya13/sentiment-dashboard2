"""
sentiment_page.py
=================
PERBAIKAN: Hapus parameter key= dari semua st.container() karena tidak
didukung di Streamlit versi lama. CSS styling tetap berjalan via class HTML.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import string
from collections import Counter
from datetime import datetime, timedelta
from html import escape
from database import engine, get_tweet_count, get_latest_crawl_time
from timezone_utils import (
    parse_dt_with_tz,
    parse_dt_with_source_tz,
    get_timezone_label,
    get_timezone_name,
)
import plotly.graph_objects as go

from sentiment_service import (
    preprocess_for_model,
    preprocess_untuk_lexicon,
    _hitung_skor_lexicon,
    _klasifikasi_hybrid,
    _load_stopwords,
    _load_stemmer,
    _STOPWORDS,
    _STEMMER,
)

from page_modules.table_utils import render_standard_table


# ─────────────────────────────────────────────────────────────
# Timezone & formatting helpers
# ─────────────────────────────────────────────────────────────

def parse_dt(series):
    return parse_dt_with_tz(series, st.session_state.get("user_timezone", "WIB (UTC+7)"))


def parse_crawled_dt(series):
    return parse_dt_with_source_tz(
        series,
        st.session_state.get("user_timezone", "WIB (UTC+7)"),
        os.getenv("APP_TIMEZONE", "Asia/Makassar"),
    )


def format_dt(value):
    if value is None or pd.isna(value):
        return "Belum ada"
    try:
        tz_label = get_timezone_label(st.session_state.get("user_timezone", "WIB (UTC+7)"))
        return f"{value.strftime('%d/%m/%Y %H:%M')} {tz_label}"
    except Exception:
        return "Belum ada"


def format_now():
    now = parse_dt(pd.Series([datetime.utcnow().isoformat()])).iloc[0]
    return format_dt(now)


def user_today():
    timezone_choice = st.session_state.get("user_timezone", "WIB (UTC+7)")
    return pd.Timestamp.now(tz=get_timezone_name(timezone_choice)).date()


def _sync_dynamic_period():
    mode = st.session_state.get("analysis_mode")
    today = user_today()
    configs = {
        "realtime": (today - timedelta(days=6), today, "Tweet Terkini — 7 Hari Terakhir"),
        "30days":   (today - timedelta(days=29), today, "30 Hari Terakhir"),
        "captured": (today, today, "Tweet Hari Ini"),
    }
    if mode not in configs:
        return
    start_day, end_day, mode_display = configs[mode]
    start_day = pd.Timestamp(start_day).date()
    end_day   = pd.Timestamp(end_day).date()
    dt_start  = datetime.combine(start_day, datetime.min.time())
    dt_end    = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
    st.session_state.filter_start_date  = dt_start
    st.session_state.filter_end_date    = dt_end
    st.session_state.filter_label       = f"{dt_start.strftime('%d/%m/%Y')} s/d {end_day.strftime('%d/%m/%Y')}"
    st.session_state.mode_display       = mode_display
    st.session_state.filter_date_column = "created_at"


# ─────────────────────────────────────────────────────────────
# Core prediction
# ─────────────────────────────────────────────────────────────

def predict_batch_hybrid(texts):
    results = []
    for text in texts:
        teks_model   = preprocess_for_model(text)
        teks_lexicon = preprocess_untuk_lexicon(text)
        teks_lower   = str(text).lower()
        skor         = _hitung_skor_lexicon(teks_lexicon)
        label, conf  = _klasifikasi_hybrid(teks_model, skor, teks_lower)
        results.append((label, conf))
    return results


def preprocess_single(text):
    return preprocess_for_model(text)


# ─────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────

def _section_header(title, subtitle=""):
    sub_html = (
        f'<div style="font-size:0.78rem;color:#64748b;margin-top:4px;line-height:1.5;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;'
        f'padding:1rem 1.25rem;margin-bottom:1rem;box-shadow:0 2px 6px rgba(15,23,42,0.06);">'
        f'<div style="font-size:0.95rem;font-weight:700;color:#0f172a;letter-spacing:0.02em;">{title}</div>'
        f'{sub_html}</div>',
        unsafe_allow_html=True,
    )


def _section_gap(size="md"):
    heights = {"sm": "1rem", "md": "1.45rem", "lg": "1.9rem"}
    st.markdown(f'<div style="height:{heights.get(size,"1.45rem")};"></div>', unsafe_allow_html=True)


def _card_open(extra_style=""):
    """Buka div card pengganti st.container(border=True)."""
    st.markdown(
        f'<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:12px;'
        f'box-shadow:0 2px 6px rgba(15,23,42,0.06);padding:1.1rem 1.2rem 1rem;'
        f'margin-bottom:0.5rem;{extra_style}">',
        unsafe_allow_html=True,
    )


def _card_close():
    st.markdown('</div>', unsafe_allow_html=True)


def _render_sentiment_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

section[data-testid="stMain"] * {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}
.block-container { padding-top: 1rem !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }
header[data-testid="stHeader"] { height: 0 !important; min-height: 0 !important; }

.stButton > button {
    border-radius: 12px !important;
    font-weight: 700 !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    transition: all 0.18s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(59,108,247,0.18) !important;
}

.sent-pill {
    transition: transform 0.2s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s ease;
}
.sent-pill:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 24px rgba(15,23,42,0.10) !important;
}

@keyframes fadeDown {
    from { opacity: 0; transform: translateY(-10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.sent-header { animation: fadeDown 0.45s ease both; }

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.stat-1 { animation: fadeUp 0.35s 0.05s ease both; }
.stat-2 { animation: fadeUp 0.35s 0.12s ease both; }
.stat-3 { animation: fadeUp 0.35s 0.19s ease both; }
.stat-4 { animation: fadeUp 0.35s 0.26s ease both; }

.sentiment-active-context {
    display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.15rem; align-items: center;
}
.sentiment-context-pill {
    align-items: center; background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 999px; color: #475569; display: inline-flex;
    font-size: 0.73rem; font-weight: 750; gap: 0.35rem; line-height: 1.2;
    min-height: 28px; padding: 0.28rem 0.65rem; white-space: nowrap;
}
.sentiment-context-pill strong { color: #0f172a; font-weight: 850; }

.reco-card {
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.reco-card:hover {
    transform: translateX(3px);
    box-shadow: 0 6px 20px rgba(15,23,42,0.09) !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────

def _render_page_header():
    st.markdown("""
<div class="sent-header" style="
    background: linear-gradient(135deg,#ffffff 0%,#eef2ff 50%,#ede9fe 100%);
    border: 1px solid #c7d2fe;
    border-radius: 20px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(59,108,247,0.08);
    display: flex; align-items: center; gap: 1.1rem;
">
    <div style="
        width:52px;height:52px;
        background:linear-gradient(135deg,#3b6cf7,#6366f1);
        border-radius:14px;
        display:flex;align-items:center;justify-content:center;
        font-size:1.5rem;
        box-shadow:0 6px 16px rgba(99,102,241,0.35);
        flex-shrink:0;
    ">📈</div>
    <div>
        <h2 style="font-size:1.25rem;font-weight:800;color:#0f172a;
                   margin:0 0 4px;letter-spacing:-0.01em;line-height:1.2;">
            Analisis Sentimen</h2>
        <p style="font-size:0.8rem;color:#64748b;margin:0;line-height:1.5;">
            Klasifikasi otomatis tweet menggunakan Hybrid Classifier — Positif · Netral · Negatif</p>
    </div>
    <div style="
        margin-left:auto;
        background:linear-gradient(135deg,#eef2ff,#e0e7ff);
        border:1px solid #a5b4fc;
        border-radius:10px;
        padding:0.45rem 0.9rem;
        font-size:0.72rem;font-weight:700;color:#3b6cf7;
        white-space:nowrap;letter-spacing:0.04em;text-transform:uppercase;
    ">🤖 Hybrid Classifier</div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Summary Pills
# ─────────────────────────────────────────────────────────────

def _render_summary_pills(total, pos_n, neu_n, neg_n, pos_p, neu_p, neg_p, filter_label):
    pills = [
        ("stat-1", "📊", "linear-gradient(135deg,#eef2ff,#e0e7ff)", "#3b6cf7", "#1e3a8a", "#c7d2fe",
         "Total Dianalisis", f"{total:,}", f"Periode {filter_label}"),
        ("stat-2", "😊", "linear-gradient(135deg,#f0fdf4,#dcfce7)", "#16a34a", "#14532d", "#86efac",
         "Positif", f"{pos_n:,}", f"{pos_p:.1f}% dari total"),
        ("stat-3", "😐", "linear-gradient(135deg,#f8fafc,#f1f5f9)", "#64748b", "#334155", "#cbd5e1",
         "Netral", f"{neu_n:,}", f"{neu_p:.1f}% dari total"),
        ("stat-4", "😞", "linear-gradient(135deg,#fef2f2,#fee2e2)", "#ef4444", "#7f1d1d", "#fca5a5",
         "Negatif", f"{neg_n:,}", f"{neg_p:.1f}% dari total"),
    ]

    cols = st.columns(4, gap="medium")
    for col, (anim, icon, bg, color, dark, border, label, val, sub) in zip(cols, pills):
        fs = "1.6rem" if len(str(val)) <= 6 else "1.2rem"
        with col:
            st.markdown(
                f'<div class="sent-pill {anim}" style="background:{bg};border:1.5px solid {border};'
                f'border-radius:14px;padding:1.25rem 1rem;text-align:center;'
                f'box-shadow:0 2px 8px {color}15;margin-bottom:0.5rem;">'
                f'<div style="width:40px;height:40px;background:{color};border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;font-size:1.1rem;'
                f'margin:0 auto 0.65rem;box-shadow:0 4px 10px {color}44;">{icon}</div>'
                f'<div style="font-size:0.65rem;font-weight:800;color:{color};text-transform:uppercase;'
                f'letter-spacing:0.07em;margin-bottom:0.3rem;line-height:1.3;">{label}</div>'
                f'<div style="font-size:{fs};font-weight:800;color:{dark};line-height:1.15;'
                f'margin-bottom:0.25rem;">{val}</div>'
                f'<div style="font-size:0.67rem;color:{color};font-weight:600;opacity:0.9;'
                f'line-height:1.35;">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────
# Proportion Bar
# ─────────────────────────────────────────────────────────────

def _render_proportion_bar(pos_p, neu_p, neg_p):
    pos_p = round(pos_p, 1)
    neu_p = round(neu_p, 1)
    neg_p = round(neg_p, 1)

    st.markdown(
        f'<div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:12px;'
        f'padding:1rem 1.25rem;margin-bottom:0;">'
        f'<div style="font-size:0.72rem;font-weight:800;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.6rem;">Proporsi Sentimen Keseluruhan</div>'
        f'<div style="display:flex;border-radius:8px;overflow:hidden;height:28px;">'
        f'<div style="width:{pos_p}%;background:#16a34a;display:flex;align-items:center;'
        f'justify-content:center;font-size:0.68rem;font-weight:700;color:white;'
        f'white-space:nowrap;padding:0 4px;" title="Positif {pos_p}%">'
        f'{"😊 " + str(pos_p) + "%" if pos_p >= 8 else ""}</div>'
        f'<div style="width:{neu_p}%;background:#94a3b8;display:flex;align-items:center;'
        f'justify-content:center;font-size:0.68rem;font-weight:700;color:white;'
        f'white-space:nowrap;padding:0 4px;" title="Netral {neu_p}%">'
        f'{"😐 " + str(neu_p) + "%" if neu_p >= 8 else ""}</div>'
        f'<div style="width:{neg_p}%;background:#ef4444;display:flex;align-items:center;'
        f'justify-content:center;font-size:0.68rem;font-weight:700;color:white;'
        f'white-space:nowrap;padding:0 4px;" title="Negatif {neg_p}%">'
        f'{"😞 " + str(neg_p) + "%" if neg_p >= 8 else ""}</div>'
        f'</div>'
        f'<div style="display:flex;gap:1.25rem;margin-top:0.6rem;flex-wrap:wrap;">'
        f'<span style="font-size:0.7rem;color:#16a34a;font-weight:700;">● Positif {pos_p}%</span>'
        f'<span style="font-size:0.7rem;color:#94a3b8;font-weight:700;">● Netral {neu_p}%</span>'
        f'<span style="font-size:0.7rem;color:#ef4444;font-weight:700;">● Negatif {neg_p}%</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Donut + Bar chart
# ─────────────────────────────────────────────────────────────

def _render_donut_chart(pos_n, neu_n, neg_n, total, filter_label):
    labels, values, colors = [], [], []
    color_map = {"Positif": "#16a34a", "Netral": "#94a3b8", "Negatif": "#ef4444"}
    for label, val in [("Positif", pos_n), ("Netral", neu_n), ("Negatif", neg_n)]:
        if val > 0:
            labels.append(label)
            values.append(val)
            colors.append(color_map[label])

    dominant = max([("Positif", pos_n), ("Netral", neu_n), ("Negatif", neg_n)], key=lambda x: x[1])
    dom_pct  = round(dominant[1] / total * 100) if total > 0 else 0
    dom_emoji = {"Positif": "😊", "Netral": "😐", "Negatif": "😞"}.get(dominant[0], "📊")

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.62,
        marker=dict(colors=colors, line=dict(color="white", width=4)),
        textinfo="label+percent", textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>%{value:,} tweet — %{percent}<extra></extra>",
        direction="clockwise", sort=False,
    )])
    fig.add_annotation(
        text=f"<b>{dom_pct}%</b><br><span style='font-size:10px;color:#94a3b8;'>{dom_emoji} {dominant[0]}</span>",
        x=0.5, y=0.5, showarrow=False, align="center", font=dict(size=18, color="#0f172a"),
    )
    fig.update_layout(
        height=290, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", font=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    return dominant


def _render_bar_chart(pos_n, neu_n, neg_n, total):
    categories = ["Positif 😊", "Netral 😐", "Negatif 😞"]
    values     = [pos_n, neu_n, neg_n]
    colors     = ["#16a34a", "#94a3b8", "#ef4444"]
    percentages = [(v / total * 100) if total > 0 else 0 for v in values]

    fig = go.Figure()
    for cat, val, color, pct in zip(categories, values, colors, percentages):
        fig.add_trace(go.Bar(
            x=[cat], y=[val],
            marker=dict(color=color, opacity=0.88, cornerradius=8),
            text=[f"{val:,}"], textposition="outside",
            textfont=dict(size=13, color="#0f172a"), width=0.5,
            hovertemplate=f"<b>{cat}</b><br>{val:,} tweet ({pct:.1f}%)<extra></extra>",
        ))
    fig.update_layout(
        height=290, margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False, tickfont=dict(size=11, color="#64748b")),
        yaxis=dict(showgrid=True, gridcolor="rgba(226,232,240,0.8)", griddash="dot",
                   tickfont=dict(size=10, color="#94a3b8")),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────
# Trend chart
# ─────────────────────────────────────────────────────────────

def _render_trend_chart(fdf, filter_label, dt_start, dt_end):
    _section_header(
        "📅 Tren Sentimen dari Hari ke Hari",
        f"Periode {filter_label} · Diupdate: {format_now()}"
    )

    df_tl = fdf.copy()
    df_tl["date"] = pd.to_datetime(df_tl["created_at"], errors="coerce").dt.date
    actual_tl = df_tl.groupby(["date", "sentiment"]).size().reset_index(name="count")

    date_range = pd.date_range(pd.Timestamp(dt_start).date(), pd.Timestamp(dt_end).date(), freq="D")
    base_dates = pd.DataFrame({"date": date_range.date})

    fig = go.Figure()
    config_lines = [
        ("Positif", "#16a34a", "rgba(22,163,74,0.08)"),
        ("Netral",  "#94a3b8", "rgba(148,163,184,0.06)"),
        ("Negatif", "#ef4444", "rgba(239,68,68,0.08)"),
    ]
    for sent, color, fill in config_lines:
        data = base_dates.merge(
            actual_tl[actual_tl["sentiment"] == sent][["date", "count"]],
            on="date", how="left",
        )
        data["count"] = data["count"].fillna(0).astype(int)
        fig.add_trace(go.Scatter(
            x=data["date"], y=data["count"], name=sent,
            mode="lines+markers",
            line=dict(color=color, width=2.5, shape="spline", smoothing=0.8),
            marker=dict(size=6, color="white", line=dict(color=color, width=2.5)),
            fill="tozeroy", fillcolor=fill,
            hovertemplate=f"<b>{sent}</b><br>%{{x}}: <b>%{{y}} tweet</b><extra></extra>",
        ))
    fig.update_layout(
        height=290, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.1, x=0, font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="rgba(226,232,240,0.6)",
                   tickfont=dict(size=10, color="#94a3b8")),
        yaxis=dict(showgrid=True, gridcolor="rgba(226,232,240,0.6)", griddash="dot",
                   tickfont=dict(size=10, color="#94a3b8")),
        hovermode="x unified",
    )
    # ─── PERBAIKAN: hapus key= dari st.container() ───
    with st.container():
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────
# Word frequency per sentimen
# ─────────────────────────────────────────────────────────────

def _render_word_freq_per_sentiment(fdf):
    _section_header(
        "📊 Kata Dominan per Sentimen",
        "Top 15 kata paling sering muncul di masing-masing kelompok sentimen"
    )

    stop_extra = {"ongkos", "kirim", "gratis", "komdigi", "ongkir"}
    sent_cfg = [
        ("Positif", "#16a34a", "#1e3a8a"),
        ("Netral",  "#64748b", "#334155"),
        ("Negatif", "#ef4444", "#7f1d1d"),
    ]

    cols = st.columns(3, gap="medium")
    for col, (sent, color, dark) in zip(cols, sent_cfg):
        with col:
            sub = fdf[fdf["sentiment"] == sent]
            all_words = " ".join(sub["clean_text"].fillna("")).split()
            filtered  = [w for w in all_words if len(w) > 2 and w not in stop_extra]
            wf = Counter(filtered).most_common(15)

            st.markdown(
                f'<div style="background:#ffffff;border:1.5px solid {color}33;border-radius:14px;'
                f'padding:0.9rem 1rem;box-shadow:0 2px 8px {color}10;margin-bottom:0.5rem;">'
                f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem;">'
                f'<div style="width:30px;height:30px;background:{color};border-radius:8px;'
                f'display:flex;align-items:center;justify-content:center;font-size:0.9rem;">'
                f'{"😊" if sent=="Positif" else "😐" if sent=="Netral" else "😞"}</div>'
                f'<div style="font-size:0.85rem;font-weight:800;color:{dark};">{sent}</div>'
                f'<div style="margin-left:auto;font-size:0.68rem;color:{color};font-weight:700;">'
                f'{len(sub):,} tweet</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if not wf:
                st.info("Belum ada data")
                st.markdown('</div>', unsafe_allow_html=True)
                continue

            words_list  = [w[0] for w in wf]
            counts_list = [w[1] for w in wf]
            max_c = max(counts_list) if counts_list else 1

            fig = go.Figure(data=[go.Bar(
                y=words_list[::-1], x=counts_list[::-1], orientation="h",
                marker=dict(
                    color=[f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},{0.35+0.65*(c/max_c):.2f})"
                           for c in counts_list[::-1]],
                    line=dict(width=0), cornerradius=4,
                ),
                text=[str(c) for c in counts_list[::-1]],
                textposition="outside",
                textfont=dict(size=9, color="#475569"),
                hovertemplate="<b>%{y}</b><br>%{x} kali<extra></extra>",
            )])
            fig.update_layout(
                height=360, margin=dict(l=0, r=40, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="rgba(203,213,225,0.6)",
                           tickfont=dict(size=8, color="#94a3b8"), fixedrange=True),
                yaxis=dict(showgrid=False, tickfont=dict(size=9, color="#334155"), fixedrange=True),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Word cloud
# ─────────────────────────────────────────────────────────────

def _render_wordcloud(fdf):
    _section_header(
        "☁️ Word Cloud per Sentimen",
        "Kata-kata populer dari tweet yang sudah melalui preprocessing"
    )
    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt

        stop_wc = {"ongkos", "kirim", "gratis", "komdigi", "ongkir"}
        wc1, wc2, wc3 = st.columns(3, gap="medium")
        cfg = [
            (wc1, "Positif", "Greens",  "😊 Positif", "#f0fdf4", "#14532d"),
            (wc2, "Netral",  "Blues",   "😐 Netral",  "#f8fafc", "#334155"),
            (wc3, "Negatif", "Reds",    "😞 Negatif", "#fef2f2", "#7f1d1d"),
        ]
        for col, sent, cmap, title, bg, tc in cfg:
            with col:
                st.markdown(
                    f'<div style="background:{bg};border-radius:12px;padding:0.625rem 0.875rem;'
                    f'margin-bottom:0.5rem;text-align:center;">'
                    f'<span style="font-size:0.825rem;font-weight:700;color:{tc};">{title}</span></div>',
                    unsafe_allow_html=True,
                )
                sub   = fdf[fdf["sentiment"] == sent]
                words = [w for w in " ".join(sub["clean_text"].fillna("")).split()
                         if len(w) > 2 and w not in stop_wc]
                if words:
                    wc  = WordCloud(
                        width=420, height=260, background_color="white",
                        colormap=cmap, max_words=60,
                        relative_scaling=0.5, collocations=False,
                    ).generate(" ".join(words))
                    fig, ax = plt.subplots(figsize=(5, 3.1))
                    ax.imshow(wc, interpolation="bilinear")
                    ax.axis("off")
                    plt.tight_layout(pad=0)
                    st.pyplot(fig, clear_figure=True)
                else:
                    st.info("Data kata tidak cukup")
    except ImportError:
        st.warning("Install `wordcloud` dan `matplotlib` terlebih dahulu.")


# ─────────────────────────────────────────────────────────────
# Tweet table
# ─────────────────────────────────────────────────────────────

def _render_tweet_table(fdf, filter_label):
    _section_header(
        "📋 Tabel Analisis Sentimen",
        f"Total {len(fdf):,} tweet · {filter_label}"
    )

    # ─── PERBAIKAN: ganti st.container(key=) dengan st.columns biasa ───
    tf1, tf2, tf3 = st.columns([3, 1.6, 1.7], gap="medium")
    with tf1:
        search = st.text_input(
            "🔍 Cari tweet", placeholder="Ketik kata kunci di isi tweet...",
            key="sentiment_table_search",
        )
    with tf2:
        sf = st.selectbox(
            "Filter sentimen",
            ["Semua", "Positif 😊", "Netral 😐", "Negatif 😞"],
            key="sentiment_table_filter",
        )
    with tf3:
        sort_by = st.selectbox(
            "Urutkan",
            ["Terbaru dulu", "Terlama dulu", "Keyakinan tertinggi"],
            key="sentiment_table_sort",
        )

    _section_gap("sm")

    tdf = fdf.copy()
    if "crawled_at" not in tdf.columns:
        tdf["crawled_at"] = pd.NaT

    if search:
        tdf = tdf[tdf["text"].str.contains(search, case=False, na=False)]

    sf_map = {"Positif 😊": "Positif", "Netral 😐": "Netral", "Negatif 😞": "Negatif"}
    if sf != "Semua":
        tdf = tdf[tdf["sentiment"] == sf_map.get(sf, sf)]

    if sort_by == "Terbaru dulu":
        tdf = tdf.sort_values("created_at", ascending=False)
    elif sort_by == "Terlama dulu":
        tdf = tdf.sort_values("created_at", ascending=True)
    else:
        tdf = tdf.sort_values("confidence", ascending=False)

    out = tdf[["created_at", "crawled_at", "text", "clean_text", "sentiment"]].copy()
    out["created_at"]  = out["created_at"].apply(format_dt)
    out["crawled_at"]  = out["crawled_at"].apply(format_dt)
    out["sentiment"]   = out["sentiment"].map({
        "Positif": "😊 Positif", "Netral": "😐 Netral", "Negatif": "😞 Negatif",
    }).fillna(out["sentiment"])
    out.columns = ["Tanggal Tweet", "Masuk Database", "Tweet Asli", "Tweet Bersih", "Sentimen"]

    render_standard_table(
        out, height=400, min_width=1220,
        badge_columns=["Sentimen"],
        nowrap=["Tanggal Tweet", "Masuk Database", "Sentimen"],
        wide_columns=["Tweet Asli", "Tweet Bersih"],
        column_widths={
            "Tanggal Tweet": "170px", "Masuk Database": "170px",
            "Tweet Asli": "360px",   "Tweet Bersih": "360px",
            "Sentimen": "130px",
        },
    )
    st.caption(f"Menampilkan {len(tdf):,} tweet")
    return tdf


# ─────────────────────────────────────────────────────────────
# Insight & Recommendation
# ─────────────────────────────────────────────────────────────

def _render_insight_panel(dominant, pos_n, neu_n, neg_n, total, filter_label):
    dom_name = dominant[0]
    dom_pct  = dominant[1] / total * 100 if total else 0
    neg_pct  = neg_n / total * 100 if total else 0
    pos_pct  = pos_n / total * 100 if total else 0
    neu_pct  = neu_n / total * 100 if total else 0

    _section_header(
        "💡 Insight & Rekomendasi Tindakan",
        f"Berdasarkan analisis {total:,} tweet · {filter_label}"
    )

    dom_color = {"Positif": "#16a34a", "Netral": "#64748b", "Negatif": "#ef4444"}.get(dom_name, "#3b6cf7")
    dom_bg    = {"Positif": "#f0fdf4", "Netral": "#f8fafc", "Negatif": "#fef2f2"}.get(dom_name, "#eef2ff")
    dom_emoji = {"Positif": "😊", "Netral": "😐", "Negatif": "😞"}.get(dom_name, "📊")

    st.markdown(
        f'<div style="background:{dom_bg};border:1.5px solid {dom_color}33;border-radius:14px;'
        f'padding:1rem 1.25rem;margin-bottom:1rem;border-left:4px solid {dom_color};">'
        f'<div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">'
        f'<div style="font-size:1.75rem;">{dom_emoji}</div>'
        f'<div>'
        f'<div style="font-size:0.75rem;font-weight:800;color:{dom_color};text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.15rem;">Sentimen Dominan</div>'
        f'<div style="font-size:1.1rem;font-weight:800;color:{dom_color};">'
        f'{dom_name} · {dom_pct:.1f}%</div>'
        f'</div>'
        f'<div style="margin-left:auto;font-size:0.8rem;color:#64748b;">'
        f'Positif: <strong>{pos_pct:.1f}%</strong> · '
        f'Netral: <strong>{neu_pct:.1f}%</strong> · '
        f'Negatif: <strong>{neg_pct:.1f}%</strong>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    rows = []
    if neg_pct >= 40:
        rows.append(("🔴 URGENT",  "#fef2f2", "#7f1d1d", "#ef4444",
                      "Tanggapi Keluhan Publik",
                      "Sentimen negatif tinggi — ketidakpuasan signifikan",
                      "Buat klarifikasi resmi dan buka ruang dialog publik",
                      "Humas / Tim Kebijakan"))
    if neg_pct >= 20:
        rows.append(("🟠 TINGGI",  "#fff7ed", "#7c2d12", "#ea580c",
                      "Tinjau Ulang Kebijakan",
                      f"Sentimen negatif mencapai {neg_pct:.1f}%",
                      "Evaluasi poin kebijakan yang paling banyak dikeluhkan",
                      "Tim Kebijakan"))
    if neu_pct >= 30:
        rows.append(("🟡 SEDANG",  "#fefce8", "#713f12", "#ca8a04",
                      "Tingkatkan Sosialisasi",
                      f"Sentimen netral {neu_pct:.1f}% — publik belum berpihak",
                      "Perbanyak konten edukatif dan FAQ resmi",
                      "Tim Komunikasi"))
    if pos_pct >= 20:
        rows.append(("🟢 INFO",    "#f0fdf4", "#14532d", "#16a34a",
                      "Pertahankan Momentum Positif",
                      f"Sentimen positif {pos_pct:.1f}%",
                      "Perkuat narasi positif via kanal resmi secara konsisten",
                      "Tim Media Sosial"))
    rows.append(("🔵 RUTIN",   "#eff6ff", "#1e3a8a", "#3b6cf7",
                  "Pemantauan Berkelanjutan",
                  "Opini publik dapat berubah sewaktu-waktu",
                  "Pantau sentimen harian dan buat laporan berkala",
                  "Tim Analis Data"))

    df_rek = pd.DataFrame(rows, columns=["Prioritas", "bg", "tc", "bc",
                                          "Tindakan", "Dasar Analisis",
                                          "Rekomendasi", "Penanggung Jawab"])

    for _, row in df_rek.iterrows():
        st.markdown(
            f'<div class="reco-card" style="background:{row.bg};border:1.5px solid {row.bc}44;'
            f'border-radius:14px;padding:1rem 1.25rem;margin-bottom:0.75rem;'
            f'border-left:4px solid {row.bc};">'
            f'<div style="display:flex;align-items:flex-start;gap:1rem;flex-wrap:wrap;">'
            f'<div style="min-width:90px;">'
            f'<span style="font-size:0.72rem;font-weight:800;color:{row.bc};'
            f'text-transform:uppercase;letter-spacing:0.05em;">{row.Prioritas}</span></div>'
            f'<div style="flex:1;min-width:200px;">'
            f'<div style="font-size:0.875rem;font-weight:700;color:{row.tc};margin-bottom:0.25rem;">'
            f'{row.Tindakan}</div>'
            f'<div style="font-size:0.775rem;color:{row.tc};opacity:0.75;margin-bottom:0.375rem;">'
            f'📌 {row["Dasar Analisis"]}</div>'
            f'<div style="font-size:0.8rem;color:{row.tc};line-height:1.6;">'
            f'✅ {row.Rekomendasi}</div>'
            f'</div>'
            f'<div style="min-width:120px;text-align:right;">'
            f'<span style="font-size:0.72rem;background:{row.bc}22;color:{row.bc};'
            f'font-weight:700;padding:0.25rem 0.625rem;border-radius:20px;white-space:nowrap;">'
            f'👤 {row["Penanggung Jawab"]}</span></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    export_df = df_rek[["Prioritas", "Tindakan", "Dasar Analisis", "Rekomendasi", "Penanggung Jawab"]]
    return export_df


# ─────────────────────────────────────────────────────────────
# Main show()
# ─────────────────────────────────────────────────────────────

def show():
    _render_sentiment_styles()
    _render_page_header()

    if "analysis_mode" not in st.session_state:
        st.warning("⚠️ Silakan pilih mode tampilan di halaman Ambil Data Twitter terlebih dahulu.")
        return

    _sync_dynamic_period()

    start_date   = st.session_state.get("filter_start_date")
    end_date     = st.session_state.get("filter_end_date")
    filter_label = st.session_state.get("filter_label", "-")
    mode_display = st.session_state.get("mode_display", "-")

    if start_date is None or end_date is None:
        st.warning("⚠️ Silakan buka halaman Ambil Data Twitter terlebih dahulu.")
        return

    mode_meta = {
        "realtime": ("#16a34a", "📡"),
        "30days":   ("#3b6cf7", "📅"),
        "captured": ("#0284c7", "📆"),
        "custom":   ("#d97706", "🔍"),
    }
    mode_color, mode_icon = mode_meta.get(st.session_state.analysis_mode, ("#3b6cf7", "📊"))

    st.markdown(
        f'<div style="background:#fff;border-left:4px solid {mode_color};'
        f'border-top:1.5px solid #e2e8f0;border-right:1.5px solid #e2e8f0;'
        f'border-bottom:1.5px solid #e2e8f0;border-radius:0 12px 12px 0;'
        f'padding:0.875rem 1.25rem;margin-bottom:1.5rem;'
        f'box-shadow:0 2px 6px rgba(15,23,42,0.07);'
        f'display:flex;align-items:center;gap:0.75rem;">'
        f'<span style="font-size:1.375rem;">{mode_icon}</span>'
        f'<div>'
        f'<div style="font-size:0.875rem;font-weight:700;color:#0f172a;">{mode_display}</div>'
        f'<div style="font-size:0.78rem;color:#475569;margin-top:2px;">'
        f'Periode: <strong style="color:{mode_color};">{filter_label}</strong></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Load data ─────────────────────────────────────────────
    try:
        df_all = pd.read_sql("SELECT * FROM tweets ORDER BY created_at DESC", engine)
        if df_all.empty:
            st.warning("⚠️ Belum ada data tweet.")
            return
        df_all["created_at"] = parse_dt(df_all["created_at"])
        if "crawled_at" in df_all.columns:
            df_all["crawled_at"] = parse_crawled_dt(df_all["crawled_at"])
    except Exception as e:
        st.error(f"❌ Gagal membaca database: {e}")
        return

    s_dt = pd.Timestamp(start_date)
    e_dt = pd.Timestamp(end_date)
    df   = df_all[(df_all["created_at"] >= s_dt) & (df_all["created_at"] < e_dt)].copy()

    if df.empty:
        st.warning(f"⚠️ Tidak ada tweet dalam periode {filter_label}.")
        return

    # ── Caching ───────────────────────────────────────────────
    total_tweets_in_db  = get_tweet_count()
    latest_crawl_marker = get_latest_crawl_time() or "no-crawl"
    data_marker = (total_tweets_in_db, latest_crawl_marker)
    cache_key   = (
        f"sent_{st.session_state.analysis_mode}_"
        f"{start_date}_{end_date}_{total_tweets_in_db}_{latest_crawl_marker}"
    )

    for old_key in list(st.session_state.keys()):
        if old_key.startswith("sent_") and old_key != cache_key:
            del st.session_state[old_key]

    force_refresh = data_marker != st.session_state.get("_last_sentiment_data_marker")

    if cache_key not in st.session_state or force_refresh:
        if force_refresh:
            st.info("🔄 Menyegarkan prediksi sentimen dengan data terbaru...")
        with st.spinner("🔍 Preprocessing & prediksi sentimen (Hybrid Classifier)..."):
            df["clean_text"] = df["text"].apply(preprocess_single)
            dfc = df[df["clean_text"].str.strip().str.len() > 0].copy()

            results = predict_batch_hybrid(dfc["text"].tolist())
            if results:
                sentiments, confidences = zip(*results)
            else:
                sentiments, confidences = [], []

            dfc["sentiment"]  = list(sentiments)
            dfc["confidence"] = list(confidences)

            st.session_state[cache_key]                      = dfc
            st.session_state["_last_sentiment_data_marker"] = data_marker

    df_s = st.session_state[cache_key]

    # ── Keyword filter ────────────────────────────────────────
    _section_header("🎯 Filter Kata Kunci", "Kosongkan untuk melihat semua tweet")

    # ─── PERBAIKAN: hapus key= dari st.container() ───
    with st.container():
        kw = st.text_input(
            "Kata kunci", placeholder="Contoh: ongkir, kurir, komdigi...",
            key="sentiment_keyword_search",
        )
        st.markdown(
            f'<div class="sentiment-active-context">'
            f'<span class="sentiment-context-pill" style="border-color:{mode_color}33;'
            f'background:{mode_color}0f;color:{mode_color};">'
            f'Mode <strong style="color:{mode_color};">{escape(str(mode_display))}</strong></span>'
            f'<span class="sentiment-context-pill">'
            f'Periode <strong>{escape(str(filter_label))}</strong></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _section_gap("sm")

    fdf = (
        df_s[df_s["text"].str.contains(kw, case=False, na=False)].copy()
        if kw else df_s.copy()
    )

    if fdf.empty:
        st.warning("⚠️ Tidak ada tweet yang cocok dengan kata kunci tersebut.")
        return

    sc    = fdf["sentiment"].value_counts()
    total = len(fdf)
    pos_n = int(sc.get("Positif", 0))
    neu_n = int(sc.get("Netral",  0))
    neg_n = int(sc.get("Negatif", 0))
    pos_p = pos_n / total * 100
    neu_p = neu_n / total * 100
    neg_p = neg_n / total * 100

    # ── Ringkasan ─────────────────────────────────────────────
    _section_header(
        "📌 Ringkasan Sentimen",
        f"Berdasarkan tanggal asli tweet · {filter_label}"
    )
    _section_gap("sm")
    _render_summary_pills(total, pos_n, neu_n, neg_n, pos_p, neu_p, neg_p, filter_label)
    _section_gap("sm")
    _render_proportion_bar(pos_p, neu_p, neg_p)
    _section_gap("lg")

    # ── Donut + Bar ───────────────────────────────────────────
    col_left, col_right = st.columns(2, gap="medium")
    with col_left:
        _section_header("🔵 Sebaran Sentimen", f"Periode {filter_label}")
        # ─── PERBAIKAN: hapus key= dari st.container() ───
        with st.container():
            dominant = _render_donut_chart(pos_n, neu_n, neg_n, total, filter_label)
    with col_right:
        _section_header("📊 Perbandingan Jumlah per Sentimen", f"Periode {filter_label}")
        with st.container():
            _render_bar_chart(pos_n, neu_n, neg_n, total)
    _section_gap("lg")

    # ── Trend ─────────────────────────────────────────────────
    _render_trend_chart(fdf, filter_label, start_date, end_date)
    _section_gap("lg")

    # ── Word freq ─────────────────────────────────────────────
    _render_word_freq_per_sentiment(fdf)
    _section_gap("lg")

    # ── Word cloud ────────────────────────────────────────────
    _render_wordcloud(fdf)
    _section_gap("lg")

    # ── Tweet table ───────────────────────────────────────────
    tdf = _render_tweet_table(fdf, filter_label)
    _section_gap("lg")

    # ── Insight ───────────────────────────────────────────────
    df_rek = _render_insight_panel(dominant, pos_n, neu_n, neg_n, total, filter_label)
    _section_gap("lg")

    # ── Download ──────────────────────────────────────────────
    _section_header("📥 Unduh Hasil Analisis")

    # ─── PERBAIKAN: hapus key= dari st.container() ───
    with st.container():
        d1, d2, d3 = st.columns(3, gap="medium")

        with d1:
            st.download_button(
                "📥 Semua Hasil Prediksi",
                fdf.to_csv(index=False).encode("utf-8"),
                f"hasil_prediksi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
            )
        with d2:
            summary = pd.DataFrame({
                "Sentimen": ["Positif", "Netral", "Negatif"],
                "Jumlah":   [pos_n, neu_n, neg_n],
                "Persen":   [f"{pos_p:.2f}%", f"{neu_p:.2f}%", f"{neg_p:.2f}%"],
            })
            st.download_button(
                "📈 Ringkasan Sentimen",
                summary.to_csv(index=False).encode("utf-8"),
                f"ringkasan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
            )
        with d3:
            st.download_button(
                "🎯 Rekomendasi Tindakan",
                df_rek.to_csv(index=False).encode("utf-8"),
                f"rekomendasi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
            )