"""
preprocessing_page.py
=====================
Halaman Bersihkan Data — NLP Pipeline 6 Tahap.

PIPELINE 6 TAHAP (selaras dengan sentiment_service.py):
  1. Case Folding     — ubah semua huruf jadi lowercase
  2. Cleaning         — hapus URL, mention, hashtag, angka, emoji, tanda baca
  3. Normalisasi      — singkatan/slang → kata baku
  4. Tokenizing       — pecah kalimat → list token
  5. Stopword Removal — hapus kata umum; JAGA kata sentimen penting
  6. Stemming         — bentuk dasar kata via Sastrawi ECS
"""

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


# ═══════════════════════════════════════════════════════════
#  TIMEZONE HELPERS
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
    mode  = st.session_state.get("analysis_mode")
    today = user_today()

    configs = {
        "realtime": (today - timedelta(days=6), today, "Tweet Terkini — 7 Hari Terakhir"),
        "30days":   (today - timedelta(days=29), today, "30 Hari Terakhir"),
        "captured": (today, today, "Tweet Hari Ini"),
    }

    if mode not in configs:
        return

    start_day, end_day, mode_display = configs[mode]
    dt_start = datetime.combine(start_day, datetime.min.time())
    dt_end   = datetime.combine(end_day,   datetime.max.time().replace(microsecond=0))

    st.session_state.filter_start_date  = dt_start
    st.session_state.filter_end_date    = dt_end
    st.session_state.filter_label       = f"{dt_start.strftime('%d/%m/%Y')} s/d {dt_end.strftime('%d/%m/%Y')}"
    st.session_state.mode_display       = mode_display
    st.session_state.filter_date_column = "created_at"


# ═══════════════════════════════════════════════════════════
#  PREPROCESSING PIPELINE — 6 TAHAP
#  PENTING: Pipeline ini harus IDENTIK dengan sentiment_service.py
#  agar token yang dihasilkan konsisten dengan training model.
#
#  URUTAN:
#    1. Case Folding     → lowercase dulu sebelum cleaning
#    2. Cleaning         → hapus noise setelah lowercase
#    3. Normalisasi      → singkatan/slang → kata baku
#    4. Tokenizing       → split menjadi list token
#    5. Stopword Removal → buang kata umum, jaga kata sentimen
#    6. Stemming         → bentuk dasar via Sastrawi ECS
# ═══════════════════════════════════════════════════════════

KATA_SENTIMEN_PENTING = {
    # Negasi
    "tidak", "bukan", "jangan", "kurang", "belum", "tanpa",
    # Positif
    "keren", "bagus", "mantap", "setuju", "dukung", "mendukung",
    "andal", "handal", "gercep", "bangga", "senang", "suka",
    "baik", "benar", "tepat", "oke",
    "sejahtera", "berkembang", "maju", "inovatif",
    "tegas", "sigap", "tanggap", "adil", "bijak", "bermanfaat",
    "untung", "berhasil", "sukses", "solusi", "manfaat",
    "berguna", "membantu", "bantu", "pro", "lanjut",
    "sangat", "banget", "sekali", "paling", "amat", "luar", "biasa",
    # Negatif
    "kecewa", "buruk", "jelek", "parah", "gagal", "hancur",
    "rusak", "bohong", "tipu", "korupsi",
    # Emosi
    "marah", "sedih", "khawatir",
}


def _load_stopwords():
    stopword_file = "indonesian-stopwords-complete.txt"
    base = set()
    try:
        with open(stopword_file, "r", encoding="utf-8") as f:
            base = set(f.read().splitlines())
    except FileNotFoundError:
        base = {
            "yang", "dan", "di", "ke", "dari", "ini", "itu",
            "dengan", "untuk", "pada", "adalah", "oleh", "ada",
            "ya", "akan", "atau", "juga", "sama", "karena",
            "jika", "sudah", "telah",
        }
    for kata in KATA_SENTIMEN_PENTING:
        base.discard(kata)
    base.update({
        "rt", "amp", "https", "http", "co", "t",
        "wkwk", "wkwkwk", "haha", "hehe", "xixi",
        "yg", "dgn", "utk", "dr", "krn", "tp", "jd", "sdh",
        "aja", "doang", "nih", "sih", "dong", "deh",
        "loh", "lah", "tuh", "kak", "gan",
    })
    return base


def _load_stemmer():
    try:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        return StemmerFactory().create_stemmer()
    except Exception:
        return None


