"""
sentiment_service.py
====================
Hybrid Classifier untuk analisis sentimen tweet Bahasa Indonesia.

PIPELINE PREPROCESSING — 6 TAHAP (selaras dengan preprocessing_page.py):
  1. Case Folding     → lowercase dulu sebelum cleaning
  2. Cleaning         → hapus URL, mention, hashtag, angka, emoji, tanda baca
  3. Normalisasi      → singkatan/slang → kata baku
  4. Tokenizing       → split menjadi list token
  5. Stopword Removal → buang kata umum, jaga kata sentimen penting
  6. Stemming         → bentuk dasar via Sastrawi ECS

ARSITEKTUR HYBRID:
  Teks Asli
    ├── preprocess_untuk_lexicon() ──→ _hitung_skor_lexicon() ──┐
    └── preprocess_for_model()     ──→ TF-IDF → NB Model ───────┘
                                                                  ↓
                                              _klasifikasi_hybrid() → Label + Confidence
"""

import re
import string
import joblib


# ═══════════════════════════════════════════════════════════
#  KATA SENTIMEN PENTING
#  Tidak boleh dihapus di tahap stopword removal
# ═══════════════════════════════════════════════════════════

KATA_SENTIMEN_PENTING = {
    # ── Negasi ──────────────────────────────────────────────
    "tidak", "bukan", "jangan", "kurang", "belum", "tanpa",

    # ── Sentimen POSITIF ────────────────────────────────────
    "keren", "bagus", "mantap", "setuju", "dukung", "mendukung",
    "andal", "handal", "gercep", "bangga", "senang", "suka",
    "baik", "benar", "tepat", "oke",
    "sejahtera", "berkembang", "maju", "inovatif",
    "tegas", "sigap", "tanggap", "adil", "bijak", "bermanfaat",
    "untung", "berhasil", "sukses", "solusi", "manfaat",
    "berguna", "membantu", "bantu", "pro", "lanjut",
    "sangat", "banget", "sekali", "paling", "amat", "luar", "biasa",

    # ── Sentimen NEGATIF evaluatif ──────────────────────────
    "kecewa", "buruk", "jelek", "parah", "gagal", "hancur",
    "rusak", "bohong", "tipu", "korupsi",

    # ── Emosi ───────────────────────────────────────────────
    "marah", "sedih", "khawatir",
}


# ═══════════════════════════════════════════════════════════
#  NORMALISASI (selaras dengan preprocessing_page.py)
# ═══════════════════════════════════════════════════════════

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
    # Intensitas
    "bgt": "banget", "bngt": "banget", "bget": "banget", "bgtt": "banget",
    # Positif informal
    "bener": "benar", "beneran": "benar",
    "mantep": "mantap", "mntap": "mantap",
    "kece": "keren",
    "cucok": "cocok", "cucuk": "cocok",
    "cakep": "bagus",
    "sip": "baik", "siipp": "baik",
    "top": "terbaik",
    "jos": "bagus", "josss": "bagus",
    "goks": "luar biasa",
    "setujuu": "setuju", "stuju": "setuju",
    "proud": "bangga",
    "mantul": "mantap betul",
    # Negatif informal
    "ancur": "hancur", "ancrr": "hancur",
    "parahh": "parah", "parahhh": "parah",
    "gagall": "gagal",
    "ngaco": "tidak benar",
    "ngasal": "tidak benar",
    "gaje": "tidak jelas",
    # Domain
    "ongkir": "ongkos kirim",
    "freeongkir": "gratis ongkos kirim",
    "gratisongkir": "gratis ongkos kirim",
    "free": "gratis",
    "ecommerce": "e commerce",
    "seller": "penjual",
    "buyer": "pembeli",
}


# ═══════════════════════════════════════════════════════════
#  LEXICON SENTIMEN
# ═══════════════════════════════════════════════════════════

