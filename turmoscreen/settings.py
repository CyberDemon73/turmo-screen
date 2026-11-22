"""Persistent JSON settings stored in the platform's config folder."""
import json
import os
import sys
from pathlib import Path


def config_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Turmo Screen"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Turmo Screen"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "turmoscreen"


def _legacy_settings():
    """Settings file from before the rename to Turmo Screen (the app was called SecScreen)."""
    new = config_dir()
    old = new.parent / ("secscreen" if new.name == "turmoscreen" else "SecScreen")
    return old / "settings.json"


DEFAULTS = {
    "port": "auto",
    "orientation": "reverse_landscape",
    "brightness": 60,
    "mode": "tokens",
    "autoconnect": True,
    "tray": True,
    "tray_hint_shown": False,
    "max_fps": 60,
    "refresh_minutes": 0,
    "picture": {},
    "night": {},
    "modes": {},
}


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "settings.json"
        self.data = json.loads(json.dumps(DEFAULTS))
        source = self.path
        if path is None and not self.path.exists() and _legacy_settings().exists():
            source = _legacy_settings()  # carry settings, tasks and playlists over from SecScreen
        try:
            with open(source, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass
        if source != self.path:
            self.save()

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def section(self, name):
        return self.data.setdefault("modes", {}).setdefault(name, {})

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass
