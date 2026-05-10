import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data_sentimen_komdigi.db")

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tweets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT UNIQUE,
            text TEXT,
            created_at TEXT,
            crawled_at TEXT,
            crawl_type TEXT DEFAULT 'realtime'
        )
    """)

    conn.commit()
    conn.close()


def save_tweets(data, crawl_type="realtime"):
    init_db()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    saved = 0

    for tweet in data:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO tweets
                (tweet_id, text, created_at, crawled_at, crawl_type)
                VALUES (?, ?, ?, ?, ?)
            """, (
                str(tweet.get("tweet_id", "")),
                str(tweet.get("text", "")),
                str(tweet.get("created_at", "")),
                str(tweet.get("crawled_at", "")),
                crawl_type,
            ))

            if cursor.rowcount > 0:
                saved += 1

        except Exception as e:
            print("Gagal simpan tweet:", e)

    conn.commit()
    conn.close()

    return saved


def load_tweets():
    init_db()

    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT *
        FROM tweets
        ORDER BY created_at DESC
    """, conn)

    conn.close()

    return df


def insert_tweets(df):
    data = []

    for _, row in df.iterrows():
        full_text = row.get("full_text", row.get("text", ""))

        data.append({
            "tweet_id": row.get(
                "tweet_id",
                f"{row.get('username', '')}_{hash(full_text)}"
            ),
            "text": full_text,
            "created_at": row.get("created_at", ""),
            "crawled_at": row.get("crawled_at", ""),
        })

    return save_tweets(data, "realtime")


def get_tweet_count():
    """Dapatkan jumlah tweet terbaru dari database untuk cache invalidation"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tweets")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_existing_tweet_ids(tweet_ids):
    """Ambil tweet_id yang sudah ada agar crawler bisa melewati duplikat."""
    ids = [str(tweet_id) for tweet_id in tweet_ids if str(tweet_id).strip()]

    if not ids:
        return set()

    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    existing = set()

    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        placeholders = ",".join(["?"] * len(chunk))

        cursor.execute(
            f"SELECT tweet_id FROM tweets WHERE tweet_id IN ({placeholders})",
            chunk
        )

        existing.update(str(row[0]) for row in cursor.fetchall())

    conn.close()
    return existing


def get_latest_crawl_time():
    """Dapatkan waktu crawl terakhir untuk mendeteksi data baru"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT MAX(crawled_at) as latest_crawl
        FROM tweets
    """, conn)
    conn.close()
    
    if df.empty or df['latest_crawl'].isna().all():
        return None
    return df['latest_crawl'].iloc[0]


if __name__ == "__main__":
    init_db()
    print("Database berhasil dibuat.")
