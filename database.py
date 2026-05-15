import os
import pymysql
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "mysql+pymysql://root:@localhost:3306/sentiment_komdigi")

# Daftarkan dialect pymysql agar SQLAlchemy bisa menggunakannya
pymysql.install_as_MySQLdb()

engine = create_engine(
    DB_PATH,
    echo=False,
    pool_recycle=3600,       # Reconnect otomatis setiap 1 jam (cegah timeout)
    pool_pre_ping=True,      # Cek koneksi sebelum pakai (penting untuk realtime)
)


def init_db():
    """Buat tabel tweets jika belum ada (kompatibel MySQL)."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tweets (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                tweet_id   VARCHAR(255) UNIQUE,
                text       LONGTEXT,
                created_at VARCHAR(50),
                crawled_at VARCHAR(50),
                crawl_type VARCHAR(50) DEFAULT 'realtime'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        conn.commit()


def save_tweets(data, crawl_type="realtime"):
    """Simpan daftar tweet ke MySQL. Lewati duplikat berdasarkan tweet_id."""
    init_db()

    saved = 0

    with engine.connect() as conn:
        for tweet in data:
            try:
                result = conn.execute(
                    text("""
                        INSERT IGNORE INTO tweets
                            (tweet_id, text, created_at, crawled_at, crawl_type)
                        VALUES
                            (:tweet_id, :text, :created_at, :crawled_at, :crawl_type)
                    """),
                    {
                        "tweet_id":   str(tweet.get("tweet_id", "")),
                        "text":       str(tweet.get("text", "")),
                        "created_at": str(tweet.get("created_at", "")),
                        "crawled_at": str(tweet.get("crawled_at", "")),
                        "crawl_type": crawl_type,
                    }
                )
                if result.rowcount > 0:
                    saved += 1

            except Exception as e:
                print("Gagal simpan tweet:", e)

        conn.commit()

    return saved


def load_tweets():
    """Baca semua tweet dari MySQL, urut dari yang terbaru."""
    init_db()

    df = pd.read_sql_query(
        "SELECT * FROM tweets ORDER BY created_at DESC",
        engine
    )

    return df


def insert_tweets(df):
    """Masukkan DataFrame ke database (dipakai saat import data historis CSV)."""
    data = []

    for _, row in df.iterrows():
        full_text = row.get("full_text", row.get("text", ""))

        data.append({
            "tweet_id":   row.get(
                "tweet_id",
                f"{row.get('username', '')}_{hash(full_text)}"
            ),
            "text":       full_text,
            "created_at": row.get("created_at", ""),
            "crawled_at": row.get("crawled_at", ""),
        })

    return save_tweets(data, "realtime")


def get_tweet_count():
    """Dapatkan jumlah tweet untuk cache invalidation."""
    init_db()

    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM tweets"))
        return result.scalar()


def get_existing_tweet_ids(tweet_ids):
    """Kembalikan set tweet_id yang sudah ada agar crawler bisa lewati duplikat."""
    ids = [str(tid) for tid in tweet_ids if str(tid).strip()]

    if not ids:
        return set()

    init_db()
    existing = set()

    with engine.connect() as conn:
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            placeholders = ", ".join([f":id{i}" for i in range(len(chunk))])
            params = {f"id{i}": v for i, v in enumerate(chunk)}

            rows = conn.execute(
                text(f"SELECT tweet_id FROM tweets WHERE tweet_id IN ({placeholders})"),
                params
            ).fetchall()

            existing.update(str(row[0]) for row in rows)

    return existing


def get_latest_crawl_time():
    """Dapatkan waktu crawl terakhir untuk deteksi data baru."""
    init_db()

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(crawled_at) AS latest_crawl FROM tweets")
        )
        row = result.fetchone()

    if row is None or row[0] is None:
        return None

    return row[0]


if __name__ == "__main__":
    init_db()
    print("Database MySQL berhasil diinisialisasi.")
    print("Total tweet:", get_tweet_count())