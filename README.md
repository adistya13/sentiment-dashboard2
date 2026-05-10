# Sentiment Dashboard Komdigi

Dashboard analisis sentimen tweet terkait Komdigi dan isu ongkir menggunakan Streamlit. Aplikasi ini mendukung crawling tweet, penyimpanan data ke database lokal, preprocessing teks Bahasa Indonesia, prediksi sentimen dengan model Naive Bayes, serta visualisasi hasil secara interaktif.

## Fitur Utama

- Crawling tweet berdasarkan query yang dapat dikonfigurasi.
- Penyimpanan tweet ke database SQLite.
- Pencegahan duplikasi tweet berdasarkan `tweet_id`.
- Preprocessing teks: cleaning, normalisasi kata, stopword removal, dan stemming.
- Prediksi sentimen dengan model Naive Bayes dan TF-IDF.
- Visualisasi sentimen dalam bentuk metrik, chart, tabel, dan filter periode.
- Auto refresh dashboard ketika ada data baru.
- Dukungan zona waktu Indonesia: WIB, WITA, dan WIT.

## Tools dan Library

Project ini menggunakan beberapa tools dan library berikut:

| Tools/Library | Fungsi |
| --- | --- |
| Python | Bahasa utama untuk backend, preprocessing, prediksi, dan dashboard. |
| Streamlit | Framework untuk membuat dashboard web interaktif. |
| streamlit-autorefresh | Refresh halaman dashboard otomatis berdasarkan interval tertentu. |
| Pandas | Membaca, membersihkan, memfilter, dan mengolah data tweet. |
| NumPy | Operasi numerik pendukung proses prediksi. |
| Plotly | Membuat visualisasi interaktif seperti pie chart dan grafik lain. |
| Matplotlib | Pendukung visualisasi tambahan. |
| WordCloud | Membuat visualisasi kata dominan dari tweet. |
| scikit-learn | Library machine learning untuk model Naive Bayes dan TF-IDF. |
| Joblib | Memuat file model `.pkl` dan vectorizer `.pkl`. |
| Sastrawi | Stemming kata Bahasa Indonesia. |
| SQLite | Database lokal utama untuk menyimpan data tweet tanpa server tambahan. |
| SQLAlchemy | Engine koneksi database yang digunakan oleh Pandas dan modul aplikasi. |
| python-dotenv | Membaca konfigurasi rahasia dari file `.env`. |
| OpenPyXL | Membaca dan menulis file Excel `.xlsx`. |
| Playwright | Dependensi pendukung scraping/otomasi browser bila diperlukan. |
| PyMySQL | Dependensi opsional jika suatu saat database dipindahkan ke MySQL. |
| Node.js dan npx | Menjalankan package crawler tweet. |
| tweet-harvest | Tool crawling tweet yang dipanggil melalui `npx`. |
| Git dan GitHub | Version control dan penyimpanan repository online. |

## Struktur Project

```text
sentiment_dashboard2/
├── app.py
├── crawler.py
├── scraper_worker.py
├── database.py
├── sentiment_service.py
├── timezone_utils.py
├── import_data_awal.py
├── run_scraper_loop.py
├── requirements.txt
├── model_naive_bayes.pkl
├── tfidf_vectorizer.pkl
├── indonesian-stopwords-complete.txt
├── data_sentimen_komdigi.db
├── page_modules/
│   ├── crawling_page.py
│   ├── preprocessing_page.py
│   ├── sentiment_page.py
│   └── table_utils.py
└── tweets-data/
    └── file hasil crawling csv
```

## Penjelasan Kode

### `app.py`

File utama aplikasi Streamlit. File ini mengatur konfigurasi halaman, zona waktu pengguna, auto refresh dashboard, status crawler, styling tampilan, navigasi halaman, dan pemanggilan modul halaman dari folder `page_modules`.

### `database.py`

Mengatur koneksi dan operasi database SQLite. Fungsi penting di file ini:

- `init_db()` membuat tabel `tweets` jika belum ada.
- `save_tweets()` menyimpan hasil crawling ke database.
- `load_tweets()` membaca semua tweet dari database.
- `insert_tweets()` memasukkan data dari dataframe ke database.
- `get_existing_tweet_ids()` mengecek data duplikat.
- `get_latest_crawl_time()` mengambil waktu crawling terbaru.

## Database

Project ini menggunakan database SQL berbasis SQLite, yaitu file lokal:

