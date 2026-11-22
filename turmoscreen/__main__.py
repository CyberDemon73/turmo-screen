"""Entry point: python -m turmoscreen"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="turmoscreen", description="Manager for 3.5\" USB smart screens")
    parser.add_argument("--hidden", action="store_true", help="start minimized to the tray")
    parser.add_argument("--render", metavar="DIR", help="render a preview PNG of every mode into DIR and exit")
    args = parser.parse_args()

    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .settings import Settings

    if sys.platform == "win32":
        # Give the app its own taskbar identity; otherwise Windows groups it under python.exe
        # and shows the Python logo instead of our icon.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TurmoScreen.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    if sys.platform != "darwin":
        app.setStyle("Fusion")
    from .gui import app_icon
    app.setWindowIcon(app_icon())

    from .modes import create_modes

    settings = Settings()
    modes = create_modes(settings)

    if args.render:
        return render_previews(modes, args.render)

    from .engine import Engine
    from .gui import MainWindow

    app.setQuitOnLastWindowClosed(False)
    engine = Engine(modes, settings)
    win = MainWindow(engine, modes, settings)
    app.setWindowIcon(win.windowIcon())
    engine.start()
    if settings["autoconnect"]:
        win.set_connected_ui(True)
        engine.connect_port(settings["port"])
    if not args.hidden:
        win.show()
    code = app.exec()
    engine.stop()
    return code


def render_previews(modes, out_dir):
    """Debug helper: save one frame of each mode as PNG."""
    import time
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for m in modes.values():
        m.activate()
    time.sleep(0.2)
    tokens = modes.get("tokens")
    if tokens is not None:
        deadline = time.time() + 120
        while not tokens.watcher.stats.loaded and time.time() < deadline:
            time.sleep(0.2)
    for mid, m in modes.items():
        m.render(time.time()).save(out / f"{mid}.png")
        print("saved", out / f"{mid}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
