"""Launcher used by PyInstaller builds (python -m secscreen works too)."""
import sys

from secscreen.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
