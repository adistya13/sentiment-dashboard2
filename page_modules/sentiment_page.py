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
import joblib

from page_modules.table_utils import render_standard_table


model = joblib.load("model_naive_bayes.pkl")
tfidf = joblib.load("tfidf_vectorizer.pkl")


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
        tz_label = get_timezone_label(
            st.session_state.get("user_timezone", "WIB (UTC+7)")
        )
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
        "realtime": (
            today - timedelta(days=6),
            today,
            "Tweet Terkini — 7 Hari Terakhir",
        ),
        "30days": (
            today - timedelta(days=29),
            today,
            "30 Hari Terakhir",
        ),
        "captured": (
            today,
            today,
            "Tweet Hari Ini",
        ),
    }

    if mode not in configs:
        return

    start_day, end_day, mode_display = configs[mode]
    start_day = pd.Timestamp(start_day).date()
    end_day = pd.Timestamp(end_day).date()
    # Gunakan timestamp yang lebih inklusif untuk end_date
    dt_start = datetime.combine(start_day, datetime.min.time())
    dt_end = datetime.combine(
        end_day + timedelta(days=1),  # Termasuk seluruh hari end_day
        datetime.min.time()
    )

    st.session_state.filter_start_date = dt_start
    st.session_state.filter_end_date = dt_end
    st.session_state.filter_label = (
        f"{dt_start.strftime('%d/%m/%Y')} s/d {end_day.strftime('%d/%m/%Y')}"
    )
    st.session_state.mode_display = mode_display
    st.session_state.filter_date_column = "created_at"


NORMALISASI = {
    "gk": "tidak",
    "ga": "tidak",
    "gak": "tidak",
    "nggak": "tidak",
    "ngga": "tidak",
    "tdk": "tidak",
    "tak": "tidak",
    "yg": "yang",
    "dgn": "dengan",
    "utk": "untuk",
    "org": "orang",
    "krn": "karena",
    "dr": "dari",
    "tp": "tapi",
    "tpi": "tapi",
    "sm": "sama",
    "jd": "jadi",
    "sdh": "sudah",
    "blm": "belum",
    "emg": "memang",
    "emang": "memang",
    "gimana": "bagaimana",
    "gitu": "begitu",
    "gini": "begini",
    "bgt": "banget",
    "ongkir": "ongkos kirim",
    "freeongkir": "gratis ongkir",
    "free": "gratis",
    "ecommerce": "e commerce",
}


def _load_stopwords():
    stopword_file = "indonesian-stopwords-complete.txt"
    base = set()

    try:
        with open(stopword_file, "r", encoding="utf-8") as f:
            base = set(f.read().splitlines())

        for kata in ["tidak", "bukan", "jangan", "kurang", "lebih"]:
            base.discard(kata)

    except FileNotFoundError:
        base = {
            "yang", "dan", "di", "ke", "dari", "ini", "itu",
            "dengan", "untuk", "pada", "adalah", "oleh", "ada",
            "ya", "akan", "atau", "juga"
        }

    base.update({
        "rt", "amp", "https", "http", "co", "t",
        "wkwk", "wkwkwk", "haha", "hehe",
        "yg", "dgn", "utk", "dr", "krn", "tp", "jd", "sdh",
        "aja", "doang", "banget", "bgt", "nih", "sih", "dong", "deh",
    })

    return base


def _get_stemmer():
    try:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        return StemmerFactory().create_stemmer()
    except Exception:
        return None


