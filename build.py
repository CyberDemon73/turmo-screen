"""Build a standalone app with PyInstaller.

  Windows: dist/TurmoScreen/TurmoScreen.exe
  macOS:   dist/Turmo Screen.app        (build on a Mac)
  Linux:   dist/TurmoScreen/TurmoScreen  (build on Linux)

Usage:  python build.py      (run inside the project's .venv)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_FILE_NAME = "Turmo Screen" if sys.platform == "darwin" else "TurmoScreen"


def main():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"])
    sys.path.insert(0, str(ROOT))
    from turmoscreen.draw import app_icon_image

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    if sys.platform == "win32":
        icon = build / "icon.ico"
        app_icon_image(256).save(icon, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                              (256, 256)])
    else:
        icon = build / "icon.png"  # PyInstaller turns it into .icns on macOS
        app_icon_image(1024).save(icon)

    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", APP_FILE_NAME, "--windowed", "--icon", str(icon),
        "--collect-submodules", "turmoscreen",
        str(ROOT / "turmoscreen_app.py"),
    ]
    if sys.platform == "darwin":
        args[5:5] = ["--osx-bundle-identifier", "app.turmoscreen.manager"]
    subprocess.check_call(args, cwd=ROOT)
    print("\nDone. Output is in", ROOT / "dist")


if __name__ == "__main__":
    main()
