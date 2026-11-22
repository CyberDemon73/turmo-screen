"""Reads Claude Code token usage from its local transcripts (~/.claude/projects/**/*.jsonl)."""
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


def default_roots():
    cands = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        cands += [Path(p) / "projects" for p in env.split(os.pathsep) if p]
    cands.append(Path.home() / ".claude" / "projects")
    cands.append(Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude" / "projects")
    seen, out = set(), []
    for c in cands:
        if c.is_dir() and c.resolve() not in seen:
            seen.add(c.resolve())
            out.append(c)
    return out


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class UsageStore:
    def __init__(self, roots=None):
        self.roots = roots if roots is not None else default_roots()
        self._offsets = {}
        self._by_id = {}
        self.entries = []  # sorted list of (ts, in, out, cache_write, cache_read, model)

    def poll(self):
        changed = False
        for root in self.roots:
            try:
                files = list(root.rglob("*.jsonl"))
            except OSError:
                continue
            for f in files:
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                off = self._offsets.get(f, 0)
                if size < off:
                    off = 0
                if size == off:
                    continue
                try:
                    with open(f, "rb") as fh:
                        fh.seek(off)
                        data = fh.read(size - off)
                except OSError:
                    continue
                last = data.rfind(b"\n")
                if last < 0:
                    continue
                self._offsets[f] = off + last + 1
                for line in data[:last].split(b"\n"):
                    if b'"usage"' in line and b'"assistant"' in line and self._line(line):
                        changed = True
        if changed:
            self.entries = sorted(self._by_id.values())
        return changed

    def _line(self, line):
        try:
            obj = json.loads(line)
        except ValueError:
            return False
        if obj.get("type") != "assistant":
            return False
        msg = obj.get("message") or {}
        usage = msg.get("usage")
        mid = msg.get("id")
        model = msg.get("model") or ""
        if not usage or not mid or model == "<synthetic>":
            return False
        ts = _parse_ts(obj.get("timestamp", ""))
        if ts is None:
            return False
        e = (ts, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0),
             int(usage.get("cache_creation_input_tokens") or 0), int(usage.get("cache_read_input_tokens") or 0),
             model)
        prev = self._by_id.get(mid)
        if prev is not None and sum(prev[1:5]) >= sum(e[1:5]):
            return False
        self._by_id[mid] = e
        return True


@dataclass
class Stats:
    t_in: int = 0
    t_out: int = 0
    t_cw: int = 0
    t_cr: int = 0
    t_msgs: int = 0
    block_tokens: int = 0
    block_end: float = 0.0
    block_active: bool = False
    burn_per_min: float = 0.0
    last_context: int = 0
    model: str = ""
    last_time: float = 0.0
    days: list = field(default_factory=lambda: [0] * 7)
    day_names: list = field(default_factory=lambda: [""] * 7)
    loaded: bool = False

    @property
    def today(self):
        return self.t_in + self.t_out + self.t_cw + self.t_cr

    def active(self, now):
        return self.last_time > 0 and now - self.last_time < 45


def compute(entries, now):
    s = Stats(loaded=True)
    today = datetime.fromtimestamp(now).date()
    s.day_names = [(today - timedelta(days=6 - i)).strftime("%a")[:2] for i in range(7)]
    block_start = None
    last = 0.0
    bt = 0
    burn = 0
    burn_from = now - 15 * 60
    for ts, i, o, cw, cr, model in entries:
        total = i + o + cw + cr
        d = datetime.fromtimestamp(ts).date()
        di = 6 - (today - d).days
        if 0 <= di <= 6:
            s.days[di] += total
        if d == today:
            s.t_in += i
            s.t_out += o
            s.t_cw += cw
            s.t_cr += cr
            s.t_msgs += 1
        if block_start is None or ts >= block_start + 5 * 3600 or ts - last >= 5 * 3600:
            block_start = ts - ts % 3600  # floor to the UTC hour
            bt = 0
        bt += total
        last = ts
        if ts >= burn_from:
            burn += total
    if entries:
        ts, i, o, cw, cr, model = entries[-1]
        s.last_time = ts
        s.last_context = i + cw + cr
        s.model = model
    if block_start is not None and now < block_start + 5 * 3600:
        s.block_active = True
        s.block_tokens = bt
        s.block_end = block_start + 5 * 3600
    s.burn_per_min = burn / 15.0
    return s