def preprocess(text, stopwords, stemmer):
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#", "", text)
    text = re.sub(r"\d+", "", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    text = " ".join(
        NORMALISASI.get(word, word)
        for word in text.split()
    )

    text = " ".join(
        word
        for word in text.split()
        if word not in stopwords and len(word) > 2
    )

    if stemmer:
        text = stemmer.stem(text)

    return text


def predict_batch(texts):
    vectors = tfidf.transform(texts)
    preds = model.predict(vectors)

    confidences = []

    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(vectors)
        confidences = probs.max(axis=1)
    else:
        confidences = np.ones(len(preds))

    final = []

    for pred, conf in zip(preds, confidences):
        p = str(pred).lower()

        if p == "positif":
            sentiment = "Positif"
        elif p == "negatif":
            sentiment = "Negatif"
        elif p == "netral":
            sentiment = "Netral"
        else:
            sentiment = str(pred).capitalize()

        final.append((sentiment, float(conf)))

    return final


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


def _render_sentiment_styles():
    st.markdown("""
<style>
.st-key-sentiment_keyword_panel,
.st-key-sentiment_table_controls,
.st-key-sentiment_download_panel {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.06) !important;
    margin-bottom: 0.3rem !important;
    padding: 0.75rem 1rem 0.8rem !important;
}

.st-key-sentiment_keyword_panel [data-testid="stVerticalBlock"] {
    gap: 0.35rem !important;
}

.st-key-sentiment_keyword_panel [data-testid="stTextInput"] label p,
.st-key-sentiment_table_controls [data-testid="stTextInput"] label p,
.st-key-sentiment_table_controls [data-testid="stSelectbox"] label p {
    color: #334155 !important;
    font-size: 0.72rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.04em !important;
    line-height: 1.2 !important;
    margin-bottom: 0.22rem !important;
    text-transform: uppercase !important;
}

.st-key-sentiment_keyword_panel [data-testid="stTextInput"],
.st-key-sentiment_keyword_panel [data-testid="stTextInput"] > div {
    margin-bottom: 0 !important;
}

.st-key-sentiment_keyword_panel [data-testid="stTextInput"] input,
.st-key-sentiment_table_controls [data-testid="stTextInput"] input {
    background: #ffffff !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    caret-color: #0f172a !important;
    min-height: 46px !important;
    border-radius: 10px !important;
}

.st-key-sentiment_keyword_panel [data-baseweb="input"],
.st-key-sentiment_table_controls [data-baseweb="input"],
.st-key-sentiment_table_controls [data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: #e2e8f0 !important;
    color: #0f172a !important;
    min-height: 46px !important;
    border-radius: 10px !important;
}

.st-key-sentiment_keyword_panel [data-baseweb="input"] *,
.st-key-sentiment_table_controls [data-baseweb="input"] *,
.st-key-sentiment_table_controls [data-baseweb="select"] * {
    color: #0f172a !important;
}

.st-key-sentiment_keyword_panel input::placeholder,
.st-key-sentiment_table_controls input::placeholder {
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
}

.st-key-sentiment_keyword_panel .stButton > button,
.st-key-sentiment_download_panel [data-testid="stDownloadButton"] button {
    min-height: 46px !important;
    margin-bottom: 0 !important;
    border-radius: 10px !important;
}

.st-key-sentiment_keyword_panel .stButton > button {
    font-size: 0.92rem !important;
    font-weight: 750 !important;
    padding: 0.68rem 1rem !important;
}

.sentiment-active-context {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.15rem;
}

.sentiment-context-pill {
    align-items: center;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 999px;
    color: #475569;
    display: inline-flex;
    font-size: 0.73rem;
    font-weight: 750;
    gap: 0.35rem;
    line-height: 1.2;
    min-height: 28px;
    padding: 0.28rem 0.65rem;
    white-space: nowrap;
}

.sentiment-context-pill strong {
    color: #0f172a;
    font-weight: 850;
}

.sentiment-info-chip {
    align-items: center;
    background: #f8fafc;
    border: 1.5px solid #e2e8f0;
    border-radius: 10px;
    display: flex;
    min-height: 46px;
    padding: 0.55rem 0.75rem;
}

.sentiment-info-chip-label {
    color: #64748b;
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    line-height: 1.2;
    margin-bottom: 0.18rem;
    text-transform: uppercase;
}

.sentiment-info-chip-value {
    color: #0f172a;
    font-size: 0.8rem;
    font-weight: 800;
    line-height: 1.25;
}

.sentiment-section-gap-sm { height: 1rem; }
.sentiment-section-gap-md { height: 1.45rem; }
.sentiment-section-gap-lg { height: 1.9rem; }
</style>
""", unsafe_allow_html=True)


def _section_gap(size="md"):
    st.markdown(
        f'<div class="sentiment-section-gap-{size}"></div>',
        unsafe_allow_html=True
    )


def _info_chip(label, value, color="#3b6cf7"):
    st.markdown(f"""
<div class="sentiment-info-chip" style="border-color:{color}33;background:{color}0f;">
    <div>
        <div class="sentiment-info-chip-label">{label}</div>
        <div class="sentiment-info-chip-value" style="color:{color};">{value}</div>
    </div>
</div>
""", unsafe_allow_html=True)


def _pill(col, icon, bg, color, dark, label, val, sub):
    """Render metric pill card with consistent styling"""
    with col:
        fs = "1.25rem" if len(str(val)) <= 8 else "1rem"

        st.markdown(f"""
<div style="background:{bg};border:1.5px solid {color};border-radius:14px;
            padding:1.5rem 1.25rem;text-align:center;
            box-shadow:0 2px 8px {color}15;transition:all 0.2s ease;
            min-height:178px;margin-bottom:0.65rem;">
    <div style="width:44px;height:44px;background:{color};border-radius:12px;
                display:flex;align-items:center;justify-content:center;
                font-size:1.25rem;margin:0 auto 0.875rem;flex-shrink:0;color:white;">{icon}</div>
    <div style="font-size:0.7rem;font-weight:700;color:{dark};
                text-transform:uppercase;letter-spacing:0.06em;
                margin-bottom:0.4rem;line-height:1.3;">{label}</div>
    <div style="font-size:{fs};font-weight:800;color:{dark};line-height:1.2;margin-bottom:0.5rem;">{val}</div>
    <div style="font-size:0.7rem;color:{color};font-weight:600;line-height:1.4;">{sub}</div>
</div>
""", unsafe_allow_html=True)


def _render_pie_chart(pos_n, neu_n, neg_n, total, filter_label):
    _section_header(
        "🔵 Sebaran Sentimen",
        f"Periode {filter_label} · Diupdate: {format_now()}"
    )

    labels = []
    values = []
    colors = []

    color_map = {
        "Positif": "#16a34a",
        "Netral": "#94a3b8",
        "Negatif": "#ef4444",
    }

    for label, val in [
        ("Positif", pos_n),
        ("Netral", neu_n),
        ("Negatif", neg_n)
    ]:
        if val > 0:
            labels.append(label)
            values.append(val)
            colors.append(color_map[label])

    dominant = max(
        [
            ("Positif", pos_n),
            ("Netral", neu_n),
            ("Negatif", neg_n)
        ],
        key=lambda x: x[1]
    )

    dom_pct = round(
        dominant[1] / total * 100
    ) if total > 0 else 0

    dom_emoji = {
        "Positif": "😊",
        "Netral": "😐",
        "Negatif": "😞"
    }.get(dominant[0], "📊")

    fig = go.Figure(data=[
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(
                colors=colors,
                line=dict(color="white", width=4)
            ),
            textinfo="label+percent",
            textfont=dict(size=12),
            hovertemplate="<b>%{label}</b><br>%{value:,} tweet — %{percent}<extra></extra>",
            direction="clockwise",
            sort=False,
        )
    ])

    fig.add_annotation(
        text=f"<b>{dom_pct}%</b><br><span style='font-size:10px;color:#94a3b8;'>{dom_emoji} {dominant[0]}</span>",
        x=0.5,
        y=0.5,
        showarrow=False,
        align="center",
        font=dict(size=20, color="#0f172a")
    )

    fig.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(
            orientation="h",
            y=-0.08,
            x=0.5,
            xanchor="center",
            font=dict(size=11)
        ),
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False}
    )

    return dominant