LEXICON_POSITIF = {
    "bagus", "baik", "keren", "mantap", "mantep", "hebat",
    "oke", "sip", "top", "jos", "goks", "kece", "mantul",
    "setuju", "dukung", "mendukung", "pro", "lanjut", "sepakat",
    "bangga", "senang", "suka", "puas", "gembira", "bahagia",
    "berhasil", "sukses", "berjaya", "prestasi", "pencapaian",
    "andal", "handal", "gercep", "sigap", "tanggap", "tegas",
    "adil", "bijak", "bermanfaat", "berguna", "membantu",
    "inovatif", "maju", "berkembang", "sejahtera",
    "benar", "tepat", "jelas", "transparan", "amanah", "terpercaya",
    "untung", "gratis", "murah", "hemat", "terjangkau",
    "terbaik", "luar biasa",
    "cakep", "cucok", "gaskeun", "kuy",
    "dukung", "bantu", "solusi", "manfaat",
    "memuaskan", "membanggakan", "mengagumkan",
}

LEXICON_NEGATIF = {
    "buruk", "jelek", "parah", "rusak", "hancur", "ancur",
    "gagal", "gagall", "ambruk", "terpuruk", "bangkrut",
    "bohong", "tipu", "curang", "manipulasi", "korupsi", "penipuan",
    "kebohongan",
    "kecewa", "marah", "sedih", "khawatir", "takut", "benci",
    "jijik", "muak", "kesal", "frustrasi",
    "mahal", "rugi", "merugikan",
    "lambat", "lemot", "ribet", "susah", "sulit", "bermasalah",
    "ngaco", "ngasal", "gaje", "receh",
    "tidak benar", "tidak jelas", "tidak adil", "tidak berguna",
    "mengecewakan", "menyebalkan", "menyusahkan",
}

KATA_NEGASI = {
    "tidak", "bukan", "jangan", "belum", "tanpa", "kurang",
    "anti", "non",
}


# ═══════════════════════════════════════════════════════════
#  STOPWORDS
# ═══════════════════════════════════════════════════════════

def _load_stopwords() -> set:
    """Load stopword dengan penjagaan kata sentimen penting."""
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
            "jika", "sudah", "telah", "saat", "agar", "maka",
            "lagi", "bila", "bisa", "pun", "nya",
        }

    # Jangan hapus kata sentimen penting
    for kata in KATA_SENTIMEN_PENTING:
        base.discard(kata)

    # Tambahan stopword domain-spesifik
    base.update({
        "rt", "amp", "https", "http", "co", "t",
        "wkwk", "wkwkwk", "haha", "hehe", "xixi", "hahaha",
        "yg", "dgn", "utk", "dr", "krn", "tp", "jd", "sdh",
        "aja", "doang", "nih", "sih", "dong", "deh",
        "loh", "lah", "tuh", "kak", "gan", "bro", "sis",
    })
    return base


# ═══════════════════════════════════════════════════════════
#  STEMMER
# ═══════════════════════════════════════════════════════════

def _load_stemmer():
    """Load Sastrawi stemmer. Return None jika tidak terinstall."""
    try:
        from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
        return StemmerFactory().create_stemmer()
    except Exception:
        return None


# ── Inisialisasi global ─────────────────────────────────────────────────────
_STOPWORDS = _load_stopwords()
_STEMMER   = _load_stemmer()


# ═══════════════════════════════════════════════════════════
#  MODEL LOADING (lazy)
# ═══════════════════════════════════════════════════════════

_model = None
_tfidf = None


def _load_model():
    """
    Lazy load NB model + TF-IDF vectorizer.
    Return: (model, tfidf) — keduanya bisa None.
    """
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
#  PREPROCESSING PIPELINE — 6 TAHAP
#
#  URUTAN (selaras dengan preprocessing_page.py):
#    1. Case Folding     → lowercase
#    2. Cleaning         → hapus noise
#    3. Normalisasi      → normalisasi kata
#    4. Tokenizing       → split token
#    5. Stopword Removal → buang stopword
#    6. Stemming         → bentuk dasar
# ═══════════════════════════════════════════════════════════

def _case_folding(text: str) -> str:
    """Tahap 1: Lowercase seluruh teks."""
    return str(text).lower()