```text
data_sentimen_komdigi.db
```

SQLite tetap termasuk database SQL, tetapi tidak membutuhkan server database terpisah. Karena itu project ini tidak perlu XAMPP, Apache, phpMyAdmin, atau MySQL untuk menjalankan versi saat ini.

Koneksi database dibuat di `database.py`:

```python
DB_PATH = os.getenv("DB_PATH", "data_sentimen_komdigi.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
```

Tabel utama yang digunakan adalah `tweets` dengan kolom:

| Kolom | Fungsi |
| --- | --- |
| `id` | Primary key auto increment. |
| `tweet_id` | ID unik tweet untuk mencegah duplikasi data. |
| `text` | Isi teks tweet. |
| `created_at` | Waktu tweet dibuat. |
| `crawled_at` | Waktu tweet berhasil diambil oleh crawler. |
| `crawl_type` | Jenis crawling, default `realtime`. |

Alur database:

1. `init_db()` membuat tabel `tweets` jika belum tersedia.
2. `scraper_worker.py` mengambil tweet dan mengubahnya menjadi data siap simpan.
3. `save_tweets()` menyimpan tweet baru ke SQLite.
4. Data yang sudah ada dicek melalui `get_existing_tweet_ids()` agar tidak masuk dua kali.
5. Halaman dashboard membaca data dari SQLite untuk preprocessing, prediksi sentimen, tabel, dan visualisasi.

Jika ingin memakai MySQL/XAMPP di masa depan, bagian koneksi di `database.py` perlu diubah dari SQLite ke connection string MySQL. Namun untuk repository ini, konfigurasi defaultnya adalah SQLite lokal.

### `crawler.py`

Mengatur proses crawling otomatis. File ini menyimpan state crawler ke `crawler_state.json` dan log crawling ke `auto_crawl_log.json`. Interval crawling realtime diatur melalui:

```python
NRT_INTERVAL_MINUTES = 5
```

Fungsi utama:

- `auto_crawl_job()` menjalankan satu siklus crawling.
- `main()` menjalankan crawler terus-menerus setiap beberapa menit.
- `get_crawler_state()` membaca status crawler.
- `get_auto_crawl_logs()` membaca riwayat crawling.

### `scraper_worker.py`

Berisi logika pengambilan data tweet. File ini menjalankan `tweet-harvest` melalui `npx`, membaca CSV hasil crawling, membersihkan data kosong, memfilter tweet berdasarkan rentang hari terbaru, menghapus duplikasi, lalu menyimpan tweet baru ke database.

Konfigurasi penting yang dibaca dari `.env`:

- `TWITTER_AUTH_TOKEN`
- `QUERY`
- `SCRAPE_LIMIT`
- `RECENT_DAYS`
- `APP_TIMEZONE`
- `SCRAPE_TABS`

### `page_modules/crawling_page.py`

Halaman Streamlit untuk monitoring dan kontrol crawling. Halaman ini menampilkan status crawler, riwayat crawling, countdown interval, data hasil crawl, dan kontrol untuk menjalankan proses crawl.

### `page_modules/preprocessing_page.py`

Halaman untuk menjelaskan dan menjalankan proses preprocessing teks. Tahapan yang digunakan:

1. Cleaning teks: menghapus URL, mention, hashtag, angka, tanda baca, dan karakter non-huruf.
2. Normalisasi kata tidak baku ke kata baku.
3. Stopword removal menggunakan daftar stopword Bahasa Indonesia.
4. Stemming menggunakan Sastrawi.

### `page_modules/sentiment_page.py`

Halaman analisis sentimen. File ini memuat model dan vectorizer:

```python
model = joblib.load("model_naive_bayes.pkl")
tfidf = joblib.load("tfidf_vectorizer.pkl")
```

Alur prediksi:

1. Tweet dibersihkan dan dipreprocessing.
2. Teks diubah menjadi fitur numerik menggunakan TF-IDF.
3. Model Naive Bayes memprediksi sentimen.
4. Hasil ditampilkan sebagai Positif, Netral, atau Negatif.

### `timezone_utils.py`

Mengatur konversi waktu ke zona waktu Indonesia. Aplikasi mendukung:

- WIB: `Asia/Jakarta`
- WITA: `Asia/Makassar`
- WIT: `Asia/Jayapura`

