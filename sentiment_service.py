"""
sentiment_service.py  —  Hybrid Classifier (versi perbaikan v2)
================================================================
PERBAIKAN UTAMA vs versi sebelumnya:

  MASALAH 1 — NORMALISASI MERUSAK KONTEKS SENTIMEN
    'mending' → 'lebih baik' (salah: di domain override)
    Akibat: "mending ngurusin judol daripada ngurusin ongkir"
            → "lebih baik ngurusin judol daripada..."
            → lexicon tangkap 'baik' = POSITIF (SEHARUSNYA NEGATIF)
    SOLUSI: Override 'mending' → 'mending' (biarkan apa adanya);
            hapus 'mendingan' → 'lebih baik' dari domain override.

  MASALAH 2 — LEXICON TERLALU LUAS (KATA KONTEKSTUAL)
    Kata-kata berikut dihapus dari LEXICON_POSITIF karena terlalu
    kontekstual — maknanya bergantung penuh pada kalimat sekitar:
      "baik"    → "lebih baik X daripada Y" bukan pujian
      "benar"   → "itu benar" bisa netral
      "penting" → "lebih penting" bukan pujian
      "wajar"   → "wajar aja" bisa netral
      "perlu"   → "perlu X" bukan pujian
      "tepat"   → bisa kontekstual
      "jelas"   → bisa kontekstual
      "fair"    → bisa kontekstual
      "manfaat" → bisa kontekstual
    SOLUSI: Hapus dari LEXICON_POSITIF, pindahkan ke list terpisah
            yang tidak ikut skor lexicon otomatis.

  MASALAH 3 — POLA KOMPARATIF TIDAK DIKENALI
    "mending X daripada Y", "lebih baik X daripada Y" = kritik implisit
    SOLUSI: Tambahkan deteksi POLA_KOMPARATIF_NEGATIF yang memberi
            skor negatif ketika pola ini ditemukan di teks.

  MASALAH 4 — POLA KRITIK TERSIRAT TIDAK DIKENALI
    "tidak penting", "gak usah", "ngapain", "begini aja" = kritik implisit
    SOLUSI: Tambahkan POLA_KRITIK_TERSIRAT yang memberi skor negatif
            ketika pola ini ditemukan.

  MASALAH 5 — "pembatasan gratis" DIHITUNG POSITIF
    "pembatasan gratis ongkir" → lexicon tangkap 'gratis' = POSITIF
    padahal konteksnya adalah keluhan/informasi negatif.
    SOLUSI: Jika 'gratis' didahului 'pembatasan' dalam window 3 kata,
            tidak dihitung sebagai sinyal positif.

  MASALAH 6 — TWEET INFORMATIF DIKLASIFIKASI POSITIF/NEGATIF
    "saya melihat berita mengenai pembatasan gratis ongkir" → NETRAL
    SOLUSI: Deteksi KATA_INFORMATIF; jika tweet hanya berisi konteks
            informatif tanpa kata sentimen eksplisit → dorong ke Netral.
"""

import re
import string
import joblib


# ═══════════════════════════════════════════════════════════
#  KATA SENTIMEN PENTING  (dijaga dari stopword removal)
# ═══════════════════════════════════════════════════════════

KATA_SENTIMEN_PENTING = {
    # Negasi
    "tidak", "bukan", "jangan", "kurang", "belum", "tanpa",
    # Intensitas
    "sangat", "banget", "sekali", "paling", "amat", "luar", "biasa",
    # Positif umum
    "keren", "bagus", "mantap", "setuju", "dukung", "mendukung",
    "andal", "handal", "gercep", "bangga", "senang", "suka",
    "baik", "benar", "tepat", "oke", "puas",
    "sejahtera", "berkembang", "maju", "inovatif",
    "tegas", "sigap", "tanggap", "adil", "bijak", "bermanfaat",
    "untung", "berhasil", "sukses", "solusi", "manfaat",
    "berguna", "membantu", "bantu", "pro", "lanjut",
    # Positif domain e-commerce/ongkir
    "gratis", "murah", "hemat", "terjangkau", "cepat",
    "aman", "mudah", "praktis", "terpercaya",
    # Negatif umum
    "kecewa", "mending", "malah", "buruk", "jelek", "parah",
    "gagal", "hancur", "rusak", "bohong", "tipu", "korupsi",
    # Negatif domain e-commerce/ongkir
    "mahal", "lambat", "lelet", "ribet", "susah", "repot",
    "rugi", "boros",
    # Emosi
    "marah", "sedih", "khawatir",
    
        # ── TAMBAHAN ────────────────────────────────────────────
'malas', 'males', 'enggan', 'bete', 'jengkel', 'depresi',
'gondok', 'dongkol', 'sebal', 'bosan', 'jenuh', 'heran', 'bingung', 'pusing', 'stress', 'panik',
'kapok', 'muak', 'frustrasi', 'menyesal', 'nyesel', 'mahal',
}


