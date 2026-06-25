"""
splash_page.py
──────────────
Splash screen modern, full-viewport centered.
Hanya tampil SEKALI saat pertama kali sistem diakses (browser baru/tab baru).
Jika halaman di-refresh (F5), splash TIDAK akan muncul lagi — karena status
"sudah pernah splash" disimpan di URL query parameter, bukan di session_state.

⚠️ KENAPA TIDAK PAKAI session_state SAJA?
   session_state Streamlit terikat ke session koneksi, bukan ke browser/tab.
   Pada beberapa kondisi (reconnect websocket, refresh di beberapa environment
   hosting), session_state bisa ter-reset sehingga splash muncul lagi padahal
   user hanya refresh. query_params (di URL) tidak hilang saat refresh biasa,
   sehingga lebih andal untuk menandai "splash sudah pernah tampil".

🕐 PENGATURAN DURASI:
   _SPLASH_DURATION = 10   ← ganti angka ini (satuan: detik)
   Rekomendasi: 4–8 detik

📐 PENGATURAN TINGGI IFRAME:
   components.html(..., height=700 ...)   ← sesuaikan jika konten terpotong
"""

import time
import streamlit as st
import streamlit.components.v1 as components

_APP_NAME = "SentiTrack"

# ┌─────────────────────────────────────────┐
# │  ⏱  GANTI ANGKA INI UNTUK UBAH DURASI  │
# │     Satuan: detik  |  Rekomendasi: 4–8  │
_SPLASH_DURATION = 10
# └─────────────────────────────────────────┘

# Nama parameter URL yang dipakai sebagai "penanda" splash sudah tampil.
# Tidak perlu diubah, kecuali bentrok dengan query param lain di app kamu.
_SPLASH_FLAG_KEY = "splashed"


def _build_splash_html(duration: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

/* ── Full viewport centering — bekerja di semua resolusi ── */
html, body {{
  width: 100%; height: 100%;
  overflow: hidden;
}}
body {{
  font-family: 'Plus Jakarta Sans', sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}}

/* ── Background gradient ── */
.bg {{
  position: fixed; inset: 0; z-index: 0;
  background: linear-gradient(160deg, #eef4ff 0%, #f8faff 40%, #f0f7ff 70%, #eef4ff 100%);
  background-size: 300% 300%;
  animation: gradMove {duration * 3}s ease infinite;
}}
@keyframes gradMove {{
  0%   {{ background-position: 0% 50%; }}
  50%  {{ background-position: 100% 50%; }}
  100% {{ background-position: 0% 50%; }}
}}

/* ── Pola titik ── */
.dots {{
  position: fixed; inset: 0; z-index: 1; pointer-events: none;
  background-image: radial-gradient(rgba(59,130,246,0.07) 1.5px, transparent 1.5px);
  background-size: 26px 26px;
}}

/* ── Orb cahaya latar ── */
.orb {{
  position: fixed; border-radius: 50%; z-index: 1; pointer-events: none;
  will-change: transform;
}}
.orb-1 {{
  width: 480px; height: 480px;
  top: -180px; left: -120px;
  background: radial-gradient(circle, rgba(99,102,241,0.09) 0%, transparent 70%);
  animation: floatA 9s ease-in-out infinite;
}}
.orb-2 {{
  width: 380px; height: 380px;
  bottom: -120px; right: -80px;
  background: radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%);
  animation: floatB 11s ease-in-out infinite;
}}
@keyframes floatA {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(24px,-32px); }} }}
@keyframes floatB {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(-18px,26px); }} }}

/* ── Card utama ── */
.card {{
  position: relative; z-index: 10;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  border: 1.5px solid rgba(226,232,240,0.85);
  border-radius: 24px;
  padding: 2.5rem 2.75rem 2rem;
  width: calc(100% - 2.5rem);
  max-width: 520px;
  box-shadow:
    0 0 0 1px rgba(255,255,255,0.5) inset,
    0 8px 40px rgba(59,130,246,0.09),
    0 2px 12px rgba(15,23,42,0.06);
  animation: fadeUp 0.65s cubic-bezier(0.22,1,0.36,1) forwards;
  opacity: 0;
}}
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(22px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ── Header: logo + nama app ── */
.header {{
  display: flex; align-items: center; gap: 1rem;
  margin-bottom: 1.5rem;
}}
.logo {{
  width: 54px; height: 54px; flex-shrink: 0;
  background: linear-gradient(135deg, #3b6cf7 0%, #6366f1 100%);
  border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem;
  box-shadow: 0 8px 24px rgba(59,108,247,0.28);
  animation: pulse 2.5s ease-in-out infinite;
}}
@keyframes pulse {{
  0%,100% {{ box-shadow: 0 8px 24px rgba(59,108,247,0.28), 0 0 0 0 rgba(59,108,247,0.18); }}
  50%      {{ box-shadow: 0 10px 30px rgba(59,108,247,0.38), 0 0 0 10px rgba(59,108,247,0); }}
}}
.title {{
  font-size: 1.75rem; font-weight: 800; letter-spacing: -0.03em;
  background: linear-gradient(135deg, #1e3a8a 20%, #3b6cf7 60%, #6366f1 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; line-height: 1.1;
}}
.subtitle {{
  font-size: 0.65rem; color: #64748b; font-weight: 600;
  letter-spacing: 0.01em; margin-top: 4px; line-height: 1.45;
  max-width: 320px;
}}

/* ── Divider ── */
.divider {{
  height: 1px;
  background: linear-gradient(90deg, transparent, #e2e8f0 30%, #e2e8f0 70%, transparent);
  margin: 1.25rem 0;
}}

/* ── Topik penelitian ── */
.topic {{
  background: linear-gradient(135deg, #eff6ff, #eef2ff);
  border: 1.5px solid #c7d2fe;
  border-radius: 14px;
  padding: 0.9rem 1.1rem;
  margin-bottom: 1.25rem;
}}
.topic-label {{
  font-size: 0.6rem; font-weight: 800; color: #4f46e5;
  text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem;
}}
.topic-value {{
  font-size: 0.88rem; font-weight: 700; color: #1e3a8a; line-height: 1.5;
}}
.topic-sub {{
  font-size: 0.68rem; color: #6366f1; font-weight: 600; margin-top: 0.25rem;
}}

/* ── Info grid 2×2 ── */
.info-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
  margin-bottom: 1.25rem;
}}
.info-item {{
  background: #f8fafc;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  padding: 0.65rem 0.8rem;
  display: flex; align-items: flex-start; gap: 0.6rem;
  transition: border-color 0.2s;
}}
.info-item:hover {{ border-color: #c7d2fe; }}
.info-icon {{ font-size: 1rem; flex-shrink: 0; margin-top: 1px; }}
.info-text-label {{
  font-size: 0.58rem; font-weight: 700; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;
}}
.info-text-value {{
  font-size: 0.76rem; font-weight: 700; color: #0f172a; line-height: 1.35;
}}

/* ── Identitas mahasiswa ── */
.identity {{
  display: flex; align-items: center; justify-content: space-between;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 12px;
  padding: 0.65rem 0.9rem;
  margin-bottom: 1.25rem;
}}
.identity-left {{
  font-size: 0.72rem; color: #15803d; font-weight: 600; line-height: 1.6;
}}
.identity-right {{
  font-size: 0.66rem; color: #16a34a; font-weight: 700;
  background: white; border: 1px solid #86efac; border-radius: 8px;
  padding: 0.2rem 0.6rem; white-space: nowrap;
}}

/* ── Progress bar ── */
.progress-wrap {{
  height: 4px; background: #e2e8f0; border-radius: 99px; overflow: hidden;
  margin-bottom: 0.6rem;
}}
.progress-bar {{
  height: 100%;
  background: linear-gradient(90deg, #3b6cf7, #6366f1, #818cf8);
  border-radius: 99px;
  animation: progress {duration}s linear forwards;
  width: 0%;
}}
@keyframes progress {{ from {{ width: 0%; }} to {{ width: 100%; }} }}

.progress-footer {{
  display: flex; justify-content: space-between; align-items: center;
}}
.progress-label {{
  font-size: 0.68rem; color: #94a3b8; font-weight: 500; letter-spacing: 0.03em;
}}
.progress-source {{
  font-size: 0.63rem; color: #cbd5e1; font-weight: 500;
}}

/* ── Shimmer dots loading indicator ── */
.dots-loader {{
  display: flex; align-items: center; gap: 4px; margin-top: 0.2rem;
}}
.dots-loader span {{
  width: 5px; height: 5px; border-radius: 50%; background: #c7d2fe;
  animation: bounce 1.4s ease-in-out infinite;
}}
.dots-loader span:nth-child(2) {{ animation-delay: 0.18s; }}
.dots-loader span:nth-child(3) {{ animation-delay: 0.36s; }}
@keyframes bounce {{
  0%, 80%, 100% {{ transform: scale(0.75); opacity: 0.5; }}
  40%            {{ transform: scale(1.1);  opacity: 1;   }}
}}
</style>
</head>
<body>

<div class="bg"></div>
<div class="dots"></div>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>

<div class="card">

  <!-- ── Header ── -->
  <div class="header">
    <div class="logo">📊</div>
    <div>
      <div class="title">{_APP_NAME}</div>
      <div class="subtitle">Dashboard Monitoring Sentimen Netizen terhadap Kebijakan Pembatasan Gratis Ongkir</div>
    </div>
  </div>

  <div class="divider"></div>

  <!-- ── Topik penelitian ── -->
  <div class="topic">
    <div class="topic-label">📌 Topik Penelitian</div>
    <div class="topic-value">Perancangan dan Implementasi Dashboard Sentimen Netizen X terhadap Kebijakan Pembatasan Gratis Ongkir dengan Naive Bayes</div>
    <div class="topic-sub">Komdigi · Analisis Opini Publik di Platform X (Twitter)</div>
  </div>

  <!-- ── Info grid ── -->
  <div class="info-grid">
    <div class="info-item">
      <div class="info-icon">🤖</div>
      <div>
        <div class="info-text-label">Model</div>
        <div class="info-text-value">Naive Bayes</div>
      </div>
    </div>
    <div class="info-item">
      <div class="info-icon">📡</div>
      <div>
        <div class="info-text-label">Sumber Data</div>
        <div class="info-text-value">X Data Historis via Tweet Harvest &amp; Realtime</div>
      </div>
    </div>
    <div class="info-item">
      <div class="info-icon">🔤</div>
      <div>
        <div class="info-text-label">Preprocessing</div>
        <div class="info-text-value">Case Folding · Cleaning · Normalisasi · Stopword · Stemming</div>
      </div>
    </div>
    <div class="info-item">
      <div class="info-icon">📊</div>
      <div>
        <div class="info-text-label">Output</div>
        <div class="info-text-value">Dashboard Analisis Sentimen</div>
      </div>
    </div>
  </div>

  <!-- ── Identitas mahasiswa ── -->
  <div class="identity">
    <div class="identity-left">
      <strong style="color:#0f172a;">Nurizzati Adistya Putri</strong> · E31232465<br/>
      Politeknik Negeri Jember · Manajemen Informatika
    </div>
    <div class="identity-right">Tugas Akhir 2026</div>
  </div>

  <!-- ── Progress loading ── -->
  <div class="progress-wrap">
    <div class="progress-bar"></div>
  </div>
  <div class="progress-footer">
    <div>
      <div class="progress-label">Memuat dashboard…</div>
      <div class="dots-loader">
        <span></span><span></span><span></span>
      </div>
    </div>
    <div class="progress-source">Data: X (Twitter)</div>
  </div>

</div>

</body>
</html>"""


def maybe_show_splash() -> bool:
    """
    Tampilkan splash HANYA jika belum pernah tampil di browser ini.

    Mekanisme:
    - Saat splash ditampilkan untuk pertama kali, kita menambahkan
      query parameter ?splashed=1 ke URL via st.query_params.
    - Karena ini tersimpan di URL (bukan di session_state server),
      query parameter ini TETAP ADA saat halaman di-refresh (F5).
    - Jadi: refresh biasa -> splash TIDAK muncul lagi.
            buka tab/browser baru tanpa parameter itu -> splash muncul.
            klik tombol "reset splash" (lihat reset_splash()) -> splash
            akan muncul lagi di reload berikutnya.

    Return:
        True  -> splash baru saja ditampilkan (halaman akan rerun setelahnya)
        False -> splash dilewati (sudah pernah tampil sebelumnya)
    """
    # Cek apakah flag sudah ada di URL
    already_splashed = st.query_params.get(_SPLASH_FLAG_KEY) == "1"

    if already_splashed:
        return False

    # Sembunyikan semua elemen Streamlit selama splash
    st.markdown("""
    <style>
    #MainMenu, footer, header,
    [data-testid="stHeader"],
    [data-testid="stSidebar"],
    [data-testid="stToolbar"],
    [data-testid="collapsedControl"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stDeployButton {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }
    .main > div { padding: 0 !important; margin: 0 !important; }
    [data-testid="stMain"],
    [data-testid="stAppViewContainer"],
    .stApp, html, body {
        background: #f8faff !important;
        overflow: hidden !important;
    }
    iframe { border: none !important; display: block !important; }
    </style>
    """, unsafe_allow_html=True)

    # ┌───────────────────────────────────────────────────────┐
    # │  📐  TINGGI IFRAME (px)                               │
    # │  Naikkan jika card terpotong di layar kecil.          │
    # │  Rekomendasi: 650–750                                 │
    components.html(_build_splash_html(_SPLASH_DURATION), height=700, scrolling=False)
    # └───────────────────────────────────────────────────────┘

    # Tunggu sesuai durasi splash sebelum lanjut ke halaman utama
    time.sleep(_SPLASH_DURATION + 0.3)

    # Tandai di URL bahwa splash sudah pernah tampil.
    # Penanda ini bertahan walau halaman di-refresh (F5).
    st.query_params[_SPLASH_FLAG_KEY] = "1"

    st.rerun()

    return True


def reset_splash():
    """
    Opsional: panggil fungsi ini (misalnya dari tombol di sidebar)
    jika ingin memaksa splash muncul lagi di reload berikutnya.
    Contoh penggunaan:
        if st.sidebar.button("Tampilkan ulang splash"):
            reset_splash()
            st.rerun()
    """
    if _SPLASH_FLAG_KEY in st.query_params:
        del st.query_params[_SPLASH_FLAG_KEY]