def _render_bar_chart(pos_n, neu_n, neg_n, filter_label, total):
    _section_header(
        "📊 Perbandingan Jumlah Tweet per Sentimen",
        f"Periode {filter_label} · Diupdate: {format_now()}"
    )

    categories = ["Positif 😊", "Netral 😐", "Negatif 😞"]
    values = [pos_n, neu_n, neg_n]
    colors = ["#16a34a", "#94a3b8", "#ef4444"]
    
    # Hitung persentase
    percentages = [
        (v / total * 100) if total > 0 else 0
        for v in values
    ]

    fig = go.Figure()

    for cat, val, color, pct in zip(categories, values, colors, percentages):
        fig.add_trace(
            go.Bar(
                x=[cat],
                y=[val],
                marker=dict(color=color, opacity=0.88),
                text=[f"{val:,}"],
                textposition="outside",
                textfont=dict(size=14, color="#0f172a"),
                width=0.5,
                hovertemplate=f"<b>{cat}</b><br>{val:,} tweet ({pct:.1f}%)<extra></extra>",
            )
        )

    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(226,232,240,0.8)",
            griddash="dot",
        ),
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False}
    )


def _render_trend_chart(fdf, filter_label, dt_start, dt_end):
    _section_header(
        "📅 Tren Sentimen dari Hari ke Hari",
        f"Periode {filter_label} · Diupdate: {format_now()}"
    )

    df_tl = fdf.copy()
    df_tl["date"] = pd.to_datetime(
        df_tl["created_at"],
        errors="coerce"
    ).dt.date

    actual_tl = (
        df_tl
        .groupby(["date", "sentiment"])
        .size()
        .reset_index(name="count")
    )

    date_range = pd.date_range(
        pd.Timestamp(dt_start).date(),
        pd.Timestamp(dt_end).date(),
        freq="D"
    )

    base_dates = pd.DataFrame({"date": date_range.date})

    fig = go.Figure()

    config = [
        ("Positif", "#16a34a", "rgba(22,163,74,0.08)"),
        ("Netral", "#94a3b8", "rgba(148,163,184,0.06)"),
        ("Negatif", "#ef4444", "rgba(239,68,68,0.08)"),
    ]

    for sent, color, fill in config:
        data = base_dates.merge(
            actual_tl[actual_tl["sentiment"] == sent][["date", "count"]],
            on="date",
            how="left"
        )
        data["count"] = data["count"].fillna(0).astype(int)

        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["count"],
                name=sent,
                mode="lines+markers",
                line=dict(
                    color=color,
                    width=2.5,
                    shape="spline",
                    smoothing=0.8
                ),
                marker=dict(
                    size=6,
                    color="white",
                    line=dict(color=color, width=2.5)
                ),
                fill="tozeroy",
                fillcolor=fill,
                hovertemplate=f"<b>{sent}</b><br>%{{x}}: <b>%{{y}} tweet</b><extra></extra>",
            )
        )

    fig.update_layout(
        height=290,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            orientation="h",
            y=1.1,
            x=0,
            font=dict(size=11)
        ),
        xaxis=dict(showgrid=True, gridcolor="rgba(226,232,240,0.6)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(226,232,240,0.6)", griddash="dot"),
        hovermode="x unified",
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False}
    )


