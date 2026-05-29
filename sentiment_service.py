"""
sentiment_service.py  —  Hybrid Classifier (versi perbaikan)
=============================================================
Perbaikan utama vs versi sebelumnya:
  1. LEXICON DIPERLUAS  — kata positif & negatif yang tidak ada di vocab TF-IDF
     (bagus, mantap, setuju, puas, hemat, berhasil, dll.) kini tetap bisa
     terdeteksi melalui lexicon scoring.
  2. THRESHOLD DISESUAIKAN — Layer 1 diperlonggar (net >= 2 → Positif),
     Layer anti-bias diperketat agar prediksi lebih proporsional.
  3. NEGATION WINDOW DIPERLUAS — window 3 kata (sebelumnya 2) agar
     "tidak terlalu bagus" tetap terdeteksi negasinya.
  4. PREPROCESSING IDENTIK dengan preprocessing_page.py (5 tahap).
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
}


# ═══════════════════════════════════════════════════════════
#  LEXICON SENTIMEN
#  Diperluas agar kata yang tidak ada di vocab TF-IDF tetap
#  bisa berkontribusi melalui jalur lexicon scoring.
# ═══════════════════════════════════════════════════════════

LEXICON_POSITIF = {
    # Umum & informal
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
    "solusi", "manfaat", "menguntungkan",
    "memuaskan", "membanggakan", "mengagumkan",
    "sehat", "fair", "wajar",
    "syukur", "alhamdulillah",
    "saing", "kompetitif",
    # Domain ongkir/ecommerce positif
    "terjangkau", "hemat", "efisien", "mudah", "praktis",
    "cepat", "aman", "terpercaya", "andalan",
    # Dukungan kebijakan
    "dukung", "setuju", "bagus", "tepat", "bijak",
    "perlu", "penting", "benar", "wajar", "adil",
}

LEXICON_NEGATIF = {
    # Umum
    "buruk", "jelek", "parah", "rusak", "hancur", "ancur",
    "gagal", "ambruk", "terpuruk", "bangkrut",
    "bohong", "tipu", "curang", "manipulasi", "korupsi",
    "kebohongan", "penipuan",
    "kecewa", "mending", "malah", "marah", "sedih",
    "khawatir", "takut", "benci", "jijik", "muak",
    "kesal", "frustrasi", "geram", "dongkol",
    "mahal", "rugi", "merugikan", "rugikan",
    "lambat", "lemot", "lelet", "ribet", "susah",
    "sulit", "bermasalah",
    "ngaco", "ngasal", "gaje", "receh",
    "tolol", "bodoh", "idiot", "goblok",
    "mengecewakan", "menyebalkan", "menyusahkan",
    "monopoli", "licik",
    # Domain ongkir negatif
    "boros", "memberatkan", "menyulitkan",
    "repot", "ribet", "ngeributin", "ribut",
    # Kritik kebijakan
    "salah", "keliru", "gegabah", "sembarangan",
    "tidak jelas", "ngawur", "asal",
}

KATA_NEGASI = {
    "tidak", "bukan", "jangan", "belum", "tanpa", "kurang",
    "anti", "non", "tak", "ga", "gak", "nggak", "ngga",
    "enggak", "engga",
}


# ═══════════════════════════════════════════════════════════
#  LOAD NORMALISASI DARI FILE
# ═══════════════════════════════════════════════════════════

def _load_normalization() -> dict:
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

    DOMAIN_OVERRIDES = {
        "shopee": "shopee", "tokopedia": "tokopedia", "lazada": "lazada",
        "tiktok": "tiktok", "bukalapak": "bukalapak", "blibli": "blibli",
        "sicepat": "sicepat", "jne": "jne", "jnt": "jnt",
        "anteraja": "anteraja", "ninja": "ninja",
        "freeongkir": "gratis ongkos kirim",
        "gratisongkir": "gratis ongkos kirim",
        "ongkir": "ongkos kirim", "ongkr": "ongkos kirim",
        "bykrm": "biaya kirim", "biayakirim": "biaya pengiriman",
        "komdigi": "komdigi", "kemendag": "kementerian perdagangan",
        "kominfo": "kementerian komunikasi",
        "ecommerce": "e commerce", "marketplace": "marketplace",
        "seller": "penjual", "buyer": "pembeli", "online": "online",
        # Negasi tambahan
        "gk": "tidak", "ga": "tidak", "gak": "tidak",
        "nggak": "tidak", "ngga": "tidak", "tdk": "tidak",
        "tak": "tidak", "enggak": "tidak", "engga": "tidak",
        "kagak": "tidak", "kaga": "tidak", "ndak": "tidak",
        "ngak": "tidak",
        # Intensitas
        "bgt": "banget", "bngt": "banget", "bget": "banget",
        "bgtt": "banget",
        # Positif informal
        "mantep": "mantap", "mntap": "mantap",
        "bener": "benar", "beneran": "benar",
        "kece": "keren", "sip": "baik",
        # Negatif informal
        "ancur": "hancur", "parahh": "parah",
    }
    norm_dict.update(DOMAIN_OVERRIDES)
    return norm_dict


# ═══════════════════════════════════════════════════════════
#  LOAD STOPWORDS DARI FILE
# ═══════════════════════════════════════════════════════════

def _load_stopwords() -> set:
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

    # Lindungi kata sentimen penting
    for kata in KATA_SENTIMEN_PENTING:
        base.discard(kata)

    # Tambah noise Twitter
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


# ── Inisialisasi global (dimuat sekali saat modul diimport) ─
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
    """Preprocessing ringan untuk lexicon matching (tanpa stemming)."""
    s1 = _step1_case_folding(text)
    s2 = _step2_cleaning(s1)
    s3 = _step3_normalization(s2, _NORM_DICT)
    return s3


# ═══════════════════════════════════════════════════════════
#  LEXICON SCORER  (dengan negation window diperluas ke 3)
# ═══════════════════════════════════════════════════════════

def _hitung_skor_lexicon(teks_lexicon: str) -> dict:
    """
    Hitung skor sentimen via lexicon + negation handling.

    Perubahan vs versi lama:
    - Window negasi diperluas menjadi 3 kata (sebelumnya 2)
    - Lexicon positif/negatif lebih luas (kata yang tidak ada di vocab TF-IDF)

    Return: {"positif": int, "negatif": int, "net": int}
    """
    tokens   = teks_lexicon.split()
    skor_pos = 0
    skor_neg = 0

    for i, token in enumerate(tokens):
        # Cek negasi dalam window 3 kata sebelumnya
        ada_negasi = any(
            tokens[i - j] in KATA_NEGASI
            for j in range(1, 4)
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
#  HYBRID CLASSIFIER  (diperkuat)
# ═══════════════════════════════════════════════════════════

def _klasifikasi_hybrid(
    teks_model: str,
    skor: dict,
    teks_lower: str,
) -> tuple:
    """
    Klasifikasi hybrid: sinyal lexicon + model NB 3-kelas.

    PERUBAHAN vs versi lama:
    ─────────────────────────────────────────────────────────
    Layer 1 — Override Positif KUAT (net >= 2):
      Confidence lebih tinggi karena lexicon lebih kuat.
      Range: 0.65–0.92

    Layer 1b — Override Negatif KUAT (net <= -2):
      Simetris dengan positif.
      Range: 0.65–0.90

    Layer 2 — Override Positif LEMAH (net == 1):
      Diperlonggar: sekarang berlaku jika model tidak sangat
      yakin negatif (threshold 0.70, sebelumnya 0.65).

    Layer 2b — Override Negatif LEMAH (net == -1):
      Simetris baru. Sebelumnya tidak ada.

    Layer 3 — Fallback Model NB:
      Anti-bias diperketat:
      - Model Negatif + lexicon bersih (net >= 0) + conf < 0.65
        → turunkan ke Netral (threshold naik dari 0.70 ke 0.65)
      - Model Positif + lexicon negatif kuat (net <= -1) + conf < 0.65
        → turunkan ke Netral

    Layer 4 — Ultimate Fallback:
      Lexicon saja jika model tidak tersedia.
    ─────────────────────────────────────────────────────────
    Return: (label: str, confidence: float)
    """
    net = skor["net"]
    pos = skor["positif"]
    neg = skor["negatif"]

    # ── Layer 1a: Positif KUAT ───────────────────────────────────────────────
    if net >= 2:
        conf = min(0.65 + (net * 0.05), 0.92)
        return ("Positif", round(conf, 3))

    # ── Layer 1b: Negatif KUAT ───────────────────────────────────────────────
    if net <= -2:
        conf = min(0.65 + (abs(net) * 0.05), 0.90)
        return ("Negatif", round(conf, 3))

    # ── Layer 2a: Positif LEMAH ──────────────────────────────────────────────
    if net == 1 and pos >= 1:
        model_result = _prediksi_model(teks_model)
        if model_result is not None:
            _, _, proba_dict = model_result
            neg_prob = proba_dict.get("Negatif", 0.0)
            if neg_prob < 0.70:  # diperlonggar dari 0.65
                conf = round(0.55 + (0.70 - neg_prob) * 0.30, 3)
                return ("Positif", min(conf, 0.82))
            else:
                return ("Positif", 0.55)
        return ("Positif", 0.58)

    # ── Layer 2b: Negatif LEMAH (baru) ───────────────────────────────────────
    if net == -1 and neg >= 1:
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

    # ── Layer 3: Fallback Model NB 3-kelas ───────────────────────────────────
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

    # ── Layer 4: Ultimate Fallback ────────────────────────────────────────────
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