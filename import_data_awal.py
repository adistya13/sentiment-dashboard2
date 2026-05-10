import sqlite3
from datetime import datetime

import pandas as pd


DB_FILE = "data_sentimen_komdigi.db"
EXCEL_FILE = "hasil_prediksi_sentimen.xlsx"
TABLE_NAME = "tweets"


def get_value(row, possible_names, default=""):
    for name in possible_names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def parse_date(value):
    if pd.isna(value) or value == "":
        return datetime.now().isoformat()

    try:
        return pd.to_datetime(value).isoformat()
    except Exception:
        return str(value)


df = pd.read_excel(EXCEL_FILE)

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS tweets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT UNIQUE,
    text TEXT,
    created_at TEXT,
    crawled_at TEXT,
    crawl_type TEXT
)
""")

inserted = 0
skipped = 0

for index, row in df.iterrows():
    text = str(get_value(row, [
        "text",
        "full_text",
        "Isi Tweet",
        "tweet",
        "Tweet",
        "clean_text",
        "teks",
        "komentar"
    ])).strip()

    if not text or text.lower() == "nan":
        skipped += 1
        continue

    tweet_id = str(get_value(row, [
        "tweet_id",
        "id_str",
        "ID Tweet",
        "id",
        "Id"
    ], f"historis_{index}_{abs(hash(text))}"))

    created_at = parse_date(get_value(row, [
        "created_at",
        "Tanggal Tweet",
        "tanggal",
        "date",
        "Date",
        "waktu"
    ], datetime.now().isoformat()))

    crawled_at = parse_date(get_value(row, [
        "crawled_at",
        "Masuk Database"
    ], datetime.now().isoformat()))

    try:
        cur.execute("""
            INSERT OR IGNORE INTO tweets
            (tweet_id, text, created_at, crawled_at, crawl_type)
            VALUES (?, ?, ?, ?, ?)
        """, (
            tweet_id,
            text,
            created_at,
            crawled_at,
            "historis"
        ))

        if cur.rowcount > 0:
            inserted += 1
        else:
            skipped += 1

    except Exception as e:
        print("Gagal insert:", e)
        skipped += 1

conn.commit()
conn.close()

print("Import selesai.")
print("Berhasil masuk:", inserted)
print("Dilewati:", skipped)
