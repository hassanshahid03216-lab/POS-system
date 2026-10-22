"""Settings store for shop info, hardware, and workflow preferences."""

import json
import os
from pathlib import Path

DEFAULT_SETTINGS = {
    "shop_name": "ShopFlow Super Store",
    "shop_phone": "+92 300 1234567",
    "shop_address": "Main Commercial Market",
    "receipt_footer": "Thank you for shopping with us!\nBika hua maal 3 din mein tabdeel ho sakta hai.",
    "printer_name": "",
    "sound_enabled": True,
    "auto_backup": True,
    "currency": "Rs",
    "last_external_backup_date": "",
    "backup_reminder_date": "",
}


def settings_path():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ShopFlowPOS"
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.json"


def load_settings():
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


ALLOWED_KEYS = set(DEFAULT_SETTINGS.keys()) | {"theme"}


def save_settings(values):
    path = settings_path()
    current = load_settings()
    # Whitelist allowed keys to prevent arbitrary payload injection/corruption
    sanitized = {k: v for k, v in values.items() if k in ALLOWED_KEYS}
    current.update(sanitized)
    
    # Atomic write to prevent settings file corruption during abrupt shutdowns
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