def _render_wordcloud(fdf):
    _section_header(
        "☁️ Kata-Kata Populer per Sentimen",
        "Word Cloud dari tweet yang sudah melalui preprocessing"
    )

    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt

        stop_wc = {
            "ongkos",
            "kirim",
            "gratis",
            "komdigi",
            "ongkir"
        }

        wc1, wc2, wc3 = st.columns(3, gap="medium")

        cfg = [
            (wc1, "Positif", "Greens", "😊 Positif", "#f0fdf4", "#14532d"),
            (wc2, "Netral", "Blues", "😐 Netral", "#f8fafc", "#334155"),
            (wc3, "Negatif", "Reds", "😞 Negatif", "#fef2f2", "#7f1d1d"),
        ]

        for col, sent, cmap, title, bg, tc in cfg:
            with col:
                st.markdown(f"""
                <div style="background:{bg};border-radius:12px;padding:0.625rem 0.875rem;
                            margin-bottom:0.5rem;text-align:center;">
                    <span style="font-size:0.825rem;font-weight:700;color:{tc};">{title}</span>
                </div>
                """, unsafe_allow_html=True)

                sub = fdf[
                    fdf["sentiment"] == sent
                ]

                words = [
                    w
                    for w in " ".join(
                        sub["clean_text"].fillna("")
                    ).split()
                    if len(w) > 2 and w not in stop_wc
                ]

                if words:
                    wc = WordCloud(
                        width=420,
                        height=260,
                        background_color="white",
                        colormap=cmap,
                        max_words=60,
                        relative_scaling=0.5,
                        collocations=False,
                    ).generate(" ".join(words))

                    fig, ax = plt.subplots(figsize=(5, 3.1))
                    ax.imshow(wc, interpolation="bilinear")
                    ax.axis("off")
                    plt.tight_layout(pad=0)

                    st.pyplot(
                        fig,
                        clear_figure=True
                    )

                else:
                    st.info("Data kata tidak cukup")

    except ImportError:
        st.warning("Install wordcloud dan matplotlib terlebih dahulu.")


