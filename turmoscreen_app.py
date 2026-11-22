"""Launcher used by PyInstaller builds (python -m turmoscreen works too)."""
import sys

from turmoscreen.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
