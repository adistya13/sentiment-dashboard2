import json
import os
import threading
import time
from datetime import datetime, timezone

from scraper_worker import scrape_once

AUTO_CRAWL_INTERVAL_HOURS = 0.083
NRT_INTERVAL_MINUTES = 5

LOG_FILE   = "auto_crawl_log.json"
STATE_FILE = "crawler_state.json"

# ── Lock agar tidak ada dua crawl berjalan bersamaan ──────────────
_crawl_lock = threading.Lock()

# ── Flag scheduler ────────────────────────────────────────────────
_scheduler_started = False
_scheduler_lock    = threading.Lock()

# ── Flag aktivasi NRT — harus True sebelum scheduler boleh jalan ──
# PENTING: Nilai awal selalu False. Tidak ada kode module-level
# yang boleh mengubah ini menjadi True secara otomatis.
_nrt_enabled     = False
_nrt_enable_lock = threading.Lock()

# ── Event untuk menghentikan scheduler secara bersih ──────────────
_scheduler_stop_event = threading.Event()


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
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "status":      status,
        "total_saved": total_saved,
        "error":       error,
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
        "is_running":           bool(is_running),
        "service_active":       bool(service_active),
        "updated_at":           now,
        "heartbeat_at":         now if service_active else previous_state.get("heartbeat_at"),
        "last_job_started_at":  previous_state.get("last_job_started_at"),
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
#  NRT ACTIVATION PERSISTENCE
# ═══════════════════════════════════════════════════════════

NRT_ACTIVATION_FILE = "nrt_activation.json"

def save_nrt_activation(activated: bool):
    """Simpan status aktivasi NRT ke file agar persist setelah refresh."""
    try:
        with open(NRT_ACTIVATION_FILE, "w") as f:
            json.dump({"activated": activated, "updated_at": datetime.now(timezone.utc).isoformat()}, f)
    except Exception as e:
        print(f"[crawler] Gagal menyimpan NRT activation: {e}")


def load_nrt_activation() -> bool:
    """Baca status aktivasi NRT dari file."""
    if not os.path.exists(NRT_ACTIVATION_FILE):
        return False
    try:
        with open(NRT_ACTIVATION_FILE, "r") as f:
            data = json.load(f)
            return bool(data.get("activated", False))
    except Exception:
        return False
    
# ═══════════════════════════════════════════════════════════
#  CORE JOB
# ═══════════════════════════════════════════════════════════

def auto_crawl_job():
    """
    Jalankan satu siklus crawling.
    Thread-safe: hanya satu crawl yang boleh berjalan pada satu waktu.
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
#  BACKGROUND SCHEDULER
# ═══════════════════════════════════════════════════════════

def _scheduler_loop():
    """
    Loop daemon thread. Crawl pertama langsung, lalu tiap NRT_INTERVAL_MINUTES.
    Berhenti bersih saat _scheduler_stop_event di-set.
    """
    print(f"[crawler] Scheduler dimulai — interval {NRT_INTERVAL_MINUTES} menit.")
    set_crawler_state(False, service_active=True)

    while not _scheduler_stop_event.is_set():
        auto_crawl_job()

        # Tunggu interval berikutnya sambil tulis heartbeat tiap 10 detik
        wait_until = time.time() + (NRT_INTERVAL_MINUTES * 60)
        while time.time() < wait_until and not _scheduler_stop_event.is_set():
            _write_heartbeat()
            time.sleep(min(10, max(1, wait_until - time.time())))

        if not _scheduler_stop_event.is_set():
            print(f"[crawler] Mulai crawl berikutnya...")

    # Bersihkan state saat loop selesai
    set_crawler_state(False, service_active=False)
    print("[crawler] Scheduler dihentikan.")


def _write_heartbeat():
    """Perbarui heartbeat_at tanpa mengubah field lain."""
    state = get_crawler_state()
    state["heartbeat_at"]   = datetime.now(timezone.utc).isoformat()
    state["service_active"] = True
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  ACTIVATION API  ← dipakai oleh crawling_page.py
# ═══════════════════════════════════════════════════════════

def is_nrt_enabled() -> bool:
    """Kembalikan True jika NRT sudah diaktifkan user."""
    return _nrt_enabled


def activate_nrt_scheduler():
    """
    Aktifkan NRT scheduler.
    Harus dipanggil HANYA dari tombol UI — tidak dari module-level manapun.
    Idempotent: aman dipanggil berkali-kali.
    """
    global _nrt_enabled

    with _nrt_enable_lock:
        _nrt_enabled = True
        
    save_nrt_activation(True)          # ← TAMBAH INI
    _scheduler_stop_event.clear()   # pastikan event tidak dalam kondisi set
    ensure_scheduler_running()
    print("[crawler] NRT diaktifkan oleh user.")


def deactivate_nrt_scheduler():
    """
    Hentikan NRT scheduler.
    Thread yang berjalan akan berhenti bersih pada iterasi berikutnya.
    """
    global _nrt_enabled, _scheduler_started

    with _nrt_enable_lock:
        _nrt_enabled = False

    save_nrt_activation(False)
    _scheduler_stop_event.set()     # sinyal ke thread agar berhenti

    with _scheduler_lock:
        _scheduler_started = False  # izinkan start ulang di masa depan

    set_crawler_state(False, service_active=False)
    print("[crawler] NRT dinonaktifkan oleh user.")


def ensure_scheduler_running():
    """
    Pastikan background scheduler sudah berjalan.
    HANYA berjalan jika _nrt_enabled = True (sudah diaktifkan user).
    Aman dipanggil berkali-kali (idempotent).

    JANGAN panggil fungsi ini dari module-level atau saat app startup.
    Panggil hanya setelah activate_nrt_scheduler() dipicu dari UI.
    """
    global _scheduler_started

    if not _nrt_enabled:
        # Belum diaktifkan user — jangan mulai thread apapun
        return

    with _scheduler_lock:
        if _scheduler_started:
            return

        _scheduler_stop_event.clear()
        t = threading.Thread(
            target=_scheduler_loop,
            name="CrawlerScheduler",
            daemon=True,
        )
        t.start()
        _scheduler_started = True
        print("[crawler] Background scheduler thread dimulai.")


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT (via terminal, opsional)
# ═══════════════════════════════════════════════════════════

def main():
    """Jalankan scheduler via terminal (run_scraper_loop.py)."""
    global _nrt_enabled
    _nrt_enabled = True          # mode terminal: langsung aktif

    print("Crawler realtime aktif (mode terminal).")
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