File ini membantu agar waktu tweet, waktu crawling, dan waktu dashboard tetap konsisten.

### `page_modules/table_utils.py`

Modul helper untuk menampilkan tabel dengan format yang konsisten di beberapa halaman dashboard.

## Alur Kerja Aplikasi

1. User membuka dashboard melalui Streamlit.
2. Aplikasi membaca konfigurasi dari `.env`.
3. Database SQLite diinisialisasi.
4. Crawler mengambil tweet menggunakan `tweet-harvest`.
5. Hasil crawling disimpan ke folder `tweets-data/` dalam bentuk CSV.
6. Data CSV dibaca, divalidasi, difilter, dan disimpan ke database.
7. Dashboard membaca data dari database.
8. Teks tweet dipreprocessing.
9. Model Naive Bayes memprediksi sentimen.
10. Hasil analisis ditampilkan dalam bentuk metrik, grafik, tabel, dan file unduhan.

## Instalasi

Pastikan Python dan Node.js sudah terinstall.

Clone repository:

```bash
git clone https://github.com/adistya13/sentiment-dashboard2.git
cd sentiment-dashboard2
```

Buat virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Install dependency Python:

```bash
pip install -r requirements.txt
```

Install browser Playwright jika dibutuhkan:

```bash
playwright install
```

## Konfigurasi `.env`

Buat file `.env` di root project. File ini tidak ikut diupload ke GitHub karena berisi token rahasia.

```env
TWITTER_AUTH_TOKEN=isi_token_twitter_kamu
QUERY=komdigi (ongkir OR "gratis ongkir" OR "free ongkir") OR "pembatasan gratis ongkir" OR "gratis ongkir dibatasi"
SCRAPE_LIMIT=50
RECENT_DAYS=2
APP_TIMEZONE=Asia/Makassar
SCRAPE_TABS=LATEST,TOP
DB_PATH=data_sentimen_komdigi.db
```

Catatan timezone:

- Tampilan waktu pada dashboard mengikuti timezone device/browser pengguna saat opsi **Ikuti timezone device** aktif.
- Jika timezone device berhasil terdeteksi, aplikasi akan menyesuaikan tampilan ke WIB, WITA, WIT, atau timezone valid dari browser.
- `APP_TIMEZONE` bukan timezone utama pengguna. Nilai ini digunakan sebagai fallback dan sebagai timezone sumber untuk data waktu yang tidak memiliki informasi timezone.

Keterangan:

- `TWITTER_AUTH_TOKEN`: token autentikasi Twitter/X untuk crawling.
- `QUERY`: kata kunci pencarian tweet.
- `SCRAPE_LIMIT`: jumlah maksimal tweet yang diambil per tab.
- `RECENT_DAYS`: rentang hari tweet yang dianggap realtime.
- `APP_TIMEZONE`: fallback timezone aplikasi dan timezone sumber untuk data waktu yang tidak memiliki info timezone.
- `SCRAPE_TABS`: tab pencarian yang digunakan, misalnya `LATEST`, `TOP`, atau keduanya.
- `DB_PATH`: lokasi file database SQLite.

## Menjalankan Dashboard

Jalankan aplikasi Streamlit:

```bash
streamlit run app.py
```

Biasanya dashboard akan terbuka di:

```text
http://localhost:8501
```

## Menjalankan Crawler

Untuk menjalankan crawler satu kali:

```bash
python scraper_worker.py
```

Untuk menjalankan crawler realtime terus-menerus:

```bash
python crawler.py
```

Crawler realtime akan berjalan sesuai interval yang diatur pada `crawler.py`.

## File yang Tidak Diupload ke GitHub

Beberapa file sengaja tidak diupload karena bersifat lokal atau rahasia:

- `.env`
- `venv/`
- `__pycache__/`
- `.DS_Store`
- `auto_crawl_log.json`
- `crawler_state.json`

Pengaturan ini ada di `.gitignore`.

## Update Repository ke GitHub

Setelah melakukan perubahan kode:

```bash
git add .
git commit -m "Update dokumentasi atau fitur"
git push
```

## Catatan

Model yang digunakan adalah model Naive Bayes yang sudah disimpan dalam `model_naive_bayes.pkl`, sedangkan fitur teks menggunakan `tfidf_vectorizer.pkl`. Jika model ingin diganti, pastikan nama file atau path pada `page_modules/sentiment_page.py` ikut disesuaikan.