def _cleaning(text: str) -> str:
    """Tahap 2: Hapus noise (URL, mention, hashtag, angka, emoji, tanda baca)."""
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
        r"]+", "", text, flags=re.UNICODE,
    )
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalisasi(text: str) -> str:
    """Tahap 3: Normalisasi singkatan dan kata tidak baku."""
    return " ".join(NORMALISASI.get(word, word) for word in text.split())


def _tokenize(text: str) -> list:
    """Tahap 4: Tokenizing — split ke list token."""
    return text.split()


def _remove_stopwords(tokens: list) -> list:
    """Tahap 5: Stopword removal dengan penjagaan kata sentimen."""
    return [
        w for w in tokens
        if (w not in _STOPWORDS or w in KATA_SENTIMEN_PENTING) and len(w) > 2
    ]


def _stemming(tokens: list) -> list:
    """Tahap 6: Stemming ke bentuk dasar via Sastrawi ECS."""
    if _STEMMER is None:
        return tokens
    return [_STEMMER.stem(w) for w in tokens]


def preprocess_for_model(text: str) -> str:
    """
    Full 6-tahap preprocessing → string teks bersih siap TF-IDF.

    URUTAN: Case Folding → Cleaning → Normalisasi → Tokenizing
            → Stopword Removal → Stemming

    Pipeline HARUS sama persis dengan yang dipakai saat training model.
    """
    s1 = _case_folding(text)    # Tahap 1
    s2 = _cleaning(s1)          # Tahap 2
    s3 = _normalisasi(s2)       # Tahap 3
    s4 = _tokenize(s3)          # Tahap 4
    s5 = _remove_stopwords(s4)  # Tahap 5
    s6 = _stemming(s5)          # Tahap 6
    return " ".join(s6)


def preprocess_untuk_lexicon(text: str) -> str:
    """
    Preprocessing RINGAN untuk lexicon matching.
    Tidak di-stem → kata asli bisa dicocokkan dengan lexicon.
    Pipeline: Case Folding → Cleaning → Normalisasi saja.
    """
    s1 = _case_folding(text)
    s2 = _cleaning(s1)
    s3 = _normalisasi(s2)
    return s3


# ═══════════════════════════════════════════════════════════
#  LEXICON SCORER
# ═══════════════════════════════════════════════════════════

def _hitung_skor_lexicon(teks_lexicon: str) -> dict:
    """
    Hitung skor positif dan negatif dari teks via lexicon.

    NEGATION HANDLING:
    Kata negasi dalam window 2 kata sebelum kata sentimen → polaritas dibalik.
    Contoh: "tidak bagus" → ada "tidak" sebelum "bagus" (POSITIF)
            → skor_neg += 1 (bukan skor_pos)

    Return: {"positif": int, "negatif": int, "net": int}
    """
    tokens = teks_lexicon.split()
    skor_pos = 0
    skor_neg = 0

    for i, token in enumerate(tokens):
        ada_negasi = any(
            tokens[i - j] in KATA_NEGASI
            for j in range(1, 3)
            if i - j >= 0
        )

        if token in LEXICON_POSITIF:
            if ada_negasi:
                skor_neg += 1
            else:
                skor_pos += 1
        elif token in LEXICON_NEGATIF:
            if ada_negasi:
                skor_pos += 1
            else:
                skor_neg += 1

    return {
        "positif": skor_pos,
        "negatif": skor_neg,
        "net": skor_pos - skor_neg,
    }


# ═══════════════════════════════════════════════════════════
#  HYBRID CLASSIFIER
# ═══════════════════════════════════════════════════════════

# Normalisasi label dari berbagai format yang mungkin dipakai model
_LABEL_MAP = {
    "positif": "Positif", "Positif": "Positif", "positive": "Positif", "pos": "Positif",
    "negatif": "Negatif", "Negatif": "Negatif", "negative": "Negatif", "neg": "Negatif",
    "netral":  "Netral",  "Netral":  "Netral",  "neutral":  "Netral",  "net": "Netral",
}


def _prediksi_model(teks_model: str):
    """
    Dapatkan prediksi dari NB model.
    Return: (label_norm, confidence, proba_dict) atau None.
    """
    model, tfidf = _load_model()
    if model is None or tfidf is None or not teks_model.strip():
        return None
    try:
        vec      = tfidf.transform([teks_model])
        pred_raw = model.predict(vec)[0]
        proba    = model.predict_proba(vec)[0]
        classes  = list(model.classes_)

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