# ═══════════════════════════════════════════════════════════
#  LEXICON SENTIMEN  (DIPERBAIKI — kata kontekstual dihapus)
#
#  PRINSIP PEMILIHAN KATA LEXICON:
#  Kata masuk lexicon HANYA jika bisa berdiri sendiri sebagai
#  sinyal sentimen tanpa bergantung konteks kalimat di sekitarnya.
#
#  DIHAPUS dari versi lama karena terlalu kontekstual:
#    "baik", "benar", "penting", "tepat", "jelas", "transparan",
#    "amanah", "wajar", "fair", "perlu", "manfaat", "kompetitif"
# ═══════════════════════════════════════════════════════════

LEXICON_POSITIF = {
    'setuju', 'dukung', 'mendukung', 'pro', 'sepakat',
    'bagus', 'keren', 'mantap', 'mantep', 'bravo',
    'salut', 'apresiasi', 'hebat', 'oke',
    'bangga', 'senang', 'suka', 'puas', 'gembira', 'bahagia',
    'berhasil', 'sukses', 'berjaya',
    'andal', 'handal', 'gercep', 'bijak', 'bermanfaat',
    'berguna', 'membantu', 'inovatif',
    'berantas', 'melindungi', 'perlindungan',
    'untung', 'menguntungkan', 'solusi', 'memuaskan',
}

LEXICON_NEGATIF = {
    # Umpatan
    'tolol', 'bodoh', 'goblog', 'goblok', 'dungu', 'idiot',
    'bego', 'anjing', 'bangsat', 'bajingan', 'brengsek',
    'gila', 'edan', 'biadab',
    # Penilaian buruk
    'salah', 'keliru', 'gagal', 'buruk', 'jelek', 'parah', 'mahal',
    'payah', 'lemah', 'ngawur', 'kacau', 'hancur', 'berantakan', 'gajelas',
    # Ketidakjujuran
    'bohong', 'tipu', 'menipu', 'penipuan', 'curang',
    'manipulasi', 'korupsi', 'koruptor', 'maling', 'skandal',
    # EMOSI NEGATIF — ini yang sebelumnya tidak ada
    'kecewa', 'marah', 'kesal', 'jengkel', 'gondok',
    'dongkol', 'sebal', 'sebel', 'benci', 'muak',
    'frustrasi', 'khawatir', 'cemas', 'resah', 'takut',
    'sedih', 'menyesal', 'nyesel', 'sesal', 'kapok', 'trauma',
    'malas',      # ROOT CAUSE — wajib ada
    'males',      # slang malas
    'enggan', 'bete', 'bosan', 'jenuh',
    # Penolakan
    'menolak', 'tolak', 'protes', 'keberatan', 'kontra',
    # Dampak negatif
    'merugikan', 'rugikan', 'menyusahkan', 'membebani',
    'menghambat', 'mengecewakan', 'menyebalkan',
    # Sindiran
    'percuma', 'siasia', 'konyol', 'absurd', 'miris',
    'ironis', 'memalukan', 'memprihatinkan',
    # Masalah
    'masalah', 'bermasalah', 'ricuh', 'kacau', 'ribet',
    'susah', 'sulit', 'rumit',
    # Domain Komdigi
    'judol', 'pinjol', 'ngurusin', 'ngurusi', 'urusin',
    'sibuk', 'melempem',
    # Seruan negatif
    'ckckck', 'astaga',
    # Lain
    'blokir', 'hambat', 'diskriminasi', 'zalim', 'bocor',
}

KATA_NEGASI = {
    "tidak", "bukan", "jangan", "belum", "tanpa", "kurang",
    "anti", "non", "tak", "ga", "gak", "nggak", "ngga",
    "enggak", "engga",
}


# ═══════════════════════════════════════════════════════════
#  POLA KONTEKSTUAL  (BARU — deteksi kritik implisit)
#
#  Pola-pola ini mendeteksi sentimen dari struktur kalimat,
#  bukan hanya dari kata individual. Sangat penting untuk
#  tweet berbahasa informal Indonesia.
# ═══════════════════════════════════════════════════════════

# Pola komparatif yang menandakan kritik/saran negatif tersirat
# Format: (regex_pattern, skor_negatif_tambahan)
POLA_KOMPARATIF_NEGATIF = [
    # "mending X daripada Y" — membandingkan, menyiratkan Y tidak layak
    (r"\bmending\b.{1,80}\bdaripada\b",     2),
    # "lebih baik X daripada Y" — sama dengan di atas
    (r"\blebih baik\b.{1,80}\bdaripada\b",  1),
    # "daripada X, mending Y" — variasi urutan
    (r"\bdaripada\b.{1,50}\bmending\b",     1),
    # "ketimbang urus ongkir, mending urus judol"
    (r"\bketimbang\b.{1,60}\b(kebijakan|urus|ngurusin)\b", 1),
]

# Pola kritik tersirat — frasa yang menyiratkan ketidaksetujuan
# meskipun tidak ada kata negatif eksplisit
POLA_KRITIK_TERSIRAT = [
    # "tidak penting / gak penting" — dismissif
    (r"\b(tidak|tak|gak|ga|ngga|nggak)\b.{0,15}\bpenting\b",  1),
    
    (r"\b(tidak|tak|gak|ga|ngga|nggak)\b.{0,15}\bjelas\b",  1),
    
    (r"\b(tidak|tak|gak|ga|ngga|nggak)\b.{0,15}\bbecus\b",  1),
    
    
    # "ngapain / buat apa / untuk apa" + konteks kebijakan
    (r"\b(ngapain|buat apa|untuk apa|ngapain)\b.{1,50}\b(kebijakan|ongkir|aturan|regulasi)\b", 2),
    # "gak usah / tidak usah / gak perlu"
    (r"\b(gak|ga|tidak|tak|ngga)\b\s*(usah|perlu)\b",          1),
    # "percuma / sia-sia / buang-buang"
    (r"\b(percuma|sia-sia|buang-buang)\b",                      2),
    
    (r"\b(nyusahin|ribet|maksain|susah-susahin)\b",                      2),
    
    # "mending urusin yang lain / yang lebih penting"
    (r"\bmending\b.{1,30}\b(urusin|urus)\b",                    1),
    # "kebijakan begini / aturan begini" — menyiratkan tidak setuju
    (r"\b(kebijakan|aturan|regulasi)\b.{0,20}\bbegini\b",       1),
    # "apa gunanya / apa manfaatnya" — retorikal negatif
    (r"\bapa\b.{0,10}\b(guna|manfaat|untung)\b.{0,10}(nya|sih|ini)\b", 1),
]

# Kata informatif — menunjukkan tweet berisi pelaporan/informasi netral
KATA_INFORMATIF = {
    "berita", "melihat", "membaca", "mendengar", "mengetahui",
    "laporan", "informasi", "kabar", "melaporkan", "dikabarkan",
    "menurut", "dilaporkan", "diberitakan", "dikutip", "mengutip",
}


# ═══════════════════════════════════════════════════════════
#  LOAD NORMALISASI DARI FILE
#  PERUBAHAN: Hapus override 'mending' → 'lebih baik' karena
#  mengubah kata kritis negatif menjadi sinyal positif.
# ═══════════════════════════════════════════════════════════

def _load_normalization() -> dict:
    """
    Muat kamus normalisasi dari file eksternal.

    PERBAIKAN di versi ini:
    - 'mending' dan 'mendingan' TIDAK lagi dioverride ke 'lebih baik'
      karena mengakibatkan kata negatif/kritis menjadi sinyal positif
      di lexicon scoring. Kata ini dibiarkan apa adanya agar POLA_KOMPARATIF
      dan POLA_KRITIK dapat mendeteksinya.
    - Override 'malah' dihapus — file normalisasi umum mengubah
      'malah' → 'bahkan' yang bisa mengubah konteks sentimen.
    """
    norm_file = "indonesian-normalisasi-slangword-complete.txt"
    norm_dict: dict = {}
    try:
        with open(norm_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) != 2:
                    continue
                slang  = parts[0].strip().strip("'\"").lower()
                normal = parts[1].strip().lower()
                if slang and normal:
                    norm_dict[slang] = normal
    except FileNotFoundError:
        pass

    # ── Override khusus domain ───────────────────────────────────────────────
    # Entri ini menimpa file generik. Perhatikan komentar DIHAPUS di bawah.
    DOMAIN_OVERRIDES: dict = {
        # Nama platform — pertahankan apa adanya
        "shopee":       "shopee",
        "tokopedia":    "tokopedia",
        "lazada":       "lazada",
        "tiktok":       "tiktok",
        "bukalapak":    "bukalapak",
        "blibli":       "blibli",
        # Logistik
        "sicepat":      "sicepat",
        "jne":          "jne",
        "jnt":          "jnt",
        "anteraja":     "anteraja",
        "ninja":        "ninja",
        # Ongkir & belanja
        "freeongkir":   "gratis ongkos kirim",
        "gratisongkir": "gratis ongkos kirim",
        "ongkir":       "ongkos kirim",
        "ongkr":        "ongkos kirim",
        "bykrm":        "biaya kirim",
        "biayakirim":   "biaya pengiriman",
        # Kebijakan & lembaga
        "komdigi":      "komdigi",
        "kemendag":     "kementerian perdagangan",
        "kominfo":      "kementerian komunikasi",
        # E-commerce umum
        "ecommerce":    "e commerce",
        "marketplace":  "marketplace",
        "seller":       "penjual",
        "buyer":        "pembeli",
        "online":       "online",
        # Negasi informal — pastikan ditangkap
        "gk":     "tidak", "ga":     "tidak", "gak":    "tidak",
        "nggak":  "tidak", "ngga":   "tidak", "tdk":    "tidak",
        "tak":    "tidak", "enggak": "tidak", "engga":  "tidak",
        "kagak":  "tidak", "kaga":   "tidak", "ndak":   "tidak",
        "ngak":   "tidak",
        # Intensitas
        "bgt": "banget", "bngt": "banget", "bget": "banget", "bgtt": "banget",
        # Positif informal — hanya yang benar-benar positif
        "mantep":  "mantap", "mntap": "mantap",
        "kece":    "keren",
        "ancur":   "hancur", "parahh": "parah",
        # ── SENGAJA TIDAK DIOVERRIDE (vs versi lama): ────────────────────────
        # "mending"   → TIDAK diubah ke "lebih baik"
        #   Alasan: "mending X daripada Y" adalah ekspresi kritik.
        #   Mengubah ke "lebih baik" membuat lexicon menangkap 'baik' = POSITIF,
        #   padahal kalimatnya bermakna negatif/kritik. Biarkan "mending" apa
        #   adanya agar POLA_KOMPARATIF_NEGATIF bisa mendeteksinya.
        #
        # "mendingan" → TIDAK diubah ke "lebih baik" (alasan sama)
        #
        # "malah"     → TIDAK dioverride. File normalisasi mengubah 'mlah'→'malah'
        #   yang sudah benar; 'malah' sendiri tidak perlu diubah ke 'bahkan'
        #   karena mengubah nuansa kritis.
        #
        # "sip"       → TIDAK dioverride ke "baik". "sip" cukup dikenal dan
        #   berdiri sendiri sebagai apresiasi. "baik" sudah dihapus dari
        #   lexicon karena terlalu kontekstual.
    }
    norm_dict.update(DOMAIN_OVERRIDES)
    return norm_dict


# ═══════════════════════════════════════════════════════════
#  LOAD STOPWORDS DARI FILE
# ═══════════════════════════════════════════════════════════

def _load_stopwords() -> set:
    """
    Muat daftar stopword dari file eksternal.

    PERBAIKAN di versi ini:
    - Pertahankan 'mending' dari stopword removal. Kata ini penting
      sebagai penanda POLA_KOMPARATIF_NEGATIF dan POLA_KRITIK_TERSIRAT.
    - Pertahankan 'daripada' dari stopword removal. Kata ini adalah
      komponen kunci pola "mending X daripada Y".
    """
    stopword_file = "indonesian-stopwords-complete.txt"
    base: set = set()
    try:
        with open(stopword_file, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word:
                    base.add(word)
    except FileNotFoundError:
        base = {
            "yang", "dan", "di", "ke", "dari", "ini", "itu",
            "dengan", "untuk", "pada", "adalah", "oleh", "ada",
            "ya", "akan", "atau", "juga", "sama", "karena",
            "jika", "sudah", "telah", "jadi", "bisa",
        }

    # ── Lindungi kata sentimen penting ──────────────────────────────────────
    for kata in KATA_SENTIMEN_PENTING:
        base.discard(kata)

    # ── Lindungi kata penanda pola kontekstual ──────────────────────────────
    # Kata-kata ini diperlukan agar POLA_KOMPARATIF dan POLA_KRITIK bisa
    # mendeteksi struktur kalimat dengan benar di teks yang sudah bersih.
    KATA_POLA_PENTING: set = {
        "mending",    # penanda pola komparatif negatif
        "mendingan",  # variasi mending
        "daripada",   # komponen "mending X daripada Y"
        "ketimbang",  # variasi daripada
        "ngapain",    # penanda kritik tersirat
        "percuma",    # penanda sia-sia
        "begini",     # "kebijakan begini" = kritik tersirat
        "gajelas",    # "gajelas aja kebijakan ini" = tidak jelas/negatif   
        "mahal",      # "mahal banget kebijakan ini" = negatif
        "nyusahin",  # penanda ribet/susah-susahin
        "malas",      # "malas banget urus kebijakan ini" = negatif
    }
    for kata in KATA_POLA_PENTING:
        base.discard(kata)

    # ── Tambah noise Twitter/sosmed ─────────────────────────────────────────
    base.update({
        "rt", "amp", "https", "http", "co", "pic",
        "wkwk", "wkwkwk", "wkwkwkwk",
        "haha", "hahaha", "hehe", "hihi", "huhu", "xixi",
        "nih", "sih", "dong", "deh", "loh", "lah", "tuh",
        "kak", "gan", "bro", "sob", "min",
    })
    return base


# ═══════════════════════════════════════════════════════════
#  LOAD STEMMER
# ═══════════════════════════════════════════════════════════

def _load_stemmer():
    try:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        return StemmerFactory().create_stemmer()
    except Exception:
        return None


# ── Inisialisasi global ──────────────────────────────────────────────────────
_STOPWORDS = _load_stopwords()
_STEMMER   = _load_stemmer()
_NORM_DICT = _load_normalization()


# ═══════════════════════════════════════════════════════════
#  MODEL LOADING (lazy, singleton)
# ═══════════════════════════════════════════════════════════

_model = None
_tfidf = None


def _load_model():
    global _model, _tfidf
    if _model is None:
        try:
            _model = joblib.load("model_naive_bayes.pkl")
        except Exception as e:
            print(f"[WARNING] Gagal load model_naive_bayes.pkl: {e}")
    if _tfidf is None:
        try:
            _tfidf = joblib.load("tfidf_vectorizer.pkl")
        except Exception as e:
            print(f"[WARNING] Gagal load tfidf_vectorizer.pkl: {e}")
    return _model, _tfidf


# ═══════════════════════════════════════════════════════════
#  5-TAHAP PREPROCESSING PIPELINE
#  IDENTIK dengan preprocessing_page.py
# ═══════════════════════════════════════════════════════════

def _step1_case_folding(text: str) -> str:
    return str(text).lower()


def _step2_cleaning(text: str) -> str:
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\d+", "", text)
    text = re.sub(
        r"["
        r"\U00010000-\U0010ffff"
        r"\U0001F600-\U0001F64F"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF"
        r"\u2600-\u26FF"
        r"\u2700-\u27BF"
        r"]+",
        "", text, flags=re.UNICODE,
    )
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _step3_normalization(text: str, norm_dict: dict) -> str:
    tokens = text.split()
    return " ".join(norm_dict.get(token, token) for token in tokens)


def _step4_stopword_removal(tokens: list, stopwords: set) -> list:
    result = []
    for token in tokens:
        if token in KATA_SENTIMEN_PENTING:
            result.append(token)
            continue
        if token in stopwords:
            continue
        if len(token) <= 2:
            continue
        result.append(token)
    return result


def _step5_stemming(tokens: list, stemmer) -> list:
    if stemmer is None:
        return tokens
    return [stemmer.stem(token) for token in tokens]


def preprocess_for_model(text: str) -> str:
    """Full 5-tahap preprocessing → string teks bersih siap TF-IDF."""
    s1 = _step1_case_folding(text)
    s2 = _step2_cleaning(s1)
    s3 = _step3_normalization(s2, _NORM_DICT)
    s4 = _step4_stopword_removal(s3.split(), _STOPWORDS)
    s5 = _step5_stemming(s4, _STEMMER)
    return " ".join(s5)


def preprocess_untuk_lexicon(text: str) -> str:
    """
    Preprocessing untuk lexicon matching.
    PENTING: TIDAK distem dan TIDAK dihapus stopword-nya agar
    pola kontekstual (mending, daripada, begini, dll.) tetap ada
    dan bisa dideteksi oleh POLA_KOMPARATIF dan POLA_KRITIK.
    """
    s1 = _step1_case_folding(text)
    s2 = _step2_cleaning(s1)
    s3 = _step3_normalization(s2, _NORM_DICT)
    return s3  # Kembalikan setelah normalisasi saja — stopword & stem TIDAK dilakukan


# ═══════════════════════════════════════════════════════════
#  LEXICON SCORER  (DIPERBAIKI — pola kontekstual + pembatasan)
# ═══════════════════════════════════════════════════════════

def _hitung_skor_lexicon(teks_lexicon: str) -> dict:
    """
    Hitung skor sentimen via lexicon + pola kontekstual + negation handling.

    PERUBAHAN UTAMA vs versi lama:
    ─────────────────────────────────────────────────────────────────────
    1. POLA_KOMPARATIF_NEGATIF: "mending X daripada Y" → tambah skor negatif
    2. POLA_KRITIK_TERSIRAT: "tidak penting", "gak usah", dll. → skor negatif
    3. POLA 'pembatasan gratis': 'gratis' tidak dihitung positif jika
       didahului 'pembatasan' dalam window 3 kata
    4. DETEKSI TWEET INFORMATIF: jika teks hanya berisi konteks informasi
       tanpa kata sentimen eksplisit, tandai sebagai 'informatif'
    5. Window negasi tetap 3 kata (dari versi sebelumnya)
    ─────────────────────────────────────────────────────────────────────
    Return: {"positif": int, "negatif": int, "net": int, "informatif": bool}
    """
    tokens   = teks_lexicon.split()
    skor_pos = 0
    skor_neg = 0

    # ── Tahap 1: Deteksi pola komparatif ──────────────────────────────────
    for pola, bobot in POLA_KOMPARATIF_NEGATIF:
        if re.search(pola, teks_lexicon):
            skor_neg += bobot

    # ── Tahap 2: Deteksi pola kritik tersirat ─────────────────────────────
    for pola, bobot in POLA_KRITIK_TERSIRAT:
        if re.search(pola, teks_lexicon):
            skor_neg += bobot

    # ── Tahap 3: Lexicon per token ────────────────────────────────────────
    for i, token in enumerate(tokens):
        # Negation window: 3 kata sebelumnya
        ada_negasi = any(
            tokens[i - j] in KATA_NEGASI
            for j in range(1, 4)
            if i - j >= 0
        )
        # Konteks pembatasan: 'gratis' setelah 'pembatasan' tidak = positif
        ada_pembatasan = any(
            tokens[i - j] == "pembatasan"
            for j in range(1, 4)
            if i - j >= 0
        )

        if token in LEXICON_POSITIF:
            if ada_negasi:
                skor_neg += 1
            elif ada_pembatasan and token == "gratis":
                # "pembatasan gratis ongkir" = konteks negatif/netral,
                # bukan pujian terhadap 'gratis'. Lewati.
                pass
            else:
                skor_pos += 1

        elif token in LEXICON_NEGATIF:
            if ada_negasi:
                skor_pos += 1
            else:
                skor_neg += 1

    # ── Tahap 4: Deteksi tweet informatif ────────────────────────────────
    # Tweet informatif: mengandung kata pelaporan, TIDAK ada kata sentimen
    # eksplisit, dan panjang teks tidak terlalu pendek.
    token_set = set(tokens)
    ada_info_kata = bool(token_set & KATA_INFORMATIF)
    ada_sentimen_eksplisit = bool(
        (token_set & LEXICON_POSITIF) | (token_set & LEXICON_NEGATIF)
    )
    # Informatif jika: ada kata informatif + tidak ada sentimen eksplisit
    # + skor negatif dari pola kecil (≤1, artinya cuma 'pembatasan')
    is_informatif = (
        ada_info_kata
        and not ada_sentimen_eksplisit
        and skor_neg <= 1
    )

    return {
        "positif":    skor_pos,   # ← wajib ada
        "negatif":    skor_neg,   # ← wajib ada
        "net":        skor_pos - skor_neg,
        "informatif": is_informatif,
    }


# ═══════════════════════════════════════════════════════════
#  PREDIKSI MODEL NB
# ═══════════════════════════════════════════════════════════

_LABEL_MAP = {
    "positif": "Positif", "Positif": "Positif",
    "positive": "Positif", "pos": "Positif",
    "negatif": "Negatif", "Negatif": "Negatif",
    "negative": "Negatif", "neg": "Negatif",
    "netral":  "Netral",  "Netral":  "Netral",
    "neutral": "Netral",  "net": "Netral",
}


def _prediksi_model(teks_model: str):
    """
    Prediksi dari model NB 3-kelas.
    Return: (label_norm, confidence, proba_dict) atau None jika gagal.
    """
    model, tfidf = _load_model()
    if model is None or tfidf is None or not teks_model.strip():
        return None
    try:
        vec        = tfidf.transform([teks_model])
        pred_raw   = model.predict(vec)[0]
        proba      = model.predict_proba(vec)[0]
        classes    = list(model.classes_)

        label_norm = _LABEL_MAP.get(str(pred_raw), "Netral")
        pred_idx   = classes.index(pred_raw) if pred_raw in classes else 0
        confidence = float(proba[pred_idx])

        proba_dict = {
            _LABEL_MAP.get(str(cls), str(cls)): float(p)
            for cls, p in zip(classes, proba)
        }
        return label_norm, confidence, proba_dict
    except Exception as e:
        print(f"[WARNING] Prediksi model gagal: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  HYBRID CLASSIFIER  (DIPERBAIKI)
# ═══════════════════════════════════════════════════════════

def _klasifikasi_hybrid(
    teks_model: str,
    skor: dict,
    teks_lower: str,
) -> tuple:
    """
    Klasifikasi hybrid: sinyal lexicon + pola kontekstual + model NB.

    ALUR KEPUTUSAN:
    ─────────────────────────────────────────────────────────────────────
    Layer 0 — Override Informatif:
      Jika skor['informatif'] = True DAN net mendekati 0 → Netral langsung.
      Mencegah tweet berita/informatif terklasifikasi positif/negatif
      karena kata domain (mis. 'gratis' dalam "berita mengenai gratis ongkir").

    Layer 1a — Override Positif KUAT (net >= 2):
      Sinyal lexicon + pola sangat kuat → Positif langsung.

    Layer 1b — Override Negatif KUAT (net <= -2):
      Sinyal lexicon + pola sangat kuat → Negatif langsung.
      CATATAN: Pola komparatif "mending X daripada Y" menambah net -2/-3
      sehingga tweet kritik implisit langsung terdeteksi di sini.

    Layer 2a — Override Positif LEMAH (net == 1):
      Konsultasi model. Jika model tidak sangat yakin Negatif → Positif.

    Layer 2b — Override Negatif LEMAH (net == -1):
      Konsultasi model. Jika model tidak sangat yakin Positif → Negatif.

    Layer 3 — Fallback Model NB:
      Anti-bias:
      - Model Negatif + lexicon bersih (net >= 0) + conf < 0.65 → Netral
      - Model Positif + lexicon negatif (net <= -1) + conf < 0.65 → Netral

    Layer 4 — Ultimate Fallback (model tidak tersedia):
      Gunakan sinyal lexicon saja.
    ─────────────────────────────────────────────────────────────────────
    Return: (label: str, confidence: float)
    """
    net        = skor["net"]
    skor_pos = skor["positif"]   # ← pastikan dict ini return nilai ini
    skor_neg = skor["negatif"]   # ← pastikan dict ini return nilai ini
    is_info    = skor.get("informatif", False)

    # ── TAMBAHAN Layer 0b: Override dominasi kata ─────────
    # Jika salah satu sisi punya ≥2 kata lebih banyak dari sisi lain,
    # langsung putuskan tanpa menunggu model NB.
    if skor_neg >= 2 and skor_neg > skor_pos:
        conf = min(0.60 + (skor_neg - skor_pos) * 0.05, 0.90)
        return ("Negatif", round(conf, 3))
    
        if skor_pos >= 2 and skor_pos > skor_neg:
            conf = min(0.60 + (skor_pos - skor_neg) * 0.05, 0.90)
        return ("Positif", round(conf, 3))

    # ── Layer 1a: Positif KUAT ────────────────────────────────────────────
    if net >= 2:
        conf = min(0.65 + (net * 0.05), 0.92)
        return ("Positif", round(conf, 3))

    # ── Layer 1b: Negatif KUAT ────────────────────────────────────────────
    # Pola komparatif ("mending X daripada Y") memberi net -2 hingga -4,
    # sehingga tweet kritik implisit langsung tertangkap di layer ini.
    if net <= -2:
        conf = min(0.65 + (abs(net) * 0.05), 0.92)
        return ("Negatif", round(conf, 3))

    # ── Layer 2a: Positif LEMAH ───────────────────────────────────────────
    if net == 1:
        model_result = _prediksi_model(teks_model)
        if model_result is not None:
            _, _, proba_dict = model_result
            neg_prob = proba_dict.get("Negatif", 0.0)
            if neg_prob < 0.70:
                conf = round(0.55 + (0.70 - neg_prob) * 0.30, 3)
                return ("Positif", min(conf, 0.82))
            else:
                return ("Positif", 0.55)
        return ("Positif", 0.58)

    # ── Layer 2b: Negatif LEMAH ───────────────────────────────────────────
    if net == -1:
        model_result = _prediksi_model(teks_model)
        if model_result is not None:
            _, _, proba_dict = model_result
            pos_prob = proba_dict.get("Positif", 0.0)
            if pos_prob < 0.70:
                conf = round(0.55 + (0.70 - pos_prob) * 0.30, 3)
                return ("Negatif", min(conf, 0.82))
            else:
                return ("Negatif", 0.55)
        return ("Negatif", 0.58)

    # ── Layer 3: Fallback Model NB ────────────────────────────────────────
    model_result = _prediksi_model(teks_model)
    if model_result is not None:
        label_norm, confidence, proba_dict = model_result

        # Anti-bias 1: Model Negatif tapi lexicon bersih → Netral
        if label_norm == "Negatif" and net >= 0 and confidence < 0.65:
            corrected_conf = round(0.50 + max(0, confidence - 0.50) * 0.20, 3)
            return ("Netral", corrected_conf)

        # Anti-bias 2: Model Positif tapi lexicon negatif → Netral
        if label_norm == "Positif" and net <= -1 and confidence < 0.65:
            corrected_conf = round(0.50 + max(0, confidence - 0.50) * 0.20, 3)
            return ("Netral", corrected_conf)

        return (label_norm, round(confidence, 3))

    # ── Layer 4: Ultimate Fallback ────────────────────────────────────────
    if net > 0:
        return ("Positif", 0.55)
    elif net < 0:
        return ("Negatif", 0.55)
    else:
        return ("Netral", 0.50)


# ═══════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════

def analisis_sentimen_single(text: str) -> tuple:
    """
    Analisis sentimen satu teks.
    Return: (label, confidence)
      label: 'Positif' | 'Netral' | 'Negatif'
    """
    teks_model   = preprocess_for_model(text)
    teks_lexicon = preprocess_untuk_lexicon(text)
    teks_lower   = str(text).lower()
    skor         = _hitung_skor_lexicon(teks_lexicon)
    return _klasifikasi_hybrid(teks_model, skor, teks_lower)


def analisis_sentimen_batch(texts: list) -> list:
    """
    Analisis sentimen batch.
    Return: list of (label, confidence)
    """
    return [analisis_sentimen_single(text) for text in texts]


# ═══════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY
# ═══════════════════════════════════════════════════════════

def bersihkan_teks(text: str) -> str:
    """[LEGACY] Gunakan preprocess_for_model()."""
    return preprocess_for_model(text)


def prediksi_sentimen(list_text: list):
    """
    [LEGACY] Prediksi batch.
    Return: (list clean_texts, list labels)
    """
    clean_texts = [preprocess_for_model(t) for t in list_text]
    labels = [analisis_sentimen_single(t)[0] for t in list_text]
    return clean_texts, labels