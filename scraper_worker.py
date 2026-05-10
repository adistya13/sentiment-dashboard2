import os
import glob
import hashlib
import subprocess
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.errors import EmptyDataError
from dotenv import load_dotenv

from database import save_tweets, init_db, get_existing_tweet_ids

load_dotenv()

AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN")

QUERY = os.getenv(
    "QUERY",
    'komdigi (ongkir OR "gratis ongkir" OR "free ongkir") OR "pembatasan gratis ongkir" OR "gratis ongkir dibatasi"'
)

SCRAPE_LIMIT = int(
    os.getenv("SCRAPE_LIMIT", "50")
)

RECENT_DAYS = int(
    os.getenv("RECENT_DAYS", "2")
)

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Makassar")

SCRAPE_TABS = [
    tab.strip().upper()
    for tab in os.getenv("SCRAPE_TABS", "LATEST,TOP").split(",")
    if tab.strip()
]


def get_recent_window():
    today = datetime.now(ZoneInfo(APP_TIMEZONE)).date()
    since_day = today - timedelta(days=max(RECENT_DAYS - 1, 0))
    until_day = today + timedelta(days=1)

    return since_day, until_day


def build_recent_query():
    query_lower = f" {QUERY.lower()}"

    if " since:" in query_lower or " until:" in query_lower:
        return QUERY

    since_day, until_day = get_recent_window()

    return f"({QUERY}) since:{since_day.isoformat()} until:{until_day.isoformat()}"


def normalize_tweet_date(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)

    if pd.isna(parsed):
        # Selalu gunakan UTC timezone untuk konsistensi
        return datetime.now(timezone.utc).isoformat()

    return parsed.isoformat()


def is_in_recent_window(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)

    if pd.isna(parsed):
        return False

    try:
        local_dt = parsed.tz_convert(APP_TIMEZONE)
    except Exception:
        local_dt = parsed

    since_day, until_day = get_recent_window()
    tweet_day = local_dt.date()

    return since_day <= tweet_day < until_day


def stable_fallback_id(row, full_text):
    username = str(row.get("username", "") or "unknown").strip() or "unknown"
    digest = hashlib.sha1(
        full_text.encode("utf-8", errors="ignore")
    ).hexdigest()[:16]

    return f"{username}_{digest}"


def extract_tweet_id(row, full_text):
    for column in ("id_str", "tweet_id", "id"):
        value = row.get(column)

        if pd.notna(value) and str(value).strip():
            return str(value).strip()

    return stable_fallback_id(row, full_text)


def is_header_like_row(row, tweet_id, full_text):
    text = str(full_text or "").strip().lower()
    tweet_id_text = str(tweet_id or "").strip().lower()
    created_at = str(row.get("created_at", "") or "").strip().lower()

    header_values = {
        "full_text",
        "text",
        "id_str",
        "tweet_id",
        "created_at",
        "conversation_id_str",
    }

    return (
        text in header_values
        or tweet_id_text in header_values
        or created_at == "created_at"
    )


def ambil_file_csv_terbaru(min_mtime=None, output_name=None):
    if output_name:
        output_path = os.path.join("tweets-data", output_name)
        root, ext = os.path.splitext(output_path)
        files = [
            path for path in (
                output_path,
                f"{root}.old{ext}",
            )
            if os.path.exists(path)
        ]
    else:
        files = glob.glob("tweets-data/*.csv")

    if not files:
        return None

    if min_mtime is not None:
        files = [
            path for path in files
            if os.path.getmtime(path) >= min_mtime
        ]

    if not files:
        return None

    non_empty_files = [
        path for path in files
        if os.path.getsize(path) > 2
    ]

    if non_empty_files:
        files = non_empty_files

    return max(
        files,
        key=os.path.getmtime
    )


