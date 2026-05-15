import json
import os
import threading
import time
from datetime import datetime, timezone

from scraper_worker import scrape_once

AUTO_CRAWL_INTERVAL_HOURS = 0.083
NRT_INTERVAL_MINUTES = 5

LOG_FILE = "auto_crawl_log.json"
STATE_FILE = "crawler_state.json"

# ── Internal lock agar tidak ada dua crawl berjalan bersamaan ──
_crawl_lock = threading.Lock()

# ── Flag untuk scheduler background thread ──
_scheduler_started = False
_scheduler_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════
#  STATE & LOG HELPERS
# ═══════════════════════════════════════════════════════════

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
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(logs[:50], f, indent=2)
    except Exception as e:
        print(f"[crawler] Gagal menulis log: {e}")


def set_crawler_state(is_running=False, service_active=None):
    previous_state = get_crawler_state()
    now = datetime.now(timezone.utc).isoformat()

    if service_active is None:
        service_active = previous_state.get("service_active", False)

    state = {
        "is_running": bool(is_running),
        "service_active": bool(service_active),
        "updated_at": now,
        "heartbeat_at": now if service_active else previous_state.get("heartbeat_at"),
        "last_job_started_at": previous_state.get("last_job_started_at"),
        "last_job_finished_at": previous_state.get("last_job_finished_at"),
    }

    if is_running:
        state["last_job_started_at"] = now
    elif previous_state.get("is_running"):
        state["last_job_finished_at"] = now

    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[crawler] Gagal menulis state: {e}")


# ═══════════════════════════════════════════════════════════
#  CORE JOB
# ═══════════════════════════════════════════════════════════

def auto_crawl_job():
    """
    Jalankan satu siklus crawling.
    Thread-safe: hanya satu crawl yang boleh berjalan pada satu waktu.
    Bisa dipanggil dari tombol UI maupun scheduler otomatis.
    """
    if not _crawl_lock.acquire(blocking=False):
        print("[crawler] Crawl sedang berjalan, skip.")
        return 0

    print("=" * 50)
    print("CRAWLING MULAI:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 50)

    service_active = get_crawler_state().get("service_active", False)
    set_crawler_state(True, service_active=service_active)

    total = 0
    try:
        total = scrape_once(limit=int(os.getenv("SCRAPE_LIMIT", "50")))
        if total is None:
            total = 0

        save_auto_crawl_log(status="success", total_saved=total, error=None)
        print(f"[crawler] Selesai. {total} tweet baru tersimpan.")

    except Exception as e:
        save_auto_crawl_log(status="error", total_saved=0, error=str(e))
        print(f"[crawler] Error: {e}")

    finally:
        set_crawler_state(False, service_active=service_active)
        _crawl_lock.release()

    return total


# ═══════════════════════════════════════════════════════════
#  BACKGROUND SCHEDULER (dipakai Streamlit, tanpa terminal)
# ═══════════════════════════════════════════════════════════

def _scheduler_loop():
    """
    Loop yang berjalan di daemon thread.
    Crawling pertama langsung dijalankan, lalu setiap NRT_INTERVAL_MINUTES menit.
    """
    print(f"[crawler] Scheduler dimulai — interval {NRT_INTERVAL_MINUTES} menit.")
    set_crawler_state(False, service_active=True)

    while True:
        auto_crawl_job()

        # Tulis heartbeat setiap 30 detik selagi menunggu interval berikutnya
        wait_until = time.time() + (NRT_INTERVAL_MINUTES * 60)
        while time.time() < wait_until:
            # Heartbeat agar is_crawler_service_active() tetap True
            _write_heartbeat()
            time.sleep(min(30, max(1, wait_until - time.time())))

        print(f"[crawler] Interval berikutnya dalam {NRT_INTERVAL_MINUTES} menit...")


def _write_heartbeat():
    """Perbarui heartbeat_at tanpa mengubah field lain."""
    state = get_crawler_state()
    state["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    state["service_active"] = True
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def ensure_scheduler_running():
    """
    Pastikan background scheduler sudah berjalan.
    Aman dipanggil berkali-kali (idempotent).
    Dipanggil dari crawling_page.py saat halaman dirender.
    """
    global _scheduler_started

    with _scheduler_lock:
        if _scheduler_started:
            return

        t = threading.Thread(target=_scheduler_loop, name="CrawlerScheduler", daemon=True)
        t.start()
        _scheduler_started = True
        print("[crawler] Background scheduler thread dimulai.")


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT (tetap bisa dipakai via terminal jika mau)
# ═══════════════════════════════════════════════════════════

def main():
    """Jalankan scheduler via terminal (opsional, tidak wajib)."""
    print("Crawler realtime aktif.")
    print(f"Interval: {NRT_INTERVAL_MINUTES} menit")
    set_crawler_state(False, service_active=True)

    try:
        _scheduler_loop()
    except KeyboardInterrupt:
        print("Crawler dihentikan.")
    finally:
        set_crawler_state(False, service_active=False)


if __name__ == "__main__":
    main()