# ---------------------------------------------------------------- plan limits
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
LIMIT_LABELS = {
    "five_hour": "5-hour session",
    "seven_day": "Weekly · all models",
    "seven_day_opus": "Weekly · Opus",
    "seven_day_sonnet": "Weekly · Sonnet",
}


@dataclass
class Limit:
    key: str
    label: str
    percent: float
    resets_at: float  # epoch seconds, 0 if unknown


def _read_oauth():
    """Claude Code's own login (same source as its /usage screen). Returns (token, expires_epoch) or None."""
    import subprocess
    import sys
    raw = None
    if sys.platform == "darwin":
        try:
            raw = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                                 capture_output=True, text=True, timeout=5).stdout.strip() or None
        except Exception:
            raw = None
    if raw is None:
        bases = [Path(p) for p in os.environ.get("CLAUDE_CONFIG_DIR", "").split(os.pathsep) if p]
        bases.append(Path.home() / ".claude")
        for base in bases:
            p = base / ".credentials.json"
            if p.is_file():
                raw = p.read_text(encoding="utf-8")
                break
    if not raw:
        return None
    oauth = json.loads(raw).get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        return None
    return token, (oauth.get("expiresAt") or 0) / 1000


def fetch_limits(timeout=10):
    """Returns (limits, status). Never stores or logs the token, and never refreshes it."""
    import urllib.error
    import urllib.request
    try:
        creds = _read_oauth()
    except Exception:
        creds = None
    if creds is None:
        return [], "Not signed in to Claude Code with a Claude account"
    token, expires = creds
    if expires and expires < time.time():
        return [], "Login expired — open Claude Code once to refresh it"
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
        "User-Agent": "turmo-screen",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return [], "Login not accepted — open Claude Code once to refresh it"
        return [], f"Usage service error {e.code}"
    except Exception as e:
        return [], f"Offline ({type(e).__name__})"
    limits = []
    for key, val in data.items():
        if not isinstance(val, dict) or val.get("utilization") is None:
            continue
        resets = _parse_ts(val["resets_at"]) if val.get("resets_at") else None
        limits.append(Limit(key, LIMIT_LABELS.get(key, key.replace("_", " ").capitalize()),
                            float(val["utilization"]), resets or 0.0))
    order = list(LIMIT_LABELS)
    limits.sort(key=lambda l: order.index(l.key) if l.key in order else len(order))
    return limits, ("OK" if limits else "No limit data returned")


class LimitsWatcher:
    """Refreshes plan limits in the background every 2 minutes."""

    def __init__(self, interval=120):
        self.interval = interval
        self.limits = []
        self.status = "Not checked yet"
        self.updated = 0.0
        self.enabled = True
        self._thread = None
        self._wake = threading.Event()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="limits", daemon=True)
            self._thread.start()

    def refresh_now(self):
        self._wake.set()

    def get(self, key):
        for l in self.limits:
            if l.key == key:
                return l
        return None

    def _run(self):
        while True:
            if self.enabled:
                limits, status = fetch_limits()
                if limits or not self.limits:
                    self.limits = limits
                self.status = status
                self.updated = time.time()
            else:
                self.status = "Turned off"
            self._wake.wait(self.interval)
            self._wake.clear()


class UsageWatcher:
    """Background thread keeping fresh Stats (polls every second)."""

    def __init__(self, interval=1.0):
        self.interval = interval
        self.store = UsageStore()
        self.stats = Stats()
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="usage", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.store.poll()
                self.stats = compute(self.store.entries, time.time())
            except Exception:
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