def scrape_tab(tab, effective_query, limit):
    output_name = f"hasil_{tab.lower()}.csv"
    started_at = time.time() - 1

    command = [
        "npx",
        "--yes",
        "tweet-harvest@2.6.1",
        "-o",
        output_name,
        "-s",
        effective_query,
        "--tab",
        tab,
        "-l",
        str(limit),
        "--token",
        AUTH_TOKEN,
    ]

    print(f"Scraping tab {tab}...")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"tweet-harvest tab {tab} timed out after 180 seconds")
        raise RuntimeError(
            f"tweet-harvest tab {tab} timed out (likely no results atau network issue)"
        )

    if result.returncode != 0:
        error_msg = result.stderr if result.stderr else result.stdout
        print(f"tweet-harvest stderr: {error_msg}")
        raise RuntimeError(
            f"tweet-harvest tab {tab} gagal dengan exit code {result.returncode}: {error_msg}"
        )

    latest_file = ambil_file_csv_terbaru(started_at, output_name)

    if latest_file is None:
        print(f"CSV baru untuk tab {tab} tidak ditemukan")
        return pd.DataFrame()

    # Cek ukuran file sebelum membaca
    try:
        file_size = os.path.getsize(latest_file)
        if file_size <= 2:
            print(f"CSV tab {tab} kosong atau tidak valid (ukuran: {file_size} bytes)")
            return pd.DataFrame()
    except Exception as e:
        print(f"Gagal memeriksa ukuran file {latest_file}: {e}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(latest_file)
    except EmptyDataError as e:
        print(f"CSV tab {tab} kosong atau tidak valid: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Gagal membaca CSV tab {tab}: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"Data tab {tab} kosong")
        return pd.DataFrame()

    if "full_text" not in df.columns:
        print(f"Kolom full_text tidak ditemukan pada tab {tab}")
        print(df.columns.tolist())
        return pd.DataFrame()

    df["_source_tab"] = tab
    return df


def scrape_once(limit=SCRAPE_LIMIT):
    init_db()

    if not AUTH_TOKEN:
        raise ValueError(
            "TWITTER_AUTH_TOKEN belum diisi di file .env"
        )

    effective_query = build_recent_query()
    tabs = SCRAPE_TABS or ["LATEST"]

    print("Scraping tweet realtime...")
    print("Query:", effective_query)
    print("Tab:", ", ".join(tabs))

    frames = []
    errors = []

    for tab in tabs:
        try:
            tab_df = scrape_tab(tab, effective_query, limit)
        except Exception as e:
            errors.append(f"{tab}: {e}")
            print(f"Tab {tab} gagal:", e)
            continue

        if not tab_df.empty:
            frames.append(tab_df)

    if not frames:
        # Jika tidak ada data baru dari scraper, kembalikan 0 daripada error
        # Ini normal jika tidak ada tweet baru yang sesuai kriteria
        if errors:
            print("Warning - Scrape failed with errors:", " | ".join(errors))
        else:
            print("No new data found in twitter search")
        return 0

    df = pd.concat(frames, ignore_index=True)
    print(f"Total hasil mentah dari crawler: {len(df)} tweet")

    df["_full_text_clean"] = df["full_text"].fillna("").astype(str)
    df = df[df["_full_text_clean"].str.strip().ne("")].copy()

    data = []
    outside_window = 0

    for _, row in df.iterrows():
        full_text = str(row.get("_full_text_clean", ""))
        tweet_id = extract_tweet_id(row, full_text)

        if is_header_like_row(row, tweet_id, full_text):
            continue

        created_at = normalize_tweet_date(
            row.get("created_at", datetime.now().isoformat())
        )

        if not is_in_recent_window(created_at):
            outside_window += 1
            continue

        data.append({
            "tweet_id": tweet_id,
            "text": full_text,
            "created_at": created_at,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        })

    if outside_window:
        print(
            f"{outside_window} tweet dilewati karena di luar rentang realtime"
        )

    before_dedupe = len(data)
    deduped = {}

    for tweet in data:
        deduped.setdefault(tweet["tweet_id"], tweet)

    data = list(deduped.values())
    duplicate_between_tabs = before_dedupe - len(data)

    if duplicate_between_tabs:
        print(
            f"{duplicate_between_tabs} tweet duplikat dari LATEST/TOP dilewati"
        )

    if not data:
        print("Tidak ada tweet hari ini yang bisa disimpan")
        return 0

    existing_ids = get_existing_tweet_ids(
        [tweet["tweet_id"] for tweet in data]
    )

    new_data = [
        tweet for tweet in data
        if tweet["tweet_id"] not in existing_ids
    ]

    skipped = len(data) - len(new_data)

    if skipped:
        print(f"{skipped} tweet dilewati karena sudah ada di database")

    if not new_data:
        print("Tidak ada tweet baru untuk disimpan")
        return 0

    saved = save_tweets(
        new_data,
        "realtime"
    )

    print(
        f"{saved} tweet baru berhasil disimpan"
    )

    return saved


if __name__ == "__main__":
    scrape_once()
