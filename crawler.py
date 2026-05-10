import json
import os
import time
from datetime import datetime, timezone

from scraper_worker import scrape_once

AUTO_CRAWL_INTERVAL_HOURS = 0.083
NRT_INTERVAL_MINUTES = 5

LOG_FILE = "auto_crawl_log.json"
STATE_FILE = "crawler_state.json"


def get_crawler_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def get_auto_crawl_logs(limit=10):
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)[:limit]
    except Exception:
        return []


def save_auto_crawl_log(status="success", total_saved=0, error=None):
    logs = get_auto_crawl_logs(50)

    logs.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "total_saved": total_saved,
        "error": error,
    })

    with open(LOG_FILE, "w") as f:
        json.dump(logs[:50], f, indent=2)


def set_crawler_state(is_running=False, service_active=None):
    previous_state = get_crawler_state()
    now = datetime.now(timezone.utc).isoformat()

    if service_active is None:
        service_active = previous_state.get("service_active", False)

    state = {
        "is_running": bool(is_running),
        "service_active": bool(service_active),
        "updated_at": now,
        "heartbeat_at": now if service_active else None,
        "last_job_started_at": previous_state.get("last_job_started_at"),
        "last_job_finished_at": previous_state.get("last_job_finished_at"),
    }

    if is_running:
        state["last_job_started_at"] = now
    elif previous_state.get("is_running"):
        state["last_job_finished_at"] = now

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def auto_crawl_job():
    print("=" * 50)
    print("CRAWLING MULAI:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 50)

    service_active = get_crawler_state().get("service_active", False)
    set_crawler_state(True, service_active=service_active)

    try:
        total = scrape_once(
            limit=int(os.getenv("SCRAPE_LIMIT", "50"))
        )

        if total is None:
            total = 0

        save_auto_crawl_log(
            status="success",
            total_saved=total,
            error=None
        )

        print(f"Selesai. {total} tweet baru tersimpan.")

    except Exception as e:
        save_auto_crawl_log(
            status="error",
            total_saved=0,
            error=str(e)
        )

        print("Error crawler:", e)

    finally:
        set_crawler_state(False, service_active=service_active)


def main():
    print("Crawler realtime aktif.")
    print(f"Interval: {NRT_INTERVAL_MINUTES} menit")

    set_crawler_state(False, service_active=True)

    try:
        while True:
            auto_crawl_job()
            print(f"Menunggu {NRT_INTERVAL_MINUTES} menit...")

            wait_until = time.time() + (NRT_INTERVAL_MINUTES * 60)

            while time.time() < wait_until:
                set_crawler_state(False, service_active=True)
                time.sleep(min(30, max(1, wait_until - time.time())))

    except KeyboardInterrupt:
        print("Crawler dihentikan.")

    finally:
        set_crawler_state(False, service_active=False)


if __name__ == "__main__":
    main()
