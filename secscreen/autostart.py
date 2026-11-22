"""Start SecScreen at login: Windows Run key, macOS LaunchAgent, Linux XDG autostart."""
import os
import plistlib
import sys
from pathlib import Path

NAME = "SecScreen"
LABEL = "app.secscreen.manager"


def command():
    """Argument list that launches the app hidden in the tray."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--hidden"]
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")  # no console window
    launcher = Path(__file__).resolve().parent.parent / "secscreen_app.py"
    return [str(exe), str(launcher), "--hidden"]


def _mac_plist():
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _linux_desktop():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "secscreen.desktop"


def is_enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, NAME)
                return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_plist().exists()
    return _linux_desktop().exists()


def set_enabled(enabled):
    cmd = command()
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, " ".join(f'"{c}"' if " " in c else c for c in cmd))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
    elif sys.platform == "darwin":
        p = _mac_plist()
        if enabled:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                plistlib.dump({"Label": LABEL, "ProgramArguments": cmd, "RunAtLoad": True}, f)
        elif p.exists():
            p.unlink()
    else:
        p = _linux_desktop()
        if enabled:
            p.parent.mkdir(parents=True, exist_ok=True)
            exec_line = " ".join(f'"{c}"' if " " in c else c for c in cmd)
            p.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec={exec_line}\n"
                         "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
        elif p.exists():
            p.unlink()