def _klasifikasi_hybrid(
    teks_model: str,
    skor: dict,
    teks_lower: str,
) -> tuple:
    """
    Klasifikasi hybrid: sinyal lexicon + model NB.

    LOGIKA KEPUTUSAN (berurutan):

    Layer 1 — Override Positif KUAT (net >= 2):
      → Positif, confidence 60–92%

    Layer 2 — Override Positif LEMAH (net == 1):
      → Cek model; jika model < 65% yakin Negatif → Positif
      → Jika model sangat yakin Negatif → tetap Positif (confidence rendah)

    Layer 3 — Override Negatif KUAT (net <= -2):
      → Negatif, confidence 60–90%

    Layer 4 — Fallback Model NB:
      → Prediksi model dipakai, TAPI:
        • Jika model = Negatif AND net >= 0 AND confidence < 75%
          → downgrade ke Netral (koreksi bias model)
        • Kasus lainnya → percaya model

    Layer 5 — Ultimate Fallback (model tidak tersedia):
      → Gunakan skor lexicon saja

    Return: (label: str, confidence: float)
    """
    net = skor["net"]
    pos = skor["positif"]

    # ── Layer 1: Positif KUAT ─────────────────────────────────────────────────
    if net >= 2:
        conf = min(0.60 + (net * 0.07), 0.92)
        return ("Positif", round(conf, 3))

    # ── Layer 2: Positif LEMAH ────────────────────────────────────────────────
    if net == 1 and pos >= 1:
        model_result = _prediksi_model(teks_model)
        if model_result is not None:
            _, _, proba_dict = model_result
            neg_prob = proba_dict.get("Negatif", 0.0)
            if neg_prob < 0.65:
                conf = round(0.55 + (0.65 - neg_prob) * 0.3, 3)
                return ("Positif", min(conf, 0.80))
            else:
                return ("Positif", 0.55)
        else:
            return ("Positif", 0.58)

    # ── Layer 3: Negatif KUAT ─────────────────────────────────────────────────
    if net <= -2:
        conf = min(0.60 + (abs(net) * 0.06), 0.90)
        return ("Negatif", round(conf, 3))

    # ── Layer 4: Fallback Model NB ────────────────────────────────────────────
    model_result = _prediksi_model(teks_model)
    if model_result is not None:
        label_norm, confidence, proba_dict = model_result

        # Anti-bias correction:
        # Model prediksi Negatif tapi tidak ada sinyal negatif dari lexicon
        # dan confidence < 75% → kemungkinan bias → turunkan ke Netral
        if label_norm == "Negatif" and net >= 0 and confidence < 0.75:
            corrected_conf = round(0.50 + max(0, confidence - 0.50) * 0.2, 3)
            return ("Netral", corrected_conf)

        return (label_norm, round(confidence, 3))

    # ── Layer 5: Ultimate Fallback ────────────────────────────────────────────
    if net > 0:
        return ("Positif", 0.55)
    elif net < 0:
        return ("Negatif", 0.55)
    else:
        return ("Netral", 0.50)


# ═══════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY
# ═══════════════════════════════════════════════════════════

def bersihkan_teks(text: str) -> str:
    """[LEGACY] Gunakan preprocess_for_model() untuk pipeline lengkap."""
    return preprocess_for_model(text)


def prediksi_sentimen(list_text: list):
    """
    [LEGACY] Prediksi batch dengan hybrid classifier.
    Return: (list clean_texts, list labels)
    """
    clean_texts = [preprocess_for_model(t) for t in list_text]
    labels = []
    for text in list_text:
        teks_model   = preprocess_for_model(text)
        teks_lexicon = preprocess_untuk_lexicon(text)
        teks_lower   = str(text).lower()
        skor         = _hitung_skor_lexicon(teks_lexicon)
        label, _     = _klasifikasi_hybrid(teks_model, skor, teks_lower)
        labels.append(label)
    return clean_texts, labels