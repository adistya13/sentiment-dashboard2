import streamlit as st
import pandas as pd
import os
import re
import string
from collections import Counter
import plotly.graph_objects as go
from datetime import datetime, timedelta
from database import engine, get_tweet_count, get_latest_crawl_time
from page_modules.table_utils import render_standard_table
from timezone_utils import (
    parse_dt_with_tz,
    parse_dt_with_source_tz,
    get_timezone_label,
    get_timezone_name,
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
        tz_label = get_timezone_label(
            st.session_state.get("user_timezone", "WIB (UTC+7)")
        )
        return f"{value.strftime('%d/%m/%Y %H:%M')} {tz_label}"
    except Exception:
        return "Belum ada"


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
    dt_start = datetime.combine(start_day, datetime.min.time())
    dt_end = datetime.combine(
        end_day,
        datetime.max.time().replace(microsecond=0)
    )

    st.session_state.filter_start_date = dt_start
    st.session_state.filter_end_date = dt_end
    st.session_state.filter_label = (
        f"{dt_start.strftime('%d/%m/%Y')} s/d {dt_end.strftime('%d/%m/%Y')}"
    )
    st.session_state.mode_display = mode_display
    st.session_state.filter_date_column = "created_at"


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
            "ya", "akan", "atau", "juga", "sama", "karena",
            "jika", "sudah", "telah"
        }

    base.update({
        "rt", "amp", "https", "http", "co", "t",
        "wkwk", "wkwkwk", "haha", "hehe",
        "yg", "dgn", "utk", "dr", "krn", "tp", "jd", "sdh",
        "aja", "doang", "banget", "bgt", "nih", "sih", "dong", "deh",
    })

    return base


def _load_stemmer():
    try:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        return StemmerFactory().create_stemmer()
    except Exception:
        return None


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
    "komdigi": "komdigi",
}


def step1_cleaning(text):
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#", "", text)
    text = re.sub(r"\d+", "", text)
    text = text.translate(
        str.maketrans("", "", string.punctuation)
    )
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def step2_normalization(text):
    return " ".join(
        NORMALISASI.get(word, word)
        for word in text.split()
    )


def step3_stopword_removal(text, stopwords):
    return " ".join(
        word
        for word in text.split()
        if word not in stopwords and len(word) > 2
    )


def step4_stemming(text, stemmer):
    if stemmer is None:
        return text

    return stemmer.stem(text)


def full_preprocessing(text, stopwords, stemmer):
    s1 = step1_cleaning(text)
    s2 = step2_normalization(s1)
    s3 = step3_stopword_removal(s2, stopwords)
    s4 = step4_stemming(s3, stemmer)

    return {
        "setelah_cleaning": s1,
        "setelah_normalisasi": s2,
        "setelah_stopword": s3,
        "clean_text": s4,
    }


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


def _render_preprocessing_styles():
    st.markdown("""
<style>
.st-key-preprocessing_chart_panel,
.st-key-preprocessing_download_panel {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15,23,42,0.06) !important;
    padding: 1.1rem 1.2rem 1rem !important;
}

.st-key-preprocessing_download_panel [data-testid="stDownloadButton"] button {
    min-height: 46px !important;
    margin-bottom: 0 !important;
    border-radius: 10px !important;
}

.preprocessing-section-gap-sm { height: 1rem; }
.preprocessing-section-gap-md { height: 1.45rem; }
.preprocessing-section-gap-lg { height: 1.9rem; }
</style>
""", unsafe_allow_html=True)


def _section_gap(size="md"):
    st.markdown(
        f'<div class="preprocessing-section-gap-{size}"></div>',
        unsafe_allow_html=True
    )


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