NORMALISASI = {
    # Negasi
    "gk": "tidak", "ga": "tidak", "gak": "tidak",
    "nggak": "tidak", "ngga": "tidak", "tdk": "tidak",
    "tak": "tidak", "enggak": "tidak", "engga": "tidak",
    "kagak": "tidak", "kaga": "tidak", "ndak": "tidak",
    "gkk": "tidak", "ngak": "tidak",
    # Kata ganti
    "yg": "yang", "dgn": "dengan", "utk": "untuk",
    "org": "orang", "krn": "karena", "dr": "dari",
    "sm": "sama", "pd": "pada", "dlm": "dalam",
    "bwt": "buat", "trm": "terima",
    # Verba
    "tp": "tapi", "tpi": "tapi", "jd": "jadi",
    "sdh": "sudah", "blm": "belum", "emg": "memang",
    "emang": "memang", "gimana": "bagaimana",
    "gitu": "begitu", "gini": "begini",
    "udah": "sudah", "udh": "sudah",
    "mau": "mau",
    # Intensitas
    "bgt": "banget", "bngt": "banget", "bget": "banget", "bgtt": "banget",
    # Positif informal
    "bener": "benar", "beneran": "benar",
    "mantep": "mantap", "mntap": "mantap",
    "kece": "keren", "kece bgt": "keren banget",
    "cucok": "cocok", "cucuk": "cocok",
    "cakep": "bagus", "oke bgt": "oke banget",
    "sip": "baik", "siipp": "baik",
    "top": "terbaik", "topbgt": "terbaik banget",
    "jos": "bagus", "josss": "bagus",
    "goks": "luar biasa",
    "setujuu": "setuju", "stuju": "setuju",
    "dukung": "dukung",
    "proud": "bangga",
    "mantul": "mantap betul",
    # Negatif informal
    "ancur": "hancur", "ancrr": "hancur",
    "parahh": "parah", "parahhh": "parah",
    "gagall": "gagal",
    "ngaco": "tidak benar",
    "ngasal": "tidak benar",
    "receh": "tidak penting",
    "gaje": "tidak jelas",
    "asal": "sembarangan",
    # Domain
    "ongkir": "ongkos kirim",
    "freeongkir": "gratis ongkos kirim",
    "gratisongkir": "gratis ongkos kirim",
    "free": "gratis",
    "ecommerce": "e commerce",
    "komdigi": "komdigi",
    "subsidi": "subsidi",
    "marketplace": "marketplace",
    "seller": "penjual",
    "buyer": "pembeli",
    "online": "online",
    "shopee": "shopee",
    "tokopedia": "tokopedia",
    "lazada": "lazada",
    "tiktok": "tiktok",
}


# ── Tahap 1: Case Folding ───────────────────────────────────────────────────
def step1_case_folding(text: str) -> str:
    return str(text).lower()


# ── Tahap 2: Cleaning ───────────────────────────────────────────────────────
def step2_cleaning(text: str) -> str:
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\d+", "", text)
    text = re.sub(
        r"[\U00010000-\U0010ffff"
        r"\U0001F600-\U0001F64F"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF"
        r"\u2600-\u26FF\u2700-\u27BF"
        r"]+", "", text, flags=re.UNICODE
    )
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Tahap 3: Normalisasi ────────────────────────────────────────────────────
def step3_normalization(text: str) -> str:
    return " ".join(NORMALISASI.get(word, word) for word in text.split())


# ── Tahap 4: Tokenizing ─────────────────────────────────────────────────────
def step4_tokenizing(text: str) -> list:
    return text.split()


# ── Tahap 5: Stopword Removal ───────────────────────────────────────────────
def step5_stopword_removal(tokens: list, stopwords: set) -> list:
    return [
        w for w in tokens
        if (w not in stopwords or w in KATA_SENTIMEN_PENTING) and len(w) > 2
    ]


# ── Tahap 6: Stemming ───────────────────────────────────────────────────────
def step6_stemming(tokens: list, stemmer) -> list:
    if stemmer is None:
        return tokens
    return [stemmer.stem(w) for w in tokens]


def full_preprocessing(text: str, stopwords: set, stemmer):
    """
    Jalankan 6 tahap preprocessing dan kembalikan dict hasil setiap tahap.

    URUTAN TAHAP:
      1. Case Folding     → lowercase
      2. Cleaning         → hapus noise
      3. Normalisasi      → normalisasi kata
      4. Tokenizing       → split token
      5. Stopword Removal → buang stopword
      6. Stemming         → bentuk dasar
    """
    s1_fold     = step1_case_folding(text)
    s2_clean    = step2_cleaning(s1_fold)
    s3_norm     = step3_normalization(s2_clean)
    s4_tokens   = step4_tokenizing(s3_norm)
    s5_filtered = step5_stopword_removal(s4_tokens, stopwords)
    s6_stemmed  = step6_stemming(s5_filtered, stemmer)

    return {
        "setelah_casefolding": s1_fold,
        "setelah_cleaning":    s2_clean,
        "setelah_normalisasi": s3_norm,
        "setelah_tokenizing":  " | ".join(s4_tokens),
        "setelah_stopword":    " ".join(s5_filtered),
        "clean_text":          " ".join(s6_stemmed),
        "_tokens_raw":         s4_tokens,
        "_tokens_clean":       s6_stemmed,
    }


# ═══════════════════════════════════════════════════════════
#  UI HELPERS
# ═══════════════════════════════════════════════════════════

def _section_header(title, subtitle=""):
    sub_html = (
        f'<div style="font-size:0.75rem;color:#64748b;margin-top:4px;line-height:1.5;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(f"""
<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:0.9rem 1.25rem;margin-bottom:1rem;
            box-shadow:0 2px 6px rgba(15,23,42,0.05);">
    <div style="font-size:0.9rem;font-weight:700;color:#0f172a;letter-spacing:0.01em;">{title}</div>
    {sub_html}
</div>
""", unsafe_allow_html=True)


def _gap(size="md"):
    heights = {"xs": "0.6rem", "sm": "1rem", "md": "1.45rem", "lg": "2rem"}
    st.markdown(f'<div style="height:{heights.get(size,"1.45rem")};"></div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  STYLES
# ═══════════════════════════════════════════════════════════

def _render_preprocessing_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

section[data-testid="stMain"] * {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}
.block-container { padding-top: 1rem !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }
header[data-testid="stHeader"] { height: 0 !important; min-height: 0 !important; }

.pipeline-step {
    transition: transform 0.2s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s ease;
}
.pipeline-step:hover {
    transform: translateY(-4px) scale(1.01);
    box-shadow: 0 12px 28px rgba(15,23,42,0.12) !important;
}

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

@keyframes fadeDown {
    from { opacity:0; transform:translateY(-10px); }
    to   { opacity:1; transform:translateY(0); }
}
.pp-header { animation: fadeDown 0.45s ease both; }

@keyframes fadeRight {
    from { opacity:0; transform:translateX(-12px); }
    to   { opacity:1; transform:translateX(0); }
}
.pipe-1 { animation: fadeRight 0.35s 0.05s ease both; }
.pipe-2 { animation: fadeRight 0.35s 0.12s ease both; }
.pipe-3 { animation: fadeRight 0.35s 0.19s ease both; }
.pipe-4 { animation: fadeRight 0.35s 0.26s ease both; }
.pipe-5 { animation: fadeRight 0.35s 0.33s ease both; }
.pipe-6 { animation: fadeRight 0.35s 0.40s ease both; }

.example-box { transition: all 0.18s ease; }
.example-box:hover {
    border-color: #93c5fd !important;
    box-shadow: 0 4px 14px rgba(59,108,247,0.10) !important;
}

.token-chip {
    display: inline-block;
    background: #eef2ff;
    color: #3b6cf7;
    border: 1px solid #c7d2fe;
    border-radius: 5px;
    padding: 1px 7px;
    font-size: 0.7rem;
    font-weight: 600;
    margin: 2px 2px 0 0;
    line-height: 1.6;
}

.fix-badge {
    display: inline-block;
    background: #fef9c3;
    color: #854d0e;
    border: 1px solid #fde68a;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.65rem;
    font-weight: 700;
    margin-left: 6px;
    vertical-align: middle;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  PAGE HEADER
# ═══════════════════════════════════════════════════════════

def _render_page_header():
    st.markdown("""
<div class="pp-header" style="
    background: linear-gradient(135deg,#ffffff 0%,#f0fdf4 50%,#ecfdf5 100%);
    border: 1px solid #d1fae5;
    border-radius: 20px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(16,163,74,0.08);
    display: flex; align-items: center; gap: 1.1rem;
">
    <div style="
        width:52px;height:52px;
        background:linear-gradient(135deg,#16a34a,#059669);
        border-radius:14px;
        display:flex;align-items:center;justify-content:center;
        font-size:1.5rem;
        box-shadow:0 6px 16px rgba(16,163,74,0.35);
        flex-shrink:0;
    ">🧹</div>
    <div>
        <h2 style="font-size:1.25rem;font-weight:800;color:#0f172a;
                   margin:0 0 4px;letter-spacing:-0.01em;line-height:1.2;">
            Bersihkan Data</h2>
        <p style="font-size:0.8rem;color:#64748b;margin:0;line-height:1.5;">
            Preprocessing teks 6 tahap otomatis:
            <strong style="color:#059669;">Case Folding → Cleaning → Normalisasi → Tokenizing → Stopword Removal → Stemming</strong>
        </p>
    </div>
    <div style="
        margin-left:auto;
        background:linear-gradient(135deg,#f0fdf4,#dcfce7);
        border:1px solid #86efac;
        border-radius:10px;
        padding:0.45rem 0.9rem;
        font-size:0.72rem;font-weight:700;color:#16a34a;
        white-space:nowrap;letter-spacing:0.04em;text-transform:uppercase;
    ">✨ NLP Pipeline</div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  PIPELINE STEPS CARDS
# ═══════════════════════════════════════════════════════════

def _render_pipeline_steps(stemmer_ok):
    steps = [
        {
            "num": "01", "anim": "pipe-1",
            "icon": "🔡", "color": "#0284c7", "dark": "#0c4a6e",
            "bg": "linear-gradient(135deg,#eff6ff,#dbeafe)", "border": "#bfdbfe",
            "title": "Case Folding",
            "desc": "Menyeragamkan semua huruf menjadi lowercase sebelum proses lainnya.",
            "items": [
                '"Gratis" → "gratis"',
                '"ONGKIR" → "ongkir"',
                '"KEREN" → "keren"',
                "Seluruh karakter → huruf kecil",
                "Dilakukan pertama agar cleaning konsisten",
                "Basis untuk normalisasi & stopword",
            ],
        },
        {
            "num": "02", "anim": "pipe-2",
            "icon": "🧽", "color": "#3b6cf7", "dark": "#1e3a8a",
            "bg": "linear-gradient(135deg,#eef2ff,#e0e7ff)", "border": "#c7d2fe",
            "title": "Cleaning",
            "desc": "Menghapus semua elemen noise yang tidak bermakna dari teks.",
            "items": [
                "Hapus URL (http, https, www)",
                "Hapus mention (@username)",
                "Hapus hashtag (#topik)",
                "Hapus angka & digit",
                "Hapus emoji & simbol unicode",
                "Hapus tanda baca & karakter non-latin",
            ],
        },
        {
            "num": "03", "anim": "pipe-3",
            "icon": "🔄", "color": "#16a34a", "dark": "#14532d",
            "bg": "linear-gradient(135deg,#f0fdf4,#dcfce7)", "border": "#86efac",
            "title": 'Normalisasi <span class="fix-badge">✦ Diperluas</span>',
            "desc": "Mengubah kata tidak baku, singkatan, dan slang menjadi kata baku.",
            "items": [
                "gk/ga/gak/kagak → tidak",
                "ongkir → ongkos kirim",
                "mantep → mantap",
                "kece → keren",
                "jos/josss → bagus",
                "free → gratis",
            ],
        },
        {
            "num": "04", "anim": "pipe-4",
            "icon": "✂️", "color": "#7c3aed", "dark": "#3b0764",
            "bg": "linear-gradient(135deg,#f5f3ff,#ede9fe)", "border": "#c4b5fd",
            "title": "Tokenizing",
            "desc": "Memecah kalimat menjadi unit kata (token) individual.",
            "items": [
                "Pisahkan berdasarkan spasi",
                '"keren banget" → [keren, banget]',
                "Setiap token diproses mandiri",
                "Hasil: daftar kata terpisah",
                "Input untuk stopword removal",
                "Ditampilkan sebagai chip per token",
            ],
        },
        {
            "num": "05", "anim": "pipe-5",
            "icon": "🚫", "color": "#ea580c", "dark": "#7c2d12",
            "bg": "linear-gradient(135deg,#fff7ed,#ffedd5)", "border": "#fed7aa",
            "title": 'Stopword Removal <span class="fix-badge">✦ Diperbaiki</span>',
            "desc": "Membuang kata umum; kata sentimen penting DIJAGA.",
            "items": [
                "Hapus kata umum (dan, di, ke...)",
                "Hapus token < 3 karakter",
                "JAGA negasi: tidak, bukan, jangan",
                "JAGA positif: keren, bagus, mantap",
                "JAGA evaluatif: setuju, dukung, bijak",
                "JAGA intensitas: banget, sangat, sekali",
            ],
        },
        {
            "num": "06", "anim": "pipe-6",
            "icon": "🌱", "color": "#ca8a04", "dark": "#713f12",
            "bg": "linear-gradient(135deg,#fefce8,#fef9c3)", "border": "#fde68a",
            "title": "Stemming",
            "desc": "Mengubah kata ke bentuk dasar via ECS Sastrawi.",
            "items": [
                "berlari → lari",
                "makanan → makan",
                "pembatasan → batas",
                "pengiriman → kirim",
                f"Status: {'✅ Sastrawi aktif' if stemmer_ok else '⚠️ Sastrawi tidak tersedia'}",
                "Algoritma: Enhanced Confix Stripping",
            ],
        },
    ]

    row1 = st.columns(3, gap="medium")
    for col, step in zip(row1, steps[:3]):
        _render_step_card(col, step)

    _gap("sm")

    row2 = st.columns(3, gap="medium")
    for col, step in zip(row2, steps[3:]):
        _render_step_card(col, step)


def _render_step_card(col, step):
    items_html = "".join(
        f'<div style="display:flex;align-items:flex-start;gap:0.4rem;margin-bottom:0.28rem;">'
        f'<span style="color:{step["color"]};font-size:0.62rem;margin-top:3px;flex-shrink:0;">▶</span>'
        f'<span style="font-size:0.71rem;color:{step["dark"]};opacity:0.88;line-height:1.5;">{item}</span>'
        f'</div>'
        for item in step["items"]
    )
    with col:
        st.markdown(f"""
<div class="pipeline-step {step['anim']}" style="
    background:{step['bg']};
    border:1.5px solid {step['border']};
    border-radius:16px;
    padding:1.1rem 1rem 1rem;
    box-shadow:0 2px 8px {step['color']}14;
    position:relative;overflow:hidden;
    min-height: 230px;
">
    <div style="position:absolute;top:-12px;right:-12px;
                width:58px;height:58px;background:{step['color']}10;
                border-radius:50%;"></div>
    <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.65rem;">
        <div style="width:36px;height:36px;background:{step['color']};border-radius:10px;
                    display:flex;align-items:center;justify-content:center;
                    font-size:1rem;box-shadow:0 4px 10px {step['color']}44;flex-shrink:0;">
            {step['icon']}</div>
        <div>
            <div style="font-size:0.58rem;font-weight:700;color:{step['color']};
                        letter-spacing:0.08em;text-transform:uppercase;">Tahap {step['num']}</div>
            <div style="font-size:0.88rem;font-weight:800;color:{step['dark']};line-height:1.2;">
                {step['title']}</div>
        </div>
    </div>
    <div style="font-size:0.69rem;color:{step['dark']};opacity:0.7;
                line-height:1.5;margin-bottom:0.6rem;font-style:italic;">
        {step['desc']}</div>
    <div style="border-top:1px solid {step['border']};padding-top:0.55rem;">
        {items_html}
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  FLOW ARROW
# ═══════════════════════════════════════════════════════════

def _render_flow_arrow():
    nodes = [
        ("📄 Teks Asli",    "#94a3b8", "#f8fafc",  "#e2e8f0"),
        ("① Case Folding",  "#0284c7", "#eff6ff",  "#bfdbfe"),
        ("② Cleaning",      "#3b6cf7", "#eef2ff",  "#c7d2fe"),
        ("③ Normalisasi",   "#16a34a", "#f0fdf4",  "#86efac"),
        ("④ Tokenizing",    "#7c3aed", "#f5f3ff",  "#c4b5fd"),
        ("⑤ Stopword",      "#ea580c", "#fff7ed",  "#fed7aa"),
        ("⑥ Stemming",      "#ca8a04", "#fefce8",  "#fde68a"),
        ("✅ Teks Bersih",  "#0f172a", "#0f172a",  "#334155"),
    ]

    parts = ""
    for i, (label, color, bg, border) in enumerate(nodes):
        text_c = "#f8fafc" if label == "✅ Teks Bersih" else color
        parts += (
            f'<div style="background:{bg};border:1.5px solid {border};border-radius:8px;'
            f'padding:0.28rem 0.6rem;font-size:0.68rem;font-weight:700;color:{text_c};'
            f'white-space:nowrap;">{label}</div>'
        )
        if i < len(nodes) - 1:
            next_color = nodes[i + 1][1]
            parts += (
                f'<div style="display:flex;align-items:center;">'
                f'<div style="width:22px;height:2px;'
                f'background:linear-gradient(90deg,{color},{next_color});"></div>'
                f'<div style="width:0;height:0;border-top:5px solid transparent;'
                f'border-bottom:5px solid transparent;'
                f'border-left:7px solid {next_color};margin-left:-1px;"></div>'
                f'</div>'
            )

    st.markdown(f"""
<div style="display:flex;align-items:center;flex-wrap:nowrap;
            overflow-x:auto;gap:0;padding:0.5rem 0 1rem;margin-bottom:0.5rem;">
    {parts}
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  STAT PILLS
# ═══════════════════════════════════════════════════════════

def _render_stat_pills(total_raw, total_clean, avg_tokens_before, avg_tokens_after, removed):
    c1, c2, c3, c4 = st.columns(4, gap="medium")

    cards = [
        (c1, "📥", "linear-gradient(135deg,#eef2ff,#e0e7ff)", "#3b6cf7", "#1e3a8a", "#c7d2fe",
         "Tweet Diproses", f"{total_raw:,}", "Total tweet periode ini"),
        (c2, "✅", "linear-gradient(135deg,#f0fdf4,#dcfce7)", "#16a34a", "#14532d", "#86efac",
         "Tweet Siap Analisis", f"{total_clean:,}", "Lulus semua 6 tahap"),
        (c3,
         "🗑️" if removed > 0 else "✅",
         ("linear-gradient(135deg,#fff7ed,#ffedd5)" if removed > 0 else "linear-gradient(135deg,#f0fdf4,#dcfce7)"),
         ("#ea580c" if removed > 0 else "#16a34a"),
         ("#7c2d12" if removed > 0 else "#14532d"),
         ("#fed7aa" if removed > 0 else "#86efac"),
         "Tweet Dibuang", f"{removed:,}",
         ("Teks kosong setelah preprocessing" if removed > 0 else "Semua tweet lolos")),
        (c4, "🔤", "linear-gradient(135deg,#f5f3ff,#ede9fe)", "#7c3aed", "#3b0764", "#c4b5fd",
         "Rata-rata Token",
         f"{avg_tokens_before:.0f} → {avg_tokens_after:.0f}",
         "Sebelum → Sesudah stopword"),
    ]

    for col, icon, bg, color, dark, border, label, val, sub in cards:
        with col:
            fs = "1.1rem" if len(str(val)) > 8 else "1.55rem"
            st.markdown(f"""
<div style="background:{bg};border:1.5px solid {border};
            border-radius:14px;padding:1.1rem 0.9rem;text-align:center;
            box-shadow:0 2px 8px {color}14;margin-bottom:0.5rem;">
    <div style="width:38px;height:38px;background:{color};border-radius:10px;
                display:flex;align-items:center;justify-content:center;
                font-size:1rem;margin:0 auto 0.55rem;box-shadow:0 4px 10px {color}44;">{icon}</div>
    <div style="font-size:0.62rem;font-weight:800;color:{color};text-transform:uppercase;
                letter-spacing:0.06em;margin-bottom:0.25rem;">{label}</div>
    <div style="font-size:{fs};font-weight:800;color:{dark};line-height:1.15;
                margin-bottom:0.2rem;">{val}</div>
    <div style="font-size:0.66rem;color:{color};font-weight:600;opacity:0.85;">{sub}</div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  LIVE EXAMPLE
# ═══════════════════════════════════════════════════════════

def _render_live_example(df_c):
    if df_c.empty:
        return

    sample = df_c.sample(1).iloc[0]

    _section_header(
        "🔍 Contoh Hasil Preprocessing per Tahap",
        "Contoh tweet acak dari dataset — refresh halaman untuk contoh berbeda"
    )

    # Urutan tampilan sesuai pipeline: CF → Clean → Norm → Token → Stop → Stem
    steps_ex = [
        ("📄 Teks Asli",            "text_asli",           "#0f172a", "#f8fafc",  "#e2e8f0", False),
        ("① Setelah Case Folding",  "setelah_casefolding", "#0c4a6e", "#eff6ff",  "#bfdbfe", False),
        ("② Setelah Cleaning",      "setelah_cleaning",    "#1e3a8a", "#eef2ff",  "#c7d2fe", False),
        ("③ Setelah Normalisasi",   "setelah_normalisasi", "#14532d", "#f0fdf4",  "#86efac", False),
        ("④ Setelah Tokenizing",    "setelah_tokenizing",  "#3b0764", "#f5f3ff",  "#c4b5fd", True),
        ("⑤ Setelah Stopword",     "setelah_stopword",    "#7c2d12", "#fff7ed",  "#fed7aa", False),
        ("⑥ Hasil Akhir (Stem)",   "clean_text",           "#713f12", "#fefce8",  "#fde68a", False),
    ]

    for label, col_key, text_color, bg, border, is_token in steps_ex:
        raw = sample.get(col_key, "-")
        text_display = str(raw) if raw and str(raw).strip() else "—"

        if is_token and text_display != "—":
            words = text_display.split(" | ")
            chips = "".join(
                f'<span class="token-chip">{w}</span>'
                for w in words if w.strip()
            )
            content_html = f'<div style="line-height:2;">{chips}</div>'
            char_info  = f"{len(words)} token"
        else:
            content_html = (
                f'<div style="font-size:0.82rem;color:{text_color};'
                f'line-height:1.65;word-break:break-word;">{text_display}</div>'
            )
            word_count = len(text_display.split()) if text_display != "—" else 0
            char_count = len(text_display) if text_display != "—" else 0
            char_info  = f"{word_count} kata · {char_count} karakter"

        st.markdown(
            f'<div class="example-box" style="background:{bg};border:1.5px solid {border};'
            f'border-radius:12px;padding:0.85rem 1.1rem;margin-bottom:0.55rem;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:0.4rem;">'
            f'<span style="font-size:0.68rem;font-weight:800;color:{text_color};'
            f'text-transform:uppercase;letter-spacing:0.07em;">{label}</span>'
            f'<span style="font-size:0.63rem;color:#94a3b8;font-weight:600;">{char_info}</span>'
            f'</div>'
            f'{content_html}'
            f'</div>',
            unsafe_allow_html=True
        )


# ═══════════════════════════════════════════════════════════
#  LENGTH COMPARISON CHART
# ═══════════════════════════════════════════════════════════

def _render_length_comparison_chart(df, df_c):
    _section_header(
        "📐 Perbandingan Panjang Teks per Tahap",
        "Rata-rata karakter per tweet di tiap tahap · Naik di normalisasi adalah normal (ekspansi singkatan)"
    )

    stages = [
        "Teks Asli", "① Case Folding", "② Cleaning",
        "③ Normalisasi", "④ Tokenizing", "⑤ Stopword", "⑥ Stemming"
    ]
    avgs = [
        df["text"].astype(str).str.len().mean(),
        df_c["setelah_casefolding"].astype(str).str.len().mean(),
        df_c["setelah_cleaning"].astype(str).str.len().mean(),
        df_c["setelah_normalisasi"].astype(str).str.len().mean(),
        df_c["setelah_tokenizing"].apply(
            lambda x: len(" ".join(str(x).split(" | ")))
        ).mean(),
        df_c["setelah_stopword"].astype(str).str.len().mean(),
        df_c["clean_text"].astype(str).str.len().mean(),
    ]
    avgs = [round(a, 1) for a in avgs]
    colors = ["#94a3b8", "#0284c7", "#3b6cf7", "#16a34a", "#7c3aed", "#ea580c", "#ca8a04"]

    fig = go.Figure(data=[
        go.Bar(
            x=stages, y=avgs,
            marker=dict(color=colors, line=dict(width=0), opacity=0.9, cornerradius=8),
            text=[f"{v}" for v in avgs],
            textposition="outside",
            textfont=dict(size=10, color="#475569"),
            width=0.55,
            hovertemplate="<b>%{x}</b><br>Rata-rata: %{y} karakter<extra></extra>",
        )
    ])
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=10, t=24, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickfont=dict(size=10, color="#64748b"),
                   showgrid=False, zeroline=False, showline=False, fixedrange=True),
        yaxis=dict(tickfont=dict(size=9, color="#94a3b8"),
                   showgrid=True, gridcolor="rgba(226,232,240,0.7)",
                   griddash="dot", gridwidth=1,
                   zeroline=False, showline=False, fixedrange=True),
        showlegend=False, hovermode="x unified",
    )

    st.markdown("""
<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1rem 1.2rem 0.5rem;box-shadow:0 2px 6px rgba(15,23,42,0.05);">
""", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  TOP WORDS CHART
# ═══════════════════════════════════════════════════════════

def _render_top_words_chart(df_c):
    _section_header(
        "📊 Kata-Kata Paling Sering Muncul",
        f"Dari {len(df_c):,} tweet yang sudah bersih (hasil akhir tahap 6) — Top 20 kata"
    )

    if "_tokens_clean" in df_c.columns:
        all_words = [w for tokens in df_c["_tokens_clean"] for w in (tokens if isinstance(tokens, list) else [])]
    else:
        all_words = " ".join(df_c["clean_text"].fillna("")).split()

    filtered_words = [w for w in all_words if len(w) > 2]
    word_freq = Counter(filtered_words).most_common(20)

    if not word_freq:
        st.info("⚠️ Belum cukup kata untuk ditampilkan.")
        return

    words  = [w[0] for w in word_freq]
    counts = [w[1] for w in word_freq]
    max_c  = max(counts) if counts else 1
    bar_colors = [f"rgba(59,108,247,{0.35 + 0.65*(c/max_c):.2f})" for c in counts[::-1]]

    fig = go.Figure(data=[
        go.Bar(
            y=words[::-1], x=counts[::-1], orientation="h",
            marker=dict(color=bar_colors, line=dict(width=0), cornerradius=6),
            text=[str(c) for c in counts[::-1]],
            textposition="outside",
            textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>Muncul %{x} kali<extra></extra>",
        )
    ])
    fig.update_layout(
        height=540,
        margin=dict(l=0, r=60, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="rgba(203,213,225,0.8)",
                   tickfont=dict(size=10, color="#94a3b8"),
                   zeroline=False, showline=False, fixedrange=True),
        yaxis=dict(showgrid=False, tickfont=dict(size=11, color="#334155"), fixedrange=True),
        showlegend=False,
    )

    st.markdown("""
<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1rem 1.2rem 0.5rem;box-shadow:0 2px 6px rgba(15,23,42,0.05);">
""", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
#  MAIN SHOW
# ═══════════════════════════════════════════════════════════

def show():
    _render_preprocessing_styles()
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
    mode_color, mode_icon = mode_meta.get(
        st.session_state.analysis_mode, ("#3b6cf7", "📊")
    )

    st.markdown(
        f'<div style="background:#fff;border-left:4px solid {mode_color};'
        f'border-top:1.5px solid #e2e8f0;border-right:1.5px solid #e2e8f0;'
        f'border-bottom:1.5px solid #e2e8f0;border-radius:0 12px 12px 0;'
        f'padding:0.875rem 1.25rem;margin-bottom:1.5rem;'
        f'box-shadow:0 2px 6px rgba(15,23,42,0.05);'
        f'display:flex;align-items:center;gap:0.75rem;">'
        f'<span style="font-size:1.375rem;">{mode_icon}</span>'
        f'<div>'
        f'<div style="font-size:0.875rem;font-weight:700;color:#0f172a;">{mode_display}</div>'
        f'<div style="font-size:0.78rem;color:#475569;margin-top:2px;">'
        f'Periode: <strong style="color:{mode_color};">{filter_label}</strong></div>'
        f'</div></div>',
        unsafe_allow_html=True
    )

    # ── Pipeline Overview ─────────────────────────────────────
    _section_header(
        "🔬 Alur NLP Pipeline — 6 Tahap Preprocessing",
        "Setiap tweet diproses berurutan melalui 6 tahap sebelum siap dianalisis sentimennya"
    )

    stemmer_tmp = _load_stemmer()
    _render_pipeline_steps(stemmer_tmp is not None)
    _gap("sm")
    _render_flow_arrow()
    _gap("md")

    # ── Load data ─────────────────────────────────────────────
    try:
        df_all = pd.read_sql("SELECT * FROM tweets ORDER BY created_at DESC", engine)
        if df_all.empty:
            st.warning("⚠️ Belum ada data. Kembali ke halaman Ambil Data Twitter.")
            return
        df_all["created_at"] = parse_dt(df_all["created_at"])
        if "crawled_at" in df_all.columns:
            df_all["crawled_at"] = parse_crawled_dt(df_all["crawled_at"])
    except Exception as e:
        st.error(f"❌ Gagal membaca database: {e}")
        return

    s_dt = pd.Timestamp(start_date)
    e_dt = pd.Timestamp(end_date)
    df   = df_all[(df_all["created_at"] >= s_dt) & (df_all["created_at"] <= e_dt)].copy()

    if df.empty:
        st.warning(f"⚠️ Tidak ada tweet dengan tanggal asli dalam periode {filter_label}.")
        return

    # ── Cache preprocessing ───────────────────────────────────
    total_tweets_in_db  = get_tweet_count()
    latest_crawl_marker = get_latest_crawl_time() or "no-crawl"
    data_marker         = (total_tweets_in_db, latest_crawl_marker)

    cache_key = (
        f"pp6_{st.session_state.analysis_mode}_"
        f"{start_date}_{end_date}_{total_tweets_in_db}_{latest_crawl_marker}"
    )

    for old_key in list(st.session_state.keys()):
        if old_key.startswith("pp6_") and old_key != cache_key:
            del st.session_state[old_key]

    force_refresh = data_marker != st.session_state.get("_pp_last_data_marker")

    if cache_key not in st.session_state or force_refresh:
        stemmer   = _load_stemmer()
        stopwords = _load_stopwords()

        with st.spinner("🧹 Menjalankan 6 tahap preprocessing…"):
            results = []
            for _, row in df.iterrows():
                r = full_preprocessing(row["text"], stopwords, stemmer)
                r["tweet_id"]   = row.get("tweet_id", "")
                r["text_asli"]  = row["text"]
                r["created_at"] = row["created_at"]
                r["crawled_at"] = row.get("crawled_at")
                results.append(r)

            df_c = pd.DataFrame(results)
            df_c = df_c[df_c["clean_text"].str.strip().str.len() > 0].copy()

            st.session_state[cache_key]                  = df_c
            st.session_state[cache_key + "_stemmer_ok"]  = stemmer is not None
            st.session_state["_pp_last_data_marker"]     = data_marker

    df_c       = st.session_state[cache_key]
    stemmer_ok = st.session_state.get(cache_key + "_stemmer_ok", False)

    # ── Statistik ─────────────────────────────────────────────
    avg_tok_before = df_c["setelah_tokenizing"].apply(
        lambda x: len(str(x).split(" | ")) if str(x).strip() else 0
    ).mean()
    avg_tok_after = df_c["clean_text"].apply(
        lambda x: len(str(x).split()) if str(x).strip() else 0
    ).mean()
    removed = len(df) - len(df_c)

    _section_header(
        "📌 Ringkasan Hasil Preprocessing",
        f"Berdasarkan tanggal asli tweet · {filter_label}"
    )
    _gap("xs")
    _render_stat_pills(len(df), len(df_c), avg_tok_before, avg_tok_after, removed)
    _gap("lg")

    _render_live_example(df_c)
    _gap("lg")

    # ── Tabel ─────────────────────────────────────────────────
    _section_header(
        "📋 Tabel Perbandingan Teks per Tahap",
        f"{len(df_c):,} tweet · {filter_label} — scroll horizontal untuk lihat semua kolom"
    )

    if "crawled_at" not in df_c.columns:
        df_c = df_c.copy()
        df_c["crawled_at"] = pd.NaT

    # Kolom ditampilkan sesuai urutan pipeline: CF → Clean → Norm → Token → Stop → Stem
    disp = df_c[[
        "tweet_id", "created_at", "crawled_at",
        "text_asli",
        "setelah_casefolding",
        "setelah_cleaning",
        "setelah_normalisasi",
        "setelah_tokenizing",
        "setelah_stopword",
        "clean_text",
    ]].copy()

    disp.columns = [
        "ID Tweet", "Tanggal Tweet", "Masuk Database",
        "Teks Asli",
        "① Case Folding",
        "② Cleaning",
        "③ Normalisasi",
        "④ Tokenizing",
        "⑤ Stopword",
        "⑥ Hasil Akhir",
    ]

    disp["Tanggal Tweet"]  = disp["Tanggal Tweet"].apply(format_dt)
    disp["Masuk Database"] = disp["Masuk Database"].apply(format_dt)

    render_standard_table(
        disp,
        height=360,
        min_width=2200,
        nowrap=["ID Tweet", "Tanggal Tweet", "Masuk Database"],
        wide_columns=[
            "Teks Asli", "① Case Folding", "② Cleaning",
            "③ Normalisasi", "④ Tokenizing", "⑤ Stopword", "⑥ Hasil Akhir",
        ],
        column_widths={
            "ID Tweet":         "155px",
            "Tanggal Tweet":    "165px",
            "Masuk Database":   "165px",
            "Teks Asli":        "280px",
            "① Case Folding":   "220px",
            "② Cleaning":       "240px",
            "③ Normalisasi":    "220px",
            "④ Tokenizing":     "240px",
            "⑤ Stopword":       "220px",
            "⑥ Hasil Akhir":    "220px",
        },
    )
    _gap("lg")

    _render_length_comparison_chart(df, df_c)
    _gap("lg")

    _render_top_words_chart(df_c)
    _gap("lg")

    # ── Simpan ke session state ───────────────────────────────
    st.session_state["preprocessed_df"] = df_c

    # ── Download ──────────────────────────────────────────────
    st.markdown("""
<div style="background:#ffffff;border:1.5px solid #e2e8f0;border-radius:14px;
            padding:1.1rem 1.2rem;box-shadow:0 2px 6px rgba(15,23,42,0.05);
            margin-bottom:1rem;">
""", unsafe_allow_html=True)

    d1, d2 = st.columns(2, gap="medium")

    with d1:
        st.download_button(
            "📥 Unduh Hasil Preprocessing Lengkap (semua kolom)",
            df_c.drop(columns=["_tokens_raw", "_tokens_clean"], errors="ignore"
                      ).to_csv(index=False).encode("utf-8"),
            f"preprocessing_lengkap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            use_container_width=True,
        )

    with d2:
        out2 = df_c[["tweet_id", "text_asli", "clean_text"]].copy()
        out2.columns = ["tweet_id", "tweet", "clean_text"]
        st.download_button(
            "📥 Unduh Teks Bersih Saja (siap analisis sentimen)",
            out2.to_csv(index=False).encode("utf-8"),
            f"teks_bersih_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv",
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
    _gap("sm")

    if st.button(
        "📈 Lanjut ke Analisis Sentimen →",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.current_page = "sentiment"
        st.rerun()

    _gap("sm")