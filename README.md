<div align="center">

<img src="docs/images/logo.png" alt="SecScreen logo" width="128" height="128">

# SecScreen

**Turn a cheap 3.5â€³ USB smart screen into a live Claude Code dashboard, clock, to-do list, photo frame and more.**

A cross-platform desktop app with a proper window, live preview and tray icon â€”
for **Windows**, **macOS** and **Linux**.

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-supported-000000?logo=apple&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-supported-FCC624?logo=linux&logoColor=black)
![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt%206-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)

<img src="docs/images/hero.png" alt="SecScreen showing the Claude Code token dashboard and an analog clock" width="100%">

</div>

---

## Contents

- [Highlights](#highlights)
- [Display modes](#display-modes)
- [The app](#the-app)
- [Supported hardware](#supported-hardware)
- [Platform support](#platform-support)
- [Installation](#installation)
- [Usage](#usage)
- [Performance](#performance)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Adding your own mode](#adding-your-own-mode)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Highlights

- ðŸ§  **Live Claude Code token monitor** â€” today's usage, the 5-hour window, burn rate and a 7-day chart, read straight from Claude Code's local transcripts. An animated spark ripples while Claude is working.
- ðŸ–¥ï¸ **9 display modes** â€” Claude Tokens, Clock, Tasks, Photo, GIF, Timer, Stopwatch, System monitor and Message.
- ðŸ”„ **Landscape and portrait** â€” every mode has its own layout for both, plus flipped variants for any mounting position.
- âš¡ **Up to ~60 fps** â€” only the 8Ã—8 tiles that changed are sent to the screen, so small animations run smoothly on a slow USB link.
- ðŸŽ›ï¸ **Deep screen control** â€” brightness, power, warmth, contrast, saturation, grayscale, invert, mirror, frame-rate cap, freeze, periodic full refresh, night schedule and firmware reboot.
- ðŸªŸ **A real desktop app** â€” live preview, drag-and-drop photos and GIFs, tray / menu-bar icon, start at login, auto-reconnect when the screen is unplugged.
- ðŸŒ **Cross-platform** â€” one Python codebase for Windows, macOS and Linux, packaged as a native `.exe` / `.app` with PyInstaller.

---

## Display modes

<p align="center">
  <img src="docs/images/modes-landscape.png" alt="All display modes in landscape" width="100%">
</p>

| Mode | What it shows |
|---|---|
| âœ³ **Claude Tokens** | Tokens used today (input, output, cache write, cache read), messages, the current 5-hour window with time to reset, burn rate per minute and the last 7 days. The spark animates while Claude Code is working and breathes when idle. |
| ðŸ• **Clock** | An analog clock in the style of the macOS Clock widget with a smooth sweeping second hand, or a large lock-screen-style digital clock. Dark and light themes, 12/24-hour. |
| âœ… **Tasks** | A to-do list in the style of Apple Reminders â€” add tasks, tick them off, reorder by dragging, six accent colors, dark/light theme, progress counter. |
| ðŸ–¼ **Photo** | A single photo or a slideshow, cropped to fill or fitted on a blurred backdrop. |
| ðŸŽž **GIF** | Animated GIF / WebP / PNG playback with original frame timing, speed control and several GIFs in rotation. |
| â³ **Timer** | Countdown with a progress ring and presets. Flashes, beeps and sends a notification when time is up. |
| â± **Stopwatch** | Stopwatch with laps; fastest and slowest laps highlighted. |
| ðŸ“Š **System** | CPU, memory, network and disk usage with live graphs. |
| ðŸ’¬ **Message** | Your own text, auto-sized to fill the screen â€” "In a meeting", "Do not disturb"â€¦ |

### Live animation

<p align="center">
  <img src="docs/images/tokens-live.gif" alt="The Claude Tokens dashboard with the animated spark" width="540">
</p>

### Portrait

Every mode has a dedicated portrait layout â€” not a squeezed landscape one.

<p align="center">
  <img src="docs/images/modes-portrait.png" alt="Modes in portrait orientation" width="100%">
</p>

### Themes

<p align="center">
  <img src="docs/images/modes/clock.png" alt="Analog clock, dark theme" width="32%">
  <img src="docs/images/modes/clock_light.png" alt="Analog clock, light theme" width="32%">
  <img src="docs/images/modes/clock_digital.png" alt="Digital clock" width="32%">
</p>

---

## The app

A sidebar with the modes, a live preview of exactly what's on the screen, and the selected mode's settings.
The top bar connects to the screen (auto-detected) and controls brightness, orientation and power.

<p align="center">
  <img src="docs/images/app-tasks.png" alt="SecScreen app window â€” Tasks mode" width="100%">
</p>

The **âš™ Screen** page holds the deeper display controls:

<p align="center">
  <img src="docs/images/app-screen-settings.png" alt="SecScreen app window â€” Screen settings page" width="100%">
</p>

| Section | Options |
|---|---|
| **Picture** | Warmth, contrast, saturation, black & white, invert colors, mirror image |
| **Updates** | Max frame rate (1â€“60 fps), full refresh every N minutes, freeze screen, black screen, redraw now |
| **Night schedule** | Dim the screen or turn it off between two times |
| **Device** | Detected model, port, live data rate and fps, reboot screen |
| **App** | Start at login (tray only), keep running in the tray when closed, auto-connect on start |

Closing the window keeps SecScreen running in the system tray (menu bar on macOS); quit from the tray icon.
All settings, tasks and playlists are saved automatically.

---

## Supported hardware

SecScreen drives 3.5â€³ **"Turing" / "UsbMonitor" smart screens** that use the *revision A* serial protocol â€”
small 320Ã—480 IPS panels sold under many names as "PC case monitor", "AIDA64 sub-screen" or "Turing Smart Screen 3.5â€³".

| | |
|---|---|
| **USB ID** | `1a86:5722` (serial number `USB35INCHIPSV2`) |
| **Panel** | 3.5â€³ IPS, 320Ã—480, RGB565 |
| **Connection** | USB serial (CDC-ACM) â€” `COMx` on Windows, `/dev/cu.usbmodemâ€¦` on macOS, `/dev/ttyACM*` on Linux |
| **Detected models** | UsbMonitor 3.5â€³ (rev A) and Turing 3.5â€³ (rev A) |

No vendor software or driver is needed. Close the vendor's app first â€” only one program can use the port at a time.

---

## Platform support

| Platform | Status | Notes |
|---|---|---|
| **Windows 10 / 11** | âœ… Tested with hardware | Standalone `SecScreen.exe` via `build.py` |
| **macOS 11+** | ðŸŸ¡ Supported, not yet verified on hardware | Native window and menu-bar icon; `SecScreen.app` via `build.py` |
| **Linux** (X11 / Wayland) | ðŸŸ¡ Supported, not yet verified on hardware | Needs serial-port permission (see below) |

The GUI is Qt 6 (PySide6), so it uses each platform's native look, tray and notifications.
Fonts adapt automatically: Segoe UI on Windows, San Francisco on macOS, DejaVu / Noto on Linux.

---

## Installation

You need **Python 3.9 or newer**. The launch scripts create a local virtual environment and install the
dependencies ([`requirements.txt`](requirements.txt): PySide6, pyserial, Pillow, NumPy, psutil) on first run.

### Windows

```bat
git clone https://github.com/CyberDemon73/secscreen.git
cd secscreen
run.bat
```

### macOS

```bash
git clone https://github.com/CyberDemon73/secscreen.git
cd secscreen
chmod +x run.sh SecScreen.command
./run.sh            # or double-click SecScreen.command in Finder
```

### Linux

```bash
git clone https://github.com/CyberDemon73/secscreen.git
cd secscreen
chmod +x run.sh
./run.sh
```

Allow your user to open the screen (once):

```bash
sudo cp linux/99-secscreen.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

The rule also stops ModemManager from probing the device. If Qt reports a missing xcb plugin:
`sudo apt install libxcb-cursor0`.

### Manual setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python -m secscreen                  # add --hidden to start in the tray
```

### Build a standalone app

```bash
python build.py
```

| Platform | Output |
|---|---|
| Windows | `dist/SecScreen/SecScreen.exe` |
| macOS | `dist/SecScreen.app` (unsigned â€” open it the first time with right-click â†’ Open) |
| Linux | `dist/SecScreen/SecScreen` |

Build on the platform you're targeting.

---

## Usage

1. Plug in the screen and start SecScreen â€” it finds the screen and connects automatically.
2. Pick a mode in the sidebar. The preview shows exactly what's on the screen.
3. Adjust the mode's options below the preview; changes appear on the screen immediately.
4. Use the top bar for brightness, orientation (landscape, portrait, or either flipped) and power.
5. Open **âš™ Screen** for picture tuning, the night schedule, frame-rate cap and start-at-login.

**Tips**

- Drag photos or GIFs onto the preview to show them instantly â€” animated files open in GIF mode, still images in Photo mode.
- In **Tasks**: press Enter to add, tick to complete, double-click to edit, drag to reorder.
- The **Claude Tokens** mode reads `~/.claude/projects/**/*.jsonl` (respects `CLAUDE_CONFIG_DIR`). Nothing leaves your computer.
- Settings live in `%APPDATA%\SecScreen` (Windows), `~/Library/Application Support/SecScreen` (macOS) or `~/.config/secscreen` (Linux).

---

## Performance

The panel accepts about **220 KB/s** of pixel data regardless of how it is sent, so the frame rate depends on
how much of the picture changes. SecScreen compares each frame with what's already on the panel and sends only
the 8Ã—8 tiles that changed.

| What changes per frame | Max frame rate |
|---|---|
| ~10 tiles (a digit, a dot) | ~165 fps |
| 32Ã—32 px | ~108 fps |
| 64Ã—64 px | ~27 fps |
| Whole 480Ã—320 screen | ~0.7 fps |

Measured on real hardware:

| Mode | Frame rate | Data per frame |
|---|---|---|
| Claude Tokens (spark animating) | **~58 fps** | 1.8 KB |
| Clock (smooth second hand) | **~38 fps** | 3.3 KB |
| Stopwatch (running) | **~27 fps** | 6.8 KB |
| GIF | up to 60 fps for small moving areas; full-screen motion plays at a few fps | varies |

Animations are designed for the link: the Claude spark only moves 2â€“3 ray tips per frame, so it stays smooth.

---

## How it works

```mermaid
flowchart LR
    subgraph GUI["GUI thread (Qt)"]
        W[Main window<br/>sidebar Â· preview Â· settings]
    end
    subgraph Engine["Engine thread"]
        M[Active mode<br/>render â†’ 480Ã—320 image]
        P[Picture adjustments<br/>warmth Â· contrast Â· â€¦]
        D[Tile diff<br/>8Ã—8 blocks]
        S[Serial driver<br/>rotate Â· RGB565]
    end
    U[(Claude Code<br/>transcripts)] --> M
    W -- commands --> Engine
    M --> P --> D --> S -- USB serial --> SCR[3.5â€³ screen]
    P -- preview frame --> W
```

- **Rendering** â€” each mode returns a Pillow image at the orientation's logical size (480Ã—320 or 320Ã—480).
  Shapes are drawn supersampled for clean anti-aliasing.
- **Engine** â€” a single thread owns the serial port: it renders the active mode, applies the picture settings
  and night schedule, sends the frame and emits it to the preview.
- **Driver** ([`secscreen/device.py`](secscreen/device.py)) â€” converts to RGB565, rotates in software for the
  chosen orientation, diffs against the last frame and sends only changed tiles.
- **Protocol** â€” 6-byte commands (`DISPLAY_BITMAP`, brightness, on/off, reset, hello) followed by
  little-endian RGB565 pixels.

> **Protocol note.** The firmware reads each command from its own USB packet and discards anything else in that
> packet. A command must therefore always be a separate write; if it's joined with pixel data, the screen loses
> bytes, falls out of step and shows garbage until it is power-cycled.

---

## Project structure

```
secscreen/
â”œâ”€â”€ secscreen/                # the application package (python -m secscreen)
â”‚   â”œâ”€â”€ __main__.py           # entry point
â”‚   â”œâ”€â”€ gui.py                # main window, live preview, tray icon
â”‚   â”œâ”€â”€ screen_panel.py       # âš™ Screen page (picture, updates, night, device, app)
â”‚   â”œâ”€â”€ engine.py             # render loop thread, picture adjustments, night schedule
â”‚   â”œâ”€â”€ device.py             # serial driver: orientation, tile diff, commands
â”‚   â”œâ”€â”€ usage.py              # Claude Code usage reader
â”‚   â”œâ”€â”€ autostart.py          # start at login (Windows / macOS / Linux)
â”‚   â”œâ”€â”€ settings.py           # JSON settings in the platform config folder
â”‚   â”œâ”€â”€ draw.py, fonts.py     # drawing helpers, app icon, cross-platform fonts
â”‚   â””â”€â”€ modes/                # one file per display mode
â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ images/               # README images
â”‚   â””â”€â”€ make_screenshots.py   # regenerates the images from demo data
â”œâ”€â”€ linux/99-secscreen.rules  # udev rule for serial access
â”œâ”€â”€ legacy/windows-powershell # the original PowerShell/C# prototypes
â”œâ”€â”€ build.py                  # PyInstaller build (.exe / .app)
â”œâ”€â”€ run.bat Â· run.sh Â· SecScreen.command
â””â”€â”€ requirements.txt
```

---

## Adding your own mode

A mode is a small class: `render()` returns an image, `build_settings()` returns its Qt panel.

```python
# secscreen/modes/hello.py
from PIL import Image, ImageDraw
from ..fonts import font
from .base import Mode, panel


class HelloMode(Mode):
    id = "hello"
    name = "Hello"
    icon = "ðŸ‘‹"
    description = "A minimal example mode."
    DEFAULTS = {"name": "world"}

    def fps(self):
        return 1.0                      # how often to redraw

    def render(self, now):
        w, h = self.size                # 480Ã—320 or 320Ã—480
        img = Image.new("RGB", (w, h), (20, 20, 24))
        ImageDraw.Draw(img).text((w / 2, h / 2), f"Hello, {self.cfg['name']}!",
                                 font=font(36, "bold"), fill="white", anchor="mm")
        return img

    def build_settings(self):
        widget, form = panel(self)
        return widget
```

Register it in [`secscreen/modes/__init__.py`](secscreen/modes/__init__.py) by adding `HelloMode` to `MODE_CLASSES`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **"COMx is busy or not permitted"** | Another program holds the port â€” close the vendor's app (or a second SecScreen). On Linux install the udev rule. |
| **Screen not found** | Re-plug it and press âŸ³ next to the port list. Check it appears as `1a86:5722`. |
| **Garbled picture** | Use **âš™ Screen â†’ Reboot screen**, or unplug and re-plug. Setting *Full refresh every* to a few minutes also clears leftovers. |
| **Animation is slow** | Expected for full-screen motion â€” see [Performance](#performance). Use GIF *Fit* or *Original size* scaling. |
| **Taskbar shows the Python icon** | Unpin and re-pin the app; Windows caches icons. |
| **No token data** | Claude Code must have run on this computer; check the folder shown in the Claude Tokens panel. |

---

## License

Released under the [MIT License](LICENSE).

---

## Acknowledgements

- The revision A serial protocol is the one used by the open-source
  [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python) project, which
  documents these screens in depth.
- Built with [PySide6](https://doc.qt.io/qtforpython-6/), [Pillow](https://python-pillow.org/),
  [pyserial](https://github.com/pyserial/pyserial), [NumPy](https://numpy.org/) and [psutil](https://github.com/giampaolo/psutil).

*SecScreen is an independent project. It is not affiliated with or endorsed by Anthropic, Apple or the screen's
manufacturers. "Claude" and "Claude Code" are trademarks of Anthropic.*