def _render_tweet_table(fdf, filter_label):
    _section_header(
        "📋 Tabel Analisis Sentimen",
        f"Total {len(fdf):,} tweet · {filter_label}"
    )

    with st.container(border=True, key="sentiment_table_controls"):
        tf1, tf2, tf3 = st.columns(
            [3, 1.6, 1.7],
            gap="medium",
            vertical_alignment="bottom"
        )

        with tf1:
            search = st.text_input(
                "Search tweet",
                placeholder="Ketik kata kunci di isi tweet...",
                key="sentiment_table_search"
            )

        with tf2:
            sf = st.selectbox(
                "Filter sentimen",
                ["Semua", "Positif 😊", "Netral 😐", "Negatif 😞"],
                key="sentiment_table_filter"
            )

        with tf3:
            sort_by = st.selectbox(
                "Urutkan",
                ["Terbaru dulu", "Terlama dulu", "Keyakinan tertinggi"],
                key="sentiment_table_sort"
            )

    _section_gap("sm")

    tdf = fdf.copy()

    if "crawled_at" not in tdf.columns:
        tdf["crawled_at"] = pd.NaT

    if search:
        tdf = tdf[
            tdf["text"].str.contains(
                search,
                case=False,
                na=False
            )
        ]

    sf_map = {
        "Positif 😊": "Positif",
        "Netral 😐": "Netral",
        "Negatif 😞": "Negatif",
    }

    if sf != "Semua":
        tdf = tdf[
            tdf["sentiment"] == sf_map.get(sf, sf)
        ]

    if sort_by == "Terbaru dulu":
        tdf = tdf.sort_values(
            "created_at",
            ascending=False
        )

    elif sort_by == "Terlama dulu":
        tdf = tdf.sort_values(
            "created_at",
            ascending=True
        )

    else:
        tdf = tdf.sort_values(
            "confidence",
            ascending=False
        )

    out = tdf[
        [
            "created_at",
            "crawled_at",
            "text",
            "clean_text",
            "sentiment",
            "confidence"
        ]
    ].copy()

    out["created_at"] = out["created_at"].apply(format_dt)
    out["crawled_at"] = out["crawled_at"].apply(format_dt)

    out["confidence"] = out["confidence"].apply(
        lambda x: f"{x:.0%}"
    )

    out["sentiment"] = out["sentiment"].map({
        "Positif": "😊 Positif",
        "Netral": "😐 Netral",
        "Negatif": "😞 Negatif",
    }).fillna(out["sentiment"])

    out.columns = [
        "Tanggal Tweet",
        "Masuk Database",
        "Tweet Asli",
        "Tweet Bersih",
        "Sentimen",
        "Keyakinan"
    ]

    render_standard_table(
        out,
        height=400,
        min_width=1220,
        badge_columns=["Sentimen"],
        nowrap=["Tanggal Tweet", "Masuk Database", "Sentimen", "Keyakinan"],
        wide_columns=["Tweet Asli", "Tweet Bersih"],
        column_widths={
            "Tanggal Tweet": "170px",
            "Masuk Database": "170px",
            "Tweet Asli": "360px",
            "Tweet Bersih": "360px",
            "Sentimen": "130px",
            "Keyakinan": "110px",
        },
    )

    st.caption(
        f"Menampilkan {len(tdf):,} tweet"
    )

    return tdf


