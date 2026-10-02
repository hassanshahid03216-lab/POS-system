"""Audio feedback service for barcode scans, checkout dings, and alert beeps."""

import sys
import threading

def _beep_thread(freq, duration):
    try:
        import winsound
        winsound.Beep(freq, duration)
    except Exception:
        pass

def play_scan_beep():
    """Play a short, crisp high-pitch beep on successful barcode scan."""
    if sys.platform == "win32":
        t = threading.Thread(target=_beep_thread, args=(2400, 60), daemon=True)
        t.start()

def play_success_ding():
    """Play a pleasant double-chime ding upon successful checkout or transaction."""
    def _ding():
        try:
            import winsound
            winsound.Beep(1800, 80)
            winsound.Beep(2400, 140)
        except Exception:
            pass
    if sys.platform == "win32":
        threading.Thread(target=_ding, daemon=True).start()

def play_error_beep():
    """Play a low-frequency alert beep on error or out-of-stock."""
    if sys.platform == "win32":
        t = threading.Thread(target=_beep_thread, args=(600, 200), daemon=True)
        t.start()
