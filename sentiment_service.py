"""
sentiment_service.py  —  Hybrid Classifier (versi perbaikan v5)
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

  ════════════════════════════════════════════════════════════════════
  PERBAIKAN v3 — lihat tanda "# >>> FIX v3" untuk lokasi perubahan.
  ════════════════════════════════════════════════════════════════════

  MASALAH 7 — "tidak setuju" / penolakan eksplisit KALAH oleh 'gratis'
    SOLUSI: Tambahkan pola eksplisit POLA_PENOLAKAN_EKSPLISIT
            ("tidak/gak/ga setuju", "kontra", "menolak", dst.) yang
            memberi bobot negatif tambahan di luar mekanisme negasi
            per-token yang sudah ada.

  MASALAH 8 — Kata restriksi selain 'pembatasan' tidak menetralkan 'gratis'
    SOLUSI: Perluas pengecekan dari satu kata "pembatasan" menjadi
            sekumpulan kata KATA_PEMBATASAN ("pembatasan", "dibatasi",
            "membatasi", "batasi", "terbatas", "batasan").

  MASALAH 9 — Frasa meremehkan/dismissif ("cuma bikin", "hanya menambah")
    SOLUSI: Tambahkan POLA_DISMISSIF_NEGATIF.

  MASALAH 10 — Kata intensitas ("sangat", "banget", "sekali") tidak
    memperbesar bobot kata sentimen yang menyertainya.
    SOLUSI: Tambahkan bobot tambahan (+1) jika token lexicon (positif
            ATAU negatif) didahului/diikuti kata intensitas.

  ════════════════════════════════════════════════════════════════════
  PERBAIKAN v4 (dari pengguna) — 'gratis' dihapus dari LEXICON_POSITIF,
  beberapa kata negatif & pola tambahan (chaos, aneh, tahi, samping,
  dikesampingan, gaada kerjaan, dll.) sudah ditambahkan.
  ════════════════════════════════════════════════════════════════════

  PERBAIKAN v5 (versi ini) — lihat tanda "# >>> FIX v5" untuk lokasi
  persis setiap perubahan.
  ════════════════════════════════════════════════════════════════════

  MASALAH 11 — POLA INTENSITAS TERLALU LUAS (BUG SERIUS)
    Pola lama: r"\b(banget|bgt|bngt|bget|bgtt|lebih)\b" → +2 skor NEGATIF
    untuk SEMUA tweet yang mengandung kata "banget" atau "lebih", padahal
    kata ini netral secara intrinsik dan SERING muncul di konteks POSITIF
    ("bagus banget", "lebih murah", "lebih baik pelayanannya"). Akibatnya
    banyak tweet positif/netral salah terdorong ke Negatif.
    SOLUSI: Pola digantikan dengan versi yang HANYA aktif jika kata
    intensitas tersebut berdekatan dengan kata LEXICON_NEGATIF eksplisit
    (mis. "kecewa banget", "ribet banget"). Mekanisme umum untuk semua
    kata intensitas + lexicon (positif/negatif) tetap berjalan otomatis
    lewat KATA_INTENSITAS di _hitung_skor_lexicon (FIX v3 MASALAH 10),
    jadi tidak ada kemampuan deteksi yang hilang — hanya bug overbroad-nya
    yang diperbaiki.

  MASALAH 12 — is_info DIHITUNG TAPI TIDAK PERNAH DIPAKAI (DEAD CODE)
    _hitung_skor_lexicon() sudah mendeteksi tweet informatif dengan benar
    (field 'informatif'), TAPI _klasifikasi_hybrid() hanya membaca
    skor.get("informatif") ke variabel is_info lalu TIDAK PERNAH
    menggunakannya di logika keputusan manapun. Akibatnya tweet yang
    sebenarnya cuma informasi ("disebut dalam diskusi", "sedang ramai
    dibahas") tetap diserahkan ke model NB yang bias Positif.
    SOLUSI: Tambahkan Layer 0 baru di awal _klasifikasi_hybrid yang
    benar-benar memakai is_info: jika tweet terdeteksi informatif DAN
    net == 0 (tidak ada sinyal sentimen eksplisit sama sekali) → Netral
    langsung, sebelum model NB dikonsultasikan.

  MASALAH 13 — TWEET TANPA SINYAL LEXICON SAMA SEKALI TETAP DISERAHKAN
    KE MODEL NB YANG BIAS POSITIF
    Banyak tweet murni informatif/deklaratif ("komdigi mengeluarkan
    kebijakan gratis ongkir") tidak mengandung kata KATA_INFORMATIF
    ataupun kata lexicon apapun (skor_pos = skor_neg = 0), tapi tetap
    diklasifikasikan Positif oleh model NB karena bias kata domain
    'gratis ongkir' di data training.
    SOLUSI: Tambahkan Layer 0a — jika skor_pos == 0 DAN skor_neg == 0
    (tidak ada sinyal lexicon ATAU pola apapun ditemukan), langsung
    Netral, tidak usah konsultasi model. Ini adalah override paling
    aman: tanpa sinyal sentimen sama sekali, default yang paling logis
    adalah Netral, bukan menyerahkan keputusan ke model yang terbukti
    bias.

  MASALAH 14 — "keputusan/kebijakan ... tepat" TIDAK PERNAH POSITIF
    Kata 'tepat' sengaja dikeluarkan dari LEXICON_POSITIF karena
    kontekstual (lihat MASALAH 2), tapi akibatnya kalimat seperti
    "pembatasan gratis ongkir adalah keputusan tepat" (pujian eksplisit,
    tanpa pembanding "daripada") tidak pernah terdeteksi Positif.
    SOLUSI: Tambahkan POLA_KONTEKS_POSITIF — pola frasa yang HANYA
    menangkap 'tepat' ketika muncul sebagai pujian terhadap
    keputusan/kebijakan/langkah, dan TIDAK match jika diikuti pola
    pembanding "daripada" dalam jarak dekat (supaya "lebih tepat X
    daripada Y" tetap tidak dianggap pujian berdiri sendiri).

  MASALAH 15 — KATA INFORMATIF KURANG LENGKAP
    "diskusi", "disebut", "dibahas", "ramai dibahas", "mengenai" sering
    muncul di tweet yang sekadar menyebut topik tanpa opini, tapi belum
    ada di KATA_INFORMATIF.
    SOLUSI: Tambahkan kata-kata tersebut ke KATA_INFORMATIF.

  MASALAH 16 — VARIASI 'ngurus' (tanpa akhiran) BELUM ADA
    'ngurusin', 'ngurusi', 'urusin' sudah ada di lexicon negatif, tapi
    variasi pendek 'ngurus' (mis. "ngurus ongkir") belum ada.
    SOLUSI: Tambahkan 'ngurus' ke LEXICON_NEGATIF & set protect.
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
    "murah", "hemat", "terjangkau", "cepat",
    "aman", "mudah", "praktis", "terpercaya",
    # Negatif umum
    "kecewa", "mending", "malah", "buruk", "jelek", "parah",
    "gagal", "hancur", "rusak", "bohong", "tipu", "korupsi",
    # Negatif domain e-commerce/ongkir
    "mahal", "lambat", "lelet", "ribet", "susah", "repot",
    "rugi", "boros",
    # Emosi
    "marah", "sedih", "khawatir", "cemas", "resah", "takut", "benci", "sesal", "trauma",

        # ── TAMBAHAN ────────────────────────────────────────────
'malas', 'males', 'enggan', 'bete', 'jengkel', 'depresi',
'gondok', 'dongkol', 'sebal', 'bosan', 'jenuh', 'heran', 'bingung', 'pusing', 'stress', 'panik',
'kapok', 'muak', 'frustrasi', 'menyesal', 'nyesel', 'mahal', 'gratis',

    # ── TAMBAHAN BARU — PENYELARASAN (kata sudah ada di LEXICON_POSITIF/
    #    LEXICON_NEGATIF tapi belum dijaga dari stopword removal di sini;
    #    ditambahkan agar dua arah saling melengkapi, TIDAK ADA YANG DIHAPUS) ──

    'mantep', 'kerenn', 'bravo', 'salut', 'apresiasi', 'hebat',
    'gembira', 'bahagia', 'berjaya', 'berantas', 'melindungi',
    'perlindungan', 'menguntungkan', 'memuaskan', 'diapresiasi',
    'sepakat', 'fair',
    'tolol', 'bodoh', 'goblog', 'goblok', 'guoblog', 'guoblok',
    'dungu', 'idiot', 'dikesampingkan', 'bego', 'anjing', 'bangsat', 'anjing', 'bangsat', 'anjjj',
    'bajingan', 'brengsek', 'asu', 'gila', 'edan', 'biadab', 'anjir', 'malah',
    'taik', 'tai', 'sok', 'keliru', 'payah', 'lemah', 'malah',
    'ngawur', 'kacau', 'berantakan', 'gajelas', 'menipu', 'penipuan',
    'curang', 'manipulasi', 'koruptor', 'maling', 'skandal',
    'kesal', 'sebel', 'menolak', 'tolak', 'protes', 'keberatan',
    'kontra', 'merugikan', 'rugikan', 'menyusahkan', 'membebani',
    'menghambat', 'mengecewakan', 'menyebalkan', 'percuma', 'siasia',
    'konyol', 'absurd', 'miris', 'ironis', 'memalukan',
    'memprihatinkan', 'masalah', 'bermasalah', 'ricuh', 'sulit',
    'rumit', 'judol', 'pinjol', 'ngurusin', 'ngurusi', 'urusin', 'ngurus',
    'sibuk', 'melempem', 'ckckck', 'astaga', 'blokir', 'hambat',
    'diskriminasi', 'zalim', 'bocor',

    # ── TAMBAHAN BARU — VARIASI KATA LEBIH BERAGAM (slang/sinonim umum
    #    di Twitter/X Indonesia, domain ongkir/e-commerce/kebijakan publik) ──
    # Variasi positif
    'mantul', 'jos', 'joss', 'sip', 'top', 'recommended', 'rekomen',
    'kredibel', 'akuntabel', 'responsif', 'profesional', 'amanah',
    'efektif', 'efisien', 'membanggakan', 'memudahkan', 'menolong',
    'optimal', 'progresif', 'transparan', 'akurat', 'konsisten',
    # Variasi negatif / slang kekecewaan
    'zonk', 'ngeselin', 'nyebelin', 'norak', 'lebay', 'baper',
    'overproteksi', 'overreaksi', 'asal-asalan', 'ngasal', 'amburadul',
    'serampangan', 'mubazir', 'sia', 'tabok', 'sotoy', 'songong',
    'arogan', 'plinplan', 'plin-plan', 'lemot', 'ngeluh', 'mengeluh',
    'gerutu', 'menggerutu', 'gabut', 'galau', 'overthinking',
    'parno', 'paranoid', 'insecure', 'gaslight', 'gaslighting',
    'dramatis', 'lebai', 'absurditas', 'kontroversi', 'kontroversial',

    # >>> FIX v3 — MASALAH 7 & 8: kata-kata penolakan eksplisit dan
    # variasi kata restriksi ("dibatasi" dkk.) ditambahkan di sini juga,
    # supaya preprocess_for_model() (jalur model NB) TIDAK menghapusnya
    # sebagai stopword. Lexicon-matching (preprocess_untuk_lexicon) sudah
    # otomatis aman karena jalur itu tidak melakukan stopword removal,
    # tapi kita amankan dua arah agar konsisten.
    'kontra', 'menolak', 'tolak', 'sependapat',
    'dibatasi', 'membatasi', 'batasi', 'terbatas', 'batasan',
    'cuma', 'hanya', 'bikin', 'makin',

    # >>> FIX v4 (dari pengguna): kata-kata baru dari MASALAH 11-16 lama
    'chaos', 'aneh', 'tahi', 'jir', 'samping', 'sampingkan',
    'kesampingkan', 'kesampingan', 'dikesampingan',

    # >>> FIX v5 — MASALAH 16: variasi 'ngurus' (tanpa akhiran) sudah
    # ditambahkan di atas pada baris "judol, pinjol, ..." (lihat 'ngurus').
}


# ═══════════════════════════════════════════════════════════
#  LEXICON SENTIMEN  (DIPERBAIKI — kata kontekstual dihapus,
#  DISELARASKAN penuh dengan KATA_SENTIMEN_PENTING, dan
#  DIPERKAYA dengan variasi kata/slang yang lebih beragam)
#
#  PRINSIP PEMILIHAN KATA LEXICON:
#  Kata masuk lexicon HANYA jika bisa berdiri sendiri sebagai
#  sinyal sentimen tanpa bergantung konteks kalimat di sekitarnya.
#
#  DIHAPUS dari versi lama karena terlalu kontekstual:
#    "baik", "benar", "penting", "tepat", "jelas", "transparan",
#    "amanah", "wajar", "fair", "perlu", "manfaat", "kompetitif"
#  (CATATAN: "fair", "manfaat", "amanah", dan "transparan" tetap
#   TIDAK dimasukkan sebagai token berdiri sendiri yang otomatis
#   menambah skor tanpa syarat khusus, KECUALI "fair" yang di versi
#   ini tetap dipertahankan ada — TIDAK ADA kata yang dihapus dari
#   set manapun di bawah, hanya ditambah.)
#
#  >>> FIX v5 — MASALAH 14: 'tepat' TETAP TIDAK dimasukkan sebagai token
#  lexicon berdiri sendiri (supaya "lebih tepat X daripada Y" tidak
#  otomatis positif). Sebagai gantinya, pujian eksplisit terhadap
#  "keputusan/kebijakan tepat" ditangkap lewat POLA_KONTEKS_POSITIF
#  di bawah (lihat MASALAH 14).
# ═══════════════════════════════════════════════════════════

LEXICON_POSITIF = {
    'setuju', 'dukung', 'mendukung', 'pro', 'sepakat', 'menjaga', 'melindungi',
    'bagus', 'keren', 'mantap', 'mantep', 'bravo', 'kerenn',
    'salut', 'apresiasi', 'hebat', 'oke',
    'bangga', 'senang', 'suka', 'puas', 'gembira', 'bahagia',
    'berhasil', 'sukses', 'berjaya',
    'andal', 'handal', 'gercep', 'bijak', 'bermanfaat',
    'berguna', 'membantu', 'inovatif',
    'berantas', 'melindungi', 'perlindungan',
    'untung', 'menguntungkan', 'solusi', 'memuaskan', 'diapresiasi', 'apresiasi', 'tegas', 'sigap', 'tanggap', 'adil', 'fair',

    # ── TAMBAHAN BARU — PENYELARASAN dari KATA_SENTIMEN_PENTING
    #    (kata sudah dijaga dari stopword removal, kini ditambahkan
    #    di sini agar benar-benar ikut skoring lexicon) ──
    'bantu', 'lanjut', 'manfaat',
    'murah', 'hemat', 'terjangkau', 'cepat',
    'aman', 'mudah', 'praktis', 'terpercaya',
    'sejahtera', 'berkembang', 'maju',

    # ── TAMBAHAN BARU — VARIASI KATA LEBIH BERAGAM ──
    'mantul', 'jos', 'joss', 'sip', 'top', 'recommended', 'rekomen',
    'kredibel', 'akuntabel', 'responsif', 'profesional', 'amanah',
    'efektif', 'efisien', 'membanggakan', 'memudahkan', 'menolong',
    'optimal', 'progresif', 'transparan', 'akurat', 'konsisten',
    # NOTE: 'gratis' SENGAJA TIDAK ada di sini (FIX v4 MASALAH 11 lama) —
    # 'gratis ongkir' adalah topik dataset, bukan sinyal opini.
}

LEXICON_NEGATIF = {
    # Umpatan
    'tolol', 'bodoh', 'goblog', 'goblok', 'guoblog', 'asu', 'guoblok', 'dungu', 'idiot', 'dikesampingkan', 'bego', 'anjing', 'bangsat', 'bajingan', 'brengsek', 'asu', "gajeeee",
    'bego', 'anjing', 'bangsat', 'bajingan', 'brengsek', 'asu', "gajeeee", "bangsat", "bajingan", "brengsek", "asu", "gaje", "gajelas",
    'gila', 'edan', 'biadab', 'anjir', 'taik', 'tai', 'sok', 'malah', "keguoblokan", "kegoblokan", "kebodohan", "kebegoan", "kegilaan", "kebiadaban", "ketololan",
    # Penilaian buruk
    'chaos', 'kacau', 'aneh', 'tahi', 'jir', 'sampingkan', 'kesampingkan', 'kesampingan', 'dikesampingan', 'salah', 'keliru', 'gagal', 'buruk', 'jelek', 'parah', 'mahal', 'lelet', 'lambat', 'ribet', 'repot', 'rugi', 'boros',
    'payah', 'lemah', 'ngawur', 'kacau', 'hancur', 'berantakan', 'gajelas',
    # Ketidakjujuran
    'bohong', 'tipu', 'menipu', 'penipuan', 'curang',
    'manipulasi', 'korupsi', 'koruptor', 'maling', 'skandal',
    # EMOSI NEGATIF
    'kecewa', 'marah', 'kesal', 'jengkel', 'gondok',
    'dongkol', 'sebal', 'sebel', 'benci', 'muak', 'kekecewaan', 'merepotkan', 'merugikan', 'menyusahkan', 'membebani', 'keberatan',
    'frustrasi', 'khawatir', 'cemas', 'resah', 'takut',
    'sedih', 'menyesal', 'nyesel', 'sesal', 'kapok', 'trauma',
    'malas',
    'males',
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
    'melempem',
    # >>> FIX v5 — MASALAH 16: variasi pendek 'ngurus' (mis. "ngurus
    # ongkir") ditambahkan di sini, supaya tidak cuma 'ngurusin'/
    # 'ngurusi'/'urusin' yang dikenali sebagai sinyal negatif.
    'ngurus',
    # Seruan negatif
    'ckckck', 'astaga',
    # Lain
    'blokir', 'hambat', 'diskriminasi', 'zalim',

    # ── TAMBAHAN BARU — PENYELARASAN dari KATA_SENTIMEN_PENTING ──
    'jengkel', 'depresi', 'heran', 'bingung', 'pusing', 'stress', 'panik',
    'rusak',

    # ── TAMBAHAN BARU — VARIASI KATA LEBIH BERAGAM (slang/sinonim) ──
    'zonk', 'ngeselin', 'nyebelin', 'norak', 'lebay', 'baper',
    'overproteksi', 'overreaksi', 'asal-asalan', 'ngasal', 'amburadul',
    'serampangan', 'mubazir', 'sia', 'tabok', 'sotoy', 'songong',
    'arogan', 'plinplan', 'lemot', 'ngeluh', 'mengeluh',
    'gerutu', 'menggerutu', 'gabut', 'galau', 'overthinking',
    'parno', 'paranoid', 'insecure', 'gaslight', 'gaslighting',
    'dramatis', 'lebai', 'absurditas', 'kontroversi', 'kontroversial',

    # CATATAN PENTING: frasa berspasi 'gk jelas', 'gak jelas', 'sok tahu',
    # 'sok pintar', 'sok bijak', 'ga prioritas' SENGAJA TIDAK ditaruh di
    # sini (token hasil .split() tidak akan pernah cocok dengan frasa
    # berspasi). Semua frasa tersebut TETAP ADA dan TETAP BERFUNGSI lewat
    # POLA_FRASA_NEGATIF_TAMBAHAN (regex atas teks penuh) di bawah.
}

KATA_NEGASI = {
    "tidak", "bukan", "jangan", "belum", "tanpa", "kurang",
    "anti", "non", "tak", "ga", "gak", "nggak", "ngga",
    "enggak", "engga",
}

# >>> FIX v3 — MASALAH 10: daftar kata intensitas, dipakai untuk
# menambah bobot kata lexicon (positif/negatif) yang berdekatan dengannya.
KATA_INTENSITAS = {"sangat", "banget", "amat", "sekali", "paling", "bgt"}

# >>> FIX v3 — MASALAH 8: kata-kata yang menandakan konteks "dibatasi/
# restriksi".
KATA_PEMBATASAN = {"pembatasan", "dibatasi", "membatasi", "batasi", "terbatas", "batasan"}


# ═══════════════════════════════════════════════════════════
#  POLA KONTEKSTUAL  (BARU — deteksi kritik implisit)
# ═══════════════════════════════════════════════════════════

POLA_KOMPARATIF_NEGATIF = [
    (r"\bmending\b.{1,80}\bdaripada\b",     2),
    (r"\bmalah\b.{1,80}\bdaripada\b",     2),
    (r"\blebih baik\b.{1,80}\bdaripada\b",  1),
    (r"\bdaripada\b.{1,50}\bmending\b",     1),
    (r"\bketimbang\b.{1,60}\b(kebijakan|urus|ngurusin)\b", 1),
    (r"\balih-alih\b.{1,80}\b(malah|mending)?\b", 1),
    (r"\bketimbang\b.{1,80}\b(mending|malah)\b", 2),
    (r"\bharusnya\b.{1,60}\bbukan\b", 1),
]

POLA_KRITIK_TERSIRAT = [
    (r"\b(tidak|tak|gak|ga|gk|ngga|nggak)\b.{0,15}\bpenting\b",  1),
    (r"\b(tidak|tak|gak|ga|gk|ngga|nggak)\b.{0,15}\bjelas\b",  1),
    (r"\b(tidak|tak|gak|ga|ngga|nggak)\b.{0,15}\bbecus\b",  1),
    (r"\b(gaada|ga ada|gak ada|tidak ada|kurang)\s*kerjaan\b", 2),
    (r"\bmending\b.{1,30}\b(sampingkan|kesampingkan|dulu|aja)\b", 1),
    (r"\b(ngapain|buat apa|untuk apa|ngapain)\b.{1,50}\b(kebijakan|ongkir|aturan|regulasi)\b", 2),
    (r"\b(gak|ga|tidak|tak|ngga)\b\s*(usah|perlu)\b",          1),
    (r"\b(percuma|sia-sia|buang-buang)\b",                      2),
    (r"\b(sangat merugikan|sia-sia|buang-buang)\b",                      2),
    (r"\b(sangat mengecewakan|sia-sia|buang-buang)\b",                      2),
    (r"\b(sangat menyulitkan|sia-sia|melempem)\b",                      2),
    (r"\b(sangat kecewa|sia-sia|buang-buang)\b",                      2),
    (r"\b(sangat tidak setuju|sia-sia|buang-buang)\b",                      2),
    (r"\b(malas dan kecewa|sia-sia|buang-buang)\b",                      2),
    (r"\b(nyusahin banget|sia-sia|buang-buang)\b",                      2),
    (r"\b(marah|emosi|benci)\b",                      2),

    # >>> FIX v5 — MASALAH 11: pola lama di sini adalah
    #     r"\b(banget|bgt|bngt|bget|bgtt|lebih)\b"  (bobot 2)
    # yang SANGAT BERMASALAH karena cocok dengan SEMUA tweet yang
    # mengandung kata "banget" atau "lebih" — termasuk konteks positif
    # seperti "bagus banget", "lebih murah", "membantu banget". Pola
    # ini SELALU menambah +2 skor negatif tanpa syarat, sehingga sangat
    # mudah membuat tweet positif/netral salah menjadi negatif.
    # DIGANTI dengan versi yang HANYA aktif jika kata intensitas
    # tersebut benar-benar berdekatan (window ~15 karakter) dengan kata
    # negatif eksplisit — kasus seperti "kecewa banget", "ribet banget",
    # "nyesel bgt" tetap tertangkap, tapi "bagus banget" / "lebih murah"
    # TIDAK lagi otomatis kena skor negatif. Penguatan intensitas umum
    # (untuk SEMUA kata lexicon, bukan hanya daftar di bawah) tetap
    # berjalan otomatis lewat mekanisme KATA_INTENSITAS di
    # _hitung_skor_lexicon (FIX v3 MASALAH 10), jadi tidak ada
    # kemampuan deteksi yang hilang.
    (r"\b(sangat|banget|bgt|bngt|bget|bgtt|amat|sekali)\b.{0,15}"
     r"\b(kecewa|marah|kesal|rugi|susah|ribet|mahal|repot|lambat|lelet|"
     r"tolak|menolak|gagal|buruk|jelek|parah|sedih|nyesel|menyesal|"
     r"benci|muak|frustrasi|merugikan|menyusahkan)\b", 1),
    (r"\b(kecewa|marah|kesal|rugi|susah|ribet|mahal|repot|lambat|lelet|"
     r"tolak|menolak|gagal|buruk|jelek|parah|sedih|nyesel|menyesal|"
     r"benci|muak|frustrasi|merugikan|menyusahkan)\b.{0,15}"
     r"\b(sangat|banget|bgt|bngt|bget|bgtt|amat|sekali)\b", 1),

    (r"\b(nyusahin|ribet|maksain|susah-susahin)\b",                      2),

    (r"\bmending\b.{1,30}\b(ngurusin|urusin|urus)\b",                    1),
    (r"\bmalah\b.{1,30}\b(ngurusin|urusin|urus)\b",                    1),
    (r"\bjangan\b.{1,30}\b(ngurusin|urusin|urus)\b",                    1),
    (r"\bmarah\b.{1,30}\b(benci|emosi)\b",                    1),

    (r"\b(kebijakan|aturan|regulasi)\b.{0,20}\bbegini\b",       1),
    (r"\bapa\b.{0,10}\b(guna|manfaat|untung)\b.{0,10}(nya|sih|ini)\b", 1),

    (r"\b(buat apa sih|ngapain juga|emang perlu)\b", 1),
    (r"\bkapan\b.{0,15}\b(beres|selesai|kelar)\b", 1),
    (r"\bkatanya\b.{1,40}\btapi\b", 1),
    (r"\bujung-ujungnya\b", 1),
    (r"\bphp\b", 1),
    (r"\bharapan palsu\b", 1),
    (r"\bpemberi harapan palsu\b", 1),

    (r"\b(tidak|gak|ga|gk|nggak|ngga|tak|kagak|kaga)\s+setuju\b", 2),
    (r"\b(tidak|gak|ga|gk|nggak|ngga|tak)\s+sependapat\b", 2),
    (r"\bkontra\b.{0,40}\b(kebijakan|aturan|regulasi|ongkir)\b", 1),
    (r"\bmenolak\b.{0,40}\b(kebijakan|aturan|regulasi|ongkir)\b", 1),

    (r"\b(cuma|hanya)\s+(bikin|nambah|menambah|membuat)\b", 1),
    (r"\bmakin\s+(bikin|nambah|menambah|membuat)\b", 1),
]

# >>> FIX v5 — MASALAH 14: pola konteks positif — pujian eksplisit
# terhadap keputusan/kebijakan/langkah yang menyebut kata "tepat",
# tapi HANYA jika TIDAK diikuti pola pembanding "daripada" dalam jarak
# dekat (negative lookahead), supaya "lebih tepat X daripada Y" tetap
# tidak dihitung sebagai pujian berdiri sendiri (itu tetap ditangani
# oleh POLA_KOMPARATIF_NEGATIF di atas).
POLA_KONTEKS_POSITIF = [
    (r"\b(keputusan|kebijakan|langkah)\b.{0,15}\btepat\b(?!.{0,40}\bdaripada\b)", 1),
    # "tepat sasaran" — pujian eksplisit umum di wacana kebijakan publik
    (r"\btepat\s+sasaran\b", 1),
    # "sudah benar / sudah tepat" sebagai penegasan dukungan
    (r"\bsudah\s+(benar|tepat)\b(?!.{0,40}\bdaripada\b)", 1),
]

# ── Pola frasa negatif tambahan ──────────────────────────────────────
POLA_FRASA_NEGATIF_TAMBAHAN = [
    (r"\bsok\s+tahu\b",          2),
    (r"\bsok\s+pintar\b",        2),
    (r"\bsok\s+bijak\b",         2),
    (r"\b(gk|gak|ga|tidak|tak|ngga|nggak|kagak)\s+jelas\b", 2),
    (r"\b(gk|gak|ga|tidak|tak|ngga|nggak|kagak)\s+prioritas\b", 2),
    (r"\bg[ae]je+\b",            1),
    (r"\bsusah-susahin\b",       2),
    (r"\b(kerja|kerjanya)\b.{0,10}\b(gak|ga|tidak|tak)\b.{0,10}\bbecus\b", 2),
    (r"\basal[\s-]asalan\b",     2),
    (r"\bbuang[\s-]buang\s+waktu\b", 2),
    (r"\b(gk|gak|ga|tidak|tak|ngga|nggak|kagak)\s+masuk\s+akal\b", 2),
    (r"\bomon[\s-]omon\b|\bomong\s+kosong\b", 2),
]

# Kata informatif — menunjukkan tweet berisi pelaporan/informasi netral
# >>> FIX v5 — MASALAH 15: ditambah "diskusi", "disebut", "dibahas",
# "bahas", "ramai", "mengenai", "terkait" — sangat umum pada tweet yang
# cuma menyebut topik tanpa opini ("disebut dalam diskusi mengenai...",
# "sedang ramai dibahas").
KATA_INFORMATIF = {
    "berita", "melihat", "membaca", "mendengar", "mengetahui",
    "laporan", "informasi", "kabar", "melaporkan", "dikabarkan",
    "menurut", "dilaporkan", "diberitakan", "dikutip", "mengutip",

    "rilis", "merilis", "mengumumkan", "pengumuman", "update",
    "pembaruan", "siaran", "press release", "konferensi pers",

    # >>> FIX v5 — MASALAH 15
    "diskusi", "disebut", "dibahas", "bahas", "ramai", "mengenai",
    "terkait", "membahas", "perbincangan", "dibicarakan", "wacana",
}


# ═══════════════════════════════════════════════════════════
#  LOAD NORMALISASI DARI FILE
# ═══════════════════════════════════════════════════════════

def _load_normalization() -> dict:
    """
    Muat kamus normalisasi dari file eksternal.
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

    DOMAIN_OVERRIDES: dict = {
        "shopee":       "shopee",
        "tokopedia":    "tokopedia",
        "lazada":       "lazada",
        "tiktok":       "tiktok",
        "bukalapak":    "bukalapak",
        "blibli":       "blibli",
        "chaos":         "kacau",
        "overlapping": "tumpang tindih",
        "overlap":       "tumpang tindih",
        "sicepat":      "sicepat",
        "jne":          "jne",
        "jnt":          "jnt",
        "anteraja":     "anteraja",
        "ninja":        "ninja",
        "freeongkir":   "gratis ongkos kirim",
        "gratisongkir": "gratis ongkos kirim",
        "ongkir":       "ongkos kirim",
        "ongkr":        "ongkos kirim",
        "bykrm":        "biaya kirim",
        "biayakirim":   "biaya pengiriman",
        "komdigi":      "komdigi",
        "kemendag":     "kementerian perdagangan",
        "kominfo":      "kementerian komunikasi",
        "ecommerce":    "e commerce",
        "marketplace":  "marketplace",
        "seller":       "penjual",
        "buyer":        "pembeli",
        "online":       "online",
        "gk":     "tidak", "ga":     "tidak", "gak":    "tidak",
        "nggak":  "tidak", "ngga":   "tidak", "tdk":    "tidak",
        "tak":    "tidak", "enggak": "tidak", "engga":  "tidak",
        "kagak":  "tidak", "kaga":   "tidak", "ndak":   "tidak",
        "ngak":   "tidak",
        "bgt": "banget", "bngt": "banget", "bget": "banget", "bgtt": "banget",
        "mantep":  "mantap", "mntap": "mantap",
        "kece":    "keren",
        "ancur":   "hancur", "parahh": "parah",
        # >>> FIX v5 — MASALAH 14/15 pendukung: beberapa slang umum
        # tambahan supaya pola informatif/positif baru bisa kena match
        # juga pada bentuk slang-nya.
        "dibahas":  "dibahas",
        "disebut":  "disebut",
        # "mending"/"mendingan"/"malah" SENGAJA TIDAK dioverride (lihat
        # catatan panjang di versi sebelumnya — tetap berlaku).
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

    for kata in KATA_SENTIMEN_PENTING:
        base.discard(kata)

    KATA_POLA_PENTING: set = {
        "mending", "mendingan", "daripada", "ketimbang",
        "ngapain", "percuma", "begini",
        "gajelas", "mahal", "nyusahin",
        "malas", "males", "enggan",
        "prioritas", "jelas", "gajeee", "susah-susahin",
        "sok", "tahu", "pintar", "bijak",
        "tai", "taik",
        "aneh", "absurd", "konyol",
        "miris", "ironis", "memalukan", "memprihatinkan",
        "dikesampingkan",
        "gagal", "buruk", "jelek", "parah",
        "ribet", "repot", "susah", "sulit", "rumit",
        "ngurusin", "ngurusi", "urusin", "urus", "ngurus",
        "sibuk", "melempem",
        "ckckck", "astaga",
        "blokir", "hambat", "diskriminasi", "zalim",
        "malah",

        "alih-alih", "harusnya", "kapan", "beres", "selesai", "kelar",
        "katanya", "ujung-ujungnya", "php", "becus", "asal", "asalan",
        "omon", "omong", "kosong",

        "kontra", "menolak", "sependapat",
        "dibatasi", "membatasi", "batasi", "terbatas", "batasan",
        "cuma", "hanya", "bikin", "makin", "nambah", "menambah",

        # >>> FIX v4 (dari pengguna)
        "chaos", "kacau", "tahi", "jir", "samping", "sampingkan",
        "kesampingkan", "kesampingan", "dikesampingan",

        # >>> FIX v5 — MASALAH 14/15: kata penanda pola baru juga harus
        # dijaga dari stopword removal agar regex di atas (yang bekerja
        # di atas teks penuh) tetap punya kata-kata ini utuh.
        "tepat", "sasaran", "benar",
        "diskusi", "disebut", "dibahas", "bahas", "ramai", "mengenai",
        "terkait", "membahas", "perbincangan", "dibicarakan", "wacana",
    }
    for kata in KATA_POLA_PENTING:
        base.discard(kata)

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
    """
    Preprocessing untuk lexicon matching.
    PENTING: TIDAK distem dan TIDAK dihapus stopword-nya agar
    pola kontekstual tetap ada dan bisa dideteksi.
    """
    s1 = _step1_case_folding(text)
    s2 = _step2_cleaning(s1)
    s3 = _step3_normalization(s2, _NORM_DICT)
    return s3


# ═══════════════════════════════════════════════════════════
#  LEXICON SCORER
# ═══════════════════════════════════════════════════════════

def _hitung_skor_lexicon(teks_lexicon: str) -> dict:
    """
    Hitung skor sentimen via lexicon + pola kontekstual + negation handling.
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

    # ── Tahap 2b: Deteksi pola frasa negatif tambahan ─────────────────────
    for pola, bobot in POLA_FRASA_NEGATIF_TAMBAHAN:
        if re.search(pola, teks_lexicon):
            skor_neg += bobot

    # >>> FIX v5 — MASALAH 14: Deteksi pola konteks positif (pujian
    # eksplisit "keputusan/kebijakan tepat", "tepat sasaran", dst.)
    for pola, bobot in POLA_KONTEKS_POSITIF:
        if re.search(pola, teks_lexicon):
            skor_pos += bobot

    # ── Tahap 3: Lexicon per token ────────────────────────────────────────
    for i, token in enumerate(tokens):
        ada_negasi = any(
            tokens[i - j] in KATA_NEGASI
            for j in range(1, 4)
            if i - j >= 0
        )
        ada_pembatasan = (
            any(tokens[i - j] in KATA_PEMBATASAN for j in range(1, 4) if i - j >= 0)
            or any(tokens[i + j] in KATA_PEMBATASAN for j in range(1, 4) if i + j < len(tokens))
        )
        ada_intensitas = (
            any(tokens[i - j] in KATA_INTENSITAS for j in (1, 2) if i - j >= 0)
            or any(tokens[i + j] in KATA_INTENSITAS for j in (1, 2) if i + j < len(tokens))
        )

        if token in LEXICON_POSITIF:
            if ada_negasi:
                skor_neg += 1
                if ada_intensitas:
                    skor_neg += 1
            elif ada_pembatasan and token == "gratis":
                pass
            else:
                skor_pos += 1
                if ada_intensitas:
                    skor_pos += 1

        elif token in LEXICON_NEGATIF:
            if ada_negasi:
                skor_pos += 1
            else:
                skor_neg += 1
                if ada_intensitas:
                    skor_neg += 1

    # ── Tahap 4: Deteksi tweet informatif ────────────────────────────────
    token_set = set(tokens)
    ada_info_kata = bool(token_set & KATA_INFORMATIF)
    ada_sentimen_eksplisit = bool(
        (token_set & LEXICON_POSITIF) | (token_set & LEXICON_NEGATIF)
    )
    is_informatif = (
        ada_info_kata
        and not ada_sentimen_eksplisit
        and skor_neg <= 1
    )

    return {
        "positif":    skor_pos,
        "negatif":    skor_neg,
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

    ALUR KEPUTUSAN (v5):
    ─────────────────────────────────────────────────────────────────────
    Layer 0  — >>> FIX v5 (MASALAH 12, baru): Override Informatif NYATA.
      Sebelumnya is_info dihitung tapi tidak pernah dipakai (dead code).
      Sekarang: jika tweet terdeteksi informatif DAN net == 0 (tidak ada
      sinyal sentimen eksplisit/pola apapun) → Netral langsung, sebelum
      model NB dikonsultasikan. Hanya net == 0 yang dipakai (bukan
      abs(net) <= 1) supaya tweet yang punya opini lemah tetap diberi
      kesempatan diproses Layer 2a/2b di bawah.

    Layer 0a — >>> FIX v5 (MASALAH 13, baru): Override Zero-Signal.
      Jika skor_pos == 0 DAN skor_neg == 0 (tidak ada sinyal lexicon
      ATAU pola apapun ditemukan sama sekali), langsung Netral. Model
      NB terbukti bias ke Positif untuk tweet yang hanya menyebut kata
      domain ('gratis ongkir', 'komdigi', dst.) tanpa kata sentimen
      apapun, sehingga jika tidak ada sinyal sama sekali, default paling
      aman adalah Netral, bukan menyerahkan ke model.

    Layer 0b — Override dominasi kata (selisih ≥2):
      Dua blok if independen yang sejajar (bug indentasi versi lama
      sudah diperbaiki di v3).

    Layer 1a — Override Positif KUAT (net >= 2)
    Layer 1b — Override Negatif KUAT (net <= -2)
    Layer 2a — Override Positif LEMAH (net == 1), konsultasi model
    Layer 2b — Override Negatif LEMAH (net == -1), konsultasi model
    Layer 3  — Fallback Model NB (dengan anti-bias)
    Layer 4  — Ultimate Fallback (model tidak tersedia)
    ─────────────────────────────────────────────────────────────────────
    Return: (label: str, confidence: float)
    """
    net        = skor["net"]
    skor_pos = skor["positif"]
    skor_neg = skor["negatif"]
    is_info    = skor.get("informatif", False)

    # ── Layer 0: Override Informatif (FIX v5 — MASALAH 12) ───────────────
    if is_info and net == 0:
        return ("Netral", 0.60)

    # ── Layer 0a: Override Zero-Signal (FIX v5 — MASALAH 13) ─────────────
    if skor_pos == 0 and skor_neg == 0:
        return ("Netral", 0.55)

    # ── Layer 0b: Override dominasi kata ──────────────────────────────────
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

        if label_norm == "Negatif" and net >= 0 and confidence < 0.65:
            corrected_conf = round(0.50 + max(0, confidence - 0.50) * 0.20, 3)
            return ("Netral", corrected_conf)

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