def show():
    st.markdown("""
    <div class="top-header">
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <div style="width:36px;height:36px;background:#f0fdf4;border-radius:10px;
                        display:flex;align-items:center;justify-content:center;font-size:1.1rem;">
                🧹
            </div>
            <h1 class="page-title">Bersihkan Data</h1>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _render_preprocessing_styles()

    st.markdown("""
    <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;
                padding:1.25rem 1.5rem;box-shadow:0 2px 6px rgba(15,23,42,0.07);
                margin-bottom:1.25rem;">
        <div style="font-size:1rem;font-weight:700;color:#0f172a;margin-bottom:0.5rem;">
            📖 Apa yang dilakukan halaman ini?
        </div>
        <div style="font-size:0.8375rem;color:#475569;line-height:1.75;">
            Tweet dibersihkan melalui <strong>4 tahap preprocessing</strong>:
            <br>
            <strong>① Cleaning</strong> — hapus URL, mention, hashtag, angka, tanda baca
            &nbsp;→&nbsp;
            <strong>② Normalisasi</strong> — ubah kata tidak baku
            &nbsp;→&nbsp;
            <strong>③ Stopword Removal</strong> — hapus kata tidak bermakna
            &nbsp;→&nbsp;
            <strong>④ Stemming</strong> — ubah kata ke bentuk dasar.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "analysis_mode" not in st.session_state:
        st.warning("⚠️ Silakan pilih mode tampilan di halaman Ambil Data Twitter terlebih dahulu.")
        return

    _sync_dynamic_period()

    start_date = st.session_state.get("filter_start_date")
    end_date = st.session_state.get("filter_end_date")
    filter_label = st.session_state.get("filter_label", "-")
    mode_display = st.session_state.get("mode_display", "-")

    if start_date is None or end_date is None:
        st.warning("⚠️ Silakan buka halaman Ambil Data Twitter terlebih dahulu untuk memilih periode.")
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
            st.warning("⚠️ Belum ada data. Kembali ke halaman Ambil Data Twitter.")
            return

        df_all["created_at"] = parse_dt(df_all["created_at"])
        if "crawled_at" in df_all.columns:
            df_all["crawled_at"] = parse_crawled_dt(df_all["crawled_at"])

    except Exception as e:
        st.error(f"❌ {e}")
        return

    s_dt = pd.Timestamp(start_date)
    e_dt = pd.Timestamp(end_date)

    df = df_all[
        (df_all["created_at"] >= s_dt)
        &
        (df_all["created_at"] <= e_dt)
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
        f"pp_{st.session_state.analysis_mode}_"
        f"{start_date}_{end_date}_{total_tweets_in_db}_{latest_crawl_marker}"
    )
    
    # Clear old cache entries
    for old_key in list(st.session_state.keys()):
        if old_key.startswith("pp_") and old_key != cache_key:
            del st.session_state[old_key]
    
    force_refresh = data_marker != st.session_state.get("_pp_last_data_marker")

    if cache_key not in st.session_state or force_refresh:
        stemmer = _load_stemmer()
        stopwords = _load_stopwords()

        with st.spinner("🧹 Sedang memproses 4 tahap preprocessing..."):
            results = []

            for _, row in df.iterrows():
                r = full_preprocessing(
                    row["text"],
                    stopwords,
                    stemmer
                )

                r["tweet_id"] = row.get("tweet_id", "")
                r["text_asli"] = row["text"]
                r["created_at"] = row["created_at"]
                r["crawled_at"] = row.get("crawled_at")

                results.append(r)

            df_c = pd.DataFrame(results)

            df_c = df_c[
                df_c["clean_text"].str.strip().str.len() > 0
            ].copy()

            st.session_state[cache_key] = df_c
            st.session_state[cache_key + "_stemmer_ok"] = stemmer is not None
            st.session_state["_pp_last_data_marker"] = data_marker

    df_c = st.session_state[cache_key]
    stemmer_ok = st.session_state.get(
        cache_key + "_stemmer_ok",
        False
    )

    avg_b = df["text"].astype(str).str.len().mean()
    avg_a = df_c["clean_text"].astype(str).str.len().mean()
    red = ((avg_b - avg_a) / avg_b * 100) if avg_b > 0 else 0
    rmv = len(df) - len(df_c)

    _section_header(
        "📌 Ringkasan Preprocessing",
        f"Berdasarkan tanggal asli tweet · {filter_label}"
    )

    _section_gap("sm")

    c1, c2, c3, c4 = st.columns(4, gap="medium")

    _pill(
        c1, "📊", "#eef2ff", "#3b6cf7", "#1e3a8a",
        "Tweet Siap Dianalisis", f"{len(df_c):,}",
        "Setelah 4 tahap preprocessing"
    )

    _pill(
        c2, "📏", "#f0fdf4", "#16a34a", "#14532d",
        "Panjang Sebelum", f"{avg_b:.0f} karakter",
        "Rata-rata per tweet"
    )

    _pill(
        c3, "✨", "#fff7ed", "#ea580c", "#7c2d12",
        "Panjang Sesudah", f"{avg_a:.0f} karakter",
        "Rata-rata per tweet"
    )

    _pill(
        c4, "🗑️", "#fef2f2", "#ef4444", "#7f1d1d",
        "Reduksi Teks", f"{red:.1f}%",
        f"{rmv} tweet terlalu pendek dibuang"
    )

    _section_gap("lg")

    steps = [
        (
            "#eef2ff", "#3b6cf7", "#1e3a8a",
            "① Cleaning",
            "Ubah ke huruf kecil · Hapus URL, mention, hashtag, angka, tanda baca, karakter non-alfabet"
        ),
        (
            "#f0fdf4", "#16a34a", "#14532d",
            "② Normalisasi Kata",
            "Ubah singkatan/kata gaul seperti gk → tidak, ongkir → ongkos kirim."
        ),
        (
            "#fff7ed", "#ea580c", "#7c2d12",
            "③ Stopword Removal",
            "Hapus kata tidak bermakna, tetapi pertahankan kata negasi seperti tidak dan bukan."
        ),
        (
            "#fefce8", "#ca8a04", "#713f12",
            "④ Stemming",
            f"Ubah kata ke bentuk dasar. {'✅ Aktif' if stemmer_ok else '⚠️ Nonaktif'}"
        ),
    ]

    cols = st.columns(4, gap="medium")

    for col, (bg, color, dark, title, desc) in zip(cols, steps):
        with col:
            st.markdown(f"""
            <div style="background:{bg};border:1.5px solid {color}44;border-radius:14px;
                        padding:1rem;height:100%;">
                <div style="font-size:0.8rem;font-weight:800;color:{dark};
                            margin-bottom:0.5rem;">{title}</div>
                <div style="font-size:0.75rem;color:{dark};opacity:0.85;line-height:1.6;">
                    {desc}
                </div>
            </div>
            """, unsafe_allow_html=True)

    _section_gap("lg")

    _section_header(
        "📋 Perbandingan Teks per Tahap Preprocessing",
        f"{len(df_c):,} tweet · {filter_label}"
    )

    if "crawled_at" not in df_c.columns:
        df_c = df_c.copy()
        df_c["crawled_at"] = pd.NaT

    disp = df_c[
        [
            "tweet_id",
            "created_at",
            "crawled_at",
            "text_asli",
            "setelah_cleaning",
            "setelah_normalisasi",
            "setelah_stopword",
            "clean_text",
        ]
    ].copy()

    disp.columns = [
        "ID Tweet",
        "Tanggal Tweet",
        "Masuk Database",
        "Teks Asli",
        "① Setelah Cleaning",
        "② Setelah Normalisasi",
        "③ Setelah Stopword",
        "④ Hasil Akhir",
    ]

    disp["Tanggal Tweet"] = disp["Tanggal Tweet"].apply(format_dt)
    disp["Masuk Database"] = disp["Masuk Database"].apply(format_dt)

    render_standard_table(
        disp,
        height=350,
        min_width=1580,
        nowrap=["ID Tweet", "Tanggal Tweet", "Masuk Database"],
        wide_columns=[
            "Teks Asli",
            "① Setelah Cleaning",
            "② Setelah Normalisasi",
            "③ Setelah Stopword",
            "④ Hasil Akhir",
        ],
        column_widths={
            "ID Tweet": "160px",
            "Tanggal Tweet": "170px",
            "Masuk Database": "170px",
            "Teks Asli": "300px",
            "① Setelah Cleaning": "260px",
            "② Setelah Normalisasi": "260px",
            "③ Setelah Stopword": "260px",
            "④ Hasil Akhir": "260px",
        },
    )

    _section_gap("lg")

    with st.container(border=True, key="preprocessing_download_panel"):
        c1, c2 = st.columns(2, gap="medium", vertical_alignment="bottom")

        with c1:
            st.download_button(
                "📥 Unduh Hasil Preprocessing Lengkap",
                df_c.to_csv(index=False).encode("utf-8"),
                f"clean_tweet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv",
                width="stretch"
            )

        with c2:
            out2 = df_c[
                [
                    "tweet_id",
                    "text_asli",
                    "clean_text"
                ]
            ].copy()

            out2.columns = [
                "tweet_id",
                "tweet",
                "clean_text"
            ]

            st.download_button(
                "📥 Unduh Teks Bersih Saja",
                out2.to_csv(index=False).encode("utf-8"),
                f"teks_bersih_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv",
                width="stretch"
            )

    _section_gap("lg")

    _section_header(
        "📊 Kata-Kata yang Paling Sering Muncul",
        f"Dari {len(df_c):,} tweet yang sudah bersih"
    )

    all_words = " ".join(
        df_c["clean_text"].fillna("")
    ).split()

    stop_extra = {
        "ongkos",
        "kirim",
        "gratis",
        "komdigi"
    }

    filtered_words = [
        w for w in all_words
        if len(w) > 2 and w not in stop_extra
    ]

    word_freq = Counter(
        filtered_words
    ).most_common(20)

    if not word_freq:
        st.info("⚠️ Kata tidak cukup untuk ditampilkan.")

    else:
        words = [w[0] for w in word_freq]
        counts = [w[1] for w in word_freq]

        fig = go.Figure(data=[
            go.Bar(
                y=words[::-1],
                x=counts[::-1],
                orientation="h",
                marker=dict(color="#3b6cf7"),
                text=[str(c) for c in counts[::-1]],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Muncul %{x} kali<extra></extra>",
            )
        ])

        fig.update_layout(
            height=500,
            margin=dict(l=0, r=60, t=8, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="rgba(203,213,225,0.8)"),
            yaxis=dict(showgrid=False),
        )

        with st.container(border=True, key="preprocessing_chart_panel"):
            st.plotly_chart(
                fig,
                width="stretch",
                config={"displayModeBar": False}
            )

    _section_gap("lg")

    st.session_state["preprocessed_df"] = df_c

    if st.button(
        "📈 Lanjut ke Analisis Sentimen →",
        type="primary",
        width="stretch"
    ):
        st.session_state.current_page = "sentiment"
        st.rerun()