def _render_policy_recommendations(dominant, pos_n, neu_n, neg_n, total, filter_label):
    dom_name = dominant[0]
    dom_pct = dominant[1] / total * 100 if total else 0

    _section_header(
        "🎯 Rekomendasi Tindakan & Insight Kebijakan",
        f"Berdasarkan analisis {total:,} tweet · {filter_label}"
    )

    c1, c2, c3, c4 = st.columns(4, gap="medium")

    _pill(
        c1,
        {"Positif": "😊", "Netral": "😐", "Negatif": "😞"}.get(dom_name, "📊"),
        {"Positif": "#f0fdf4", "Netral": "#f8fafc", "Negatif": "#fef2f2"}.get(dom_name, "#eef2ff"),
        {"Positif": "#16a34a", "Netral": "#64748b", "Negatif": "#ef4444"}.get(dom_name, "#3b6cf7"),
        {"Positif": "#14532d", "Netral": "#334155", "Negatif": "#7f1d1d"}.get(dom_name, "#1e3a8a"),
        "Sentimen Dominan",
        f"{dom_pct:.1f}%",
        dom_name
    )

    _pill(
        c2, "😊", "#f0fdf4", "#16a34a", "#14532d",
        "Positif", f"{pos_n:,}", "Total tweet positif"
    )

    _pill(
        c3, "😐", "#f8fafc", "#64748b", "#334155",
        "Netral", f"{neu_n:,}", "Total tweet netral"
    )

    _pill(
        c4, "😞", "#fef2f2", "#ef4444", "#7f1d1d",
        "Negatif", f"{neg_n:,}", "Total tweet negatif"
    )

    _section_gap("sm")

    neg_pct = neg_n / total * 100 if total else 0
    pos_pct = pos_n / total * 100 if total else 0
    neu_pct = neu_n / total * 100 if total else 0

    rows = []

    if neg_pct >= 40:
        rows.append((
            "🔴 URGENT",
            "Tanggapi Keluhan Publik",
            "Sentimen negatif tinggi menunjukkan ketidakpuasan signifikan",
            "Buat klarifikasi resmi dan buka ruang dialog publik",
            "Humas / Tim Kebijakan"
        ))

    if neg_pct >= 20:
        rows.append((
            "🟠 TINGGI",
            "Tinjau Ulang Kebijakan",
            f"Sentimen negatif mencapai {neg_pct:.1f}%",
            "Evaluasi poin kebijakan yang paling banyak dikeluhkan",
            "Tim Kebijakan"
        ))

    if neu_pct >= 30:
        rows.append((
            "🟡 SEDANG",
            "Tingkatkan Sosialisasi",
            f"Sentimen netral {neu_pct:.1f}% menunjukkan banyak publik belum berpihak",
            "Perbanyak konten edukatif dan FAQ resmi",
            "Tim Komunikasi"
        ))

    if pos_pct >= 40:
        rows.append((
            "🟢 INFO",
            "Pertahankan Momentum Positif",
            f"Sentimen positif {pos_pct:.1f}%",
            "Perkuat narasi positif dan gunakan kanal resmi secara konsisten",
            "Tim Media Sosial"
        ))

    rows.append((
        "🔵 RUTIN",
        "Pemantauan Berkelanjutan",
        "Opini publik dapat berubah sewaktu-waktu",
        "Pantau sentimen harian dan buat laporan berkala",
        "Tim Analis Data"
    ))

    df_rek = pd.DataFrame(
        rows,
        columns=[
            "Prioritas",
            "Tindakan",
            "Dasar Analisis",
            "Rekomendasi Konkret",
            "Penanggung Jawab"
        ]
    )

    priority_color = {
        "🔴 URGENT": ("#fef2f2", "#7f1d1d", "#ef4444"),
        "🟠 TINGGI": ("#fff7ed", "#7c2d12", "#ea580c"),
        "🟡 SEDANG": ("#fefce8", "#713f12", "#ca8a04"),
        "🟢 INFO": ("#f0fdf4", "#14532d", "#16a34a"),
        "🔵 RUTIN": ("#eff6ff", "#1e3a8a", "#3b6cf7"),
    }

    for _, row in df_rek.iterrows():
        bg, tc, bc = priority_color.get(
            row["Prioritas"],
            ("#f8fafc", "#0f172a", "#64748b")
        )

        st.markdown(f"""
        <div style="background:{bg};border:1.5px solid {bc}44;border-radius:14px;
                    padding:1rem 1.25rem;margin-bottom:0.75rem;
                    border-left:4px solid {bc};">
            <div style="display:flex;align-items:flex-start;gap:1rem;flex-wrap:wrap;">
                <div style="min-width:90px;">
                    <span style="font-size:0.72rem;font-weight:800;color:{bc};
                                 text-transform:uppercase;letter-spacing:0.05em;">
                        {row["Prioritas"]}
                    </span>
                </div>
                <div style="flex:1;min-width:200px;">
                    <div style="font-size:0.875rem;font-weight:700;color:{tc};
                                margin-bottom:0.25rem;">
                        {row["Tindakan"]}
                    </div>
                    <div style="font-size:0.775rem;color:{tc};opacity:0.75;
                                margin-bottom:0.375rem;">
                        📌 {row["Dasar Analisis"]}
                    </div>
                    <div style="font-size:0.8rem;color:{tc};line-height:1.6;">
                        ✅ {row["Rekomendasi Konkret"]}
                    </div>
                </div>
                <div style="min-width:120px;text-align:right;">
                    <span style="font-size:0.72rem;background:{bc}22;color:{bc};
                                 font-weight:700;padding:0.25rem 0.625rem;
                                 border-radius:20px;white-space:nowrap;">
                        👤 {row["Penanggung Jawab"]}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    return df_rek


def show():
    st.markdown("""
    <div class="top-header">
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <div style="width:36px;height:36px;background:#eef2ff;border-radius:10px;
                        display:flex;align-items:center;justify-content:center;font-size:1.1rem;">
                📈
            </div>
            <h1 class="page-title">Analisis Sentimen</h1>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _render_sentiment_styles()

    if "analysis_mode" not in st.session_state:
        st.warning("⚠️ Silakan pilih mode tampilan di halaman Ambil Data Twitter terlebih dahulu.")
        return

    _sync_dynamic_period()

    start_date = st.session_state.get("filter_start_date")
    end_date = st.session_state.get("filter_end_date")
    filter_label = st.session_state.get("filter_label", "-")
    mode_display = st.session_state.get("mode_display", "-")

    if start_date is None or end_date is None:
        st.warning("⚠️ Silakan buka halaman Ambil Data Twitter terlebih dahulu.")
        return

    mode_meta = {
        "realtime": ("#16a34a", "📡"),
        "30days": ("#3b6cf7", "📅"),
        "captured": ("#0284c7", "📆"),
        "custom": ("#d97706", "🔍"),
    }

    mode_color, mode_icon = mode_meta.get(
        st.session_state.analysis_mode,
        ("#3b6cf7", "📊")
    )

    st.markdown(f"""
    <div style="background:#fff;border-left:4px solid {mode_color};
                border-top:1.5px solid #e2e8f0;border-right:1.5px solid #e2e8f0;
                border-bottom:1.5px solid #e2e8f0;border-radius:0 12px 12px 0;
                padding:0.875rem 1.25rem;margin-bottom:1.25rem;
                box-shadow:0 2px 6px rgba(15,23,42,0.07);
                display:flex;align-items:center;gap:0.75rem;">
        <span style="font-size:1.375rem;">{mode_icon}</span>
        <div>
            <div style="font-size:0.875rem;font-weight:700;color:#0f172a;">{mode_display}</div>
            <div style="font-size:0.78rem;color:#475569;margin-top:2px;">
                Periode: <strong style="color:#0f172a;">{filter_label}</strong>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        df_all = pd.read_sql(
            "SELECT * FROM tweets ORDER BY created_at DESC",
            engine
        )

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

    # Filter dengan lebih toleran - gunakan < untuk end_date karena sudah incremented
    df = df_all[
        (df_all["created_at"] >= s_dt)
        &
        (df_all["created_at"] < e_dt)
    ].copy()

    if df.empty:
        st.warning(
            f"⚠️ Tidak ada tweet dengan tanggal asli dalam periode {filter_label}."
        )
        return

    total_tweets_in_db = get_tweet_count()
    latest_crawl_marker = get_latest_crawl_time() or "no-crawl"
    data_marker = (total_tweets_in_db, latest_crawl_marker)
    
    cache_key = (
        f"sent_{st.session_state.analysis_mode}_"
        f"{start_date}_{end_date}_{total_tweets_in_db}_{latest_crawl_marker}"
    )

    # Clear old cache entries untuk memastikan data selalu fresh
    for old_key in list(st.session_state.keys()):
        if old_key.startswith("sent_") and old_key != cache_key:
            del st.session_state[old_key]

    force_refresh = data_marker != st.session_state.get("_last_sentiment_data_marker")
    
    if cache_key not in st.session_state or force_refresh:
        if force_refresh:
            st.info("🔄 Menyegarkan prediksi sentimen dengan data terbaru...")
        
        with st.spinner("🔍 Preprocessing & prediksi sentimen seluruh tweet..."):
            stopwords = _load_stopwords()
            stemmer = _get_stemmer()

            df["clean_text"] = df["text"].apply(
                lambda t: preprocess(t, stopwords, stemmer)
            )

            dfc = df[
                df["clean_text"].str.strip().str.len() > 0
            ].copy()

            results = predict_batch(
                dfc["clean_text"].tolist()
            )

            if results:
                sentiments, confidences = zip(*results)
            else:
                sentiments, confidences = [], []

            dfc["sentiment"] = list(sentiments)
            dfc["confidence"] = list(confidences)

            st.session_state[cache_key] = dfc
            st.session_state["_last_sentiment_data_marker"] = data_marker

    df_s = st.session_state[cache_key]

    _section_header(
        "🎯 Filter Kata Kunci",
        "Kosongkan untuk melihat semua tweet"
    )

    with st.container(border=True, key="sentiment_keyword_panel"):
        kw = st.text_input(
            "Kata kunci",
            placeholder="Contoh: ongkir, kurir, komdigi...",
            key="sentiment_keyword_search"
        )

        st.markdown(f"""
<div class="sentiment-active-context">
    <span class="sentiment-context-pill" style="border-color:{mode_color}33;background:{mode_color}0f;color:{mode_color};">
        Mode <strong style="color:{mode_color};">{escape(str(mode_display))}</strong>
    </span>
    <span class="sentiment-context-pill">
        Periode <strong>{escape(str(filter_label))}</strong>
    </span>
</div>
""", unsafe_allow_html=True)

    _section_gap("sm")

    fdf = (
        df_s[
            df_s["text"].str.contains(
                kw,
                case=False,
                na=False
            )
        ].copy()
        if kw else df_s.copy()
    )

    if fdf.empty:
        st.warning("⚠️ Tidak ada tweet yang cocok dengan kata kunci tersebut.")
        return

    sc = fdf["sentiment"].value_counts()
    total = len(fdf)

    pos_n = int(sc.get("Positif", 0))
    neu_n = int(sc.get("Netral", 0))
    neg_n = int(sc.get("Negatif", 0))

    pos_p = pos_n / total * 100
    neu_p = neu_n / total * 100
    neg_p = neg_n / total * 100

    _section_header(
        "📌 Ringkasan Sentimen",
        f"Berdasarkan tanggal asli tweet · {filter_label}"
    )

    _section_gap("sm")

    c1, c2, c3, c4 = st.columns(4, gap="medium")

    _pill(
        c1, "📊", "#eef2ff", "#3b6cf7", "#1e3a8a",
        "Total Tweet Dianalisis", f"{total:,}", f"Periode {filter_label}"
    )

    _pill(
        c2, "😊", "#f0fdf4", "#16a34a", "#14532d",
        "Positif", f"{pos_n:,}", f"{pos_p:.1f}% dari total"
    )

    _pill(
        c3, "😐", "#f8fafc", "#64748b", "#334155",
        "Netral", f"{neu_n:,}", f"{neu_p:.1f}% dari total"
    )

    _pill(
        c4, "😞", "#fef2f2", "#ef4444", "#7f1d1d",
        "Negatif", f"{neg_n:,}", f"{neg_p:.1f}% dari total"
    )

    _section_gap("lg")

    col_left, col_right = st.columns(2, gap="medium")

    with col_left:
        dominant = _render_pie_chart(
            pos_n,
            neu_n,
            neg_n,
            total,
            filter_label
        )

    with col_right:
        _render_bar_chart(
            pos_n,
            neu_n,
            neg_n,
            filter_label,
            total
        )

    _section_gap("lg")

    _render_trend_chart(
        fdf,
        filter_label,
        start_date,
        end_date
    )

    _section_gap("lg")

    _render_wordcloud(fdf)

    _section_gap("lg")

    tdf = _render_tweet_table(
        fdf,
        filter_label
    )

    _section_gap("lg")

    df_rek = _render_policy_recommendations(
        dominant,
        pos_n,
        neu_n,
        neg_n,
        total,
        filter_label
    )

    _section_gap("lg")

    _section_header("📥 Unduh Hasil Analisis")

    with st.container(border=True, key="sentiment_download_panel"):
        d1, d2, d3 = st.columns(
            3,
            gap="medium",
            vertical_alignment="bottom"
        )

        with d1:
            st.download_button(
                "📥 Semua Hasil Prediksi",
                fdf.to_csv(index=False).encode("utf-8"),
                f"hasil_prediksi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                width="stretch"
            )

        with d2:
            summary = pd.DataFrame({
                "Sentimen": ["Positif", "Netral", "Negatif"],
                "Jumlah": [pos_n, neu_n, neg_n],
                "Persen": [
                    f"{pos_p:.2f}%",
                    f"{neu_p:.2f}%",
                    f"{neg_p:.2f}%"
                ],
            })

            st.download_button(
                "📈 Ringkasan Sentimen",
                summary.to_csv(index=False).encode("utf-8"),
                f"ringkasan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                width="stretch"
            )

        with d3:
            st.download_button(
                "🎯 Rekomendasi Tindakan",
                df_rek.to_csv(index=False).encode("utf-8"),
                f"rekomendasi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                width="stretch"
            )
