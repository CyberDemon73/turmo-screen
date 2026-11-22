// Claude Code token monitor for a 3.5" Turing-style USB screen (rev A protocol, 320x480).
// Reads usage from ~/.claude/projects/**/*.jsonl incrementally and renders a dashboard
// with an animated Claude-style spark. C# 5 compatible (compiled by Windows PowerShell Add-Type).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Globalization;
using System.IO;
using System.IO.Ports;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace ClaudeScreen
{
    public struct UsageEntry
    {
        public DateTime Time;   // UTC
        public long In, Out, CW, CR;
        public string Model;
        public long Total { get { return In + Out + CW + CR; } }
    }

    public class UsageStore
    {
        readonly string root;
        readonly Dictionary<string, long> offsets = new Dictionary<string, long>();
        readonly Dictionary<string, UsageEntry> byId = new Dictionary<string, UsageEntry>();
        public List<UsageEntry> Entries = new List<UsageEntry>();
        static readonly Regex IdRx = new Regex("\"id\":\"(msg_[^\"]+)\"", RegexOptions.Compiled);
        static readonly Regex ModelRx = new Regex("\"model\":\"([^\"]+)\"", RegexOptions.Compiled);

        public UsageStore(string root) { this.root = root; }

        public bool Poll()
        {
            bool changed = false;
            if (!Directory.Exists(root)) return false;
            IEnumerable<string> files;
            try { files = Directory.EnumerateFiles(root, "*.jsonl", SearchOption.AllDirectories); }
            catch { return false; }
            foreach (string f in files)
            {
                long len;
                try { len = new FileInfo(f).Length; } catch { continue; }
                long off;
                offsets.TryGetValue(f, out off);
                if (len < off) off = 0;
                if (len == off) continue;
                try
                {
                    using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                    {
                        fs.Seek(off, SeekOrigin.Begin);
                        var buf = new byte[len - off];
                        int read = 0;
                        while (read < buf.Length)
                        {
                            int n = fs.Read(buf, read, buf.Length - read);
                            if (n <= 0) break;
                            read += n;
                        }
                        int start = 0;
                        for (int i = 0; i < read; i++)
                        {
                            if (buf[i] != 10) continue;
                            if (ProcessLine(Encoding.UTF8.GetString(buf, start, i - start))) changed = true;
                            start = i + 1;
                        }
                        offsets[f] = off + start;
                    }
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            if (changed)
            {
                Entries = new List<UsageEntry>(byId.Values);
                Entries.Sort((a, b) => a.Time.CompareTo(b.Time));
            }
            return changed;
        }

        static long Num(string s, string key)
        {
            int i = s.IndexOf(key, StringComparison.Ordinal);
            if (i < 0) return 0;
            i += key.Length;
            long v = 0;
            while (i < s.Length && s[i] >= '0' && s[i] <= '9') { v = v * 10 + (s[i] - '0'); i++; }
            return v;
        }

        bool ProcessLine(string line)
        {
            int u = line.LastIndexOf("\"usage\":{\"input_tokens\":", StringComparison.Ordinal);
            if (u < 0) return false;
            if (line.IndexOf("\"type\":\"assistant\"", StringComparison.Ordinal) < 0) return false;
            Match idm = IdRx.Match(line);
            if (!idm.Success) return false;
            Match mm = ModelRx.Match(line);
            string model = mm.Success ? mm.Groups[1].Value : "";
            if (model == "<synthetic>") return false;

            int ti = line.LastIndexOf("\"timestamp\":\"", StringComparison.Ordinal);
            if (ti < 0) return false;
            ti += 13;
            int te = line.IndexOf('"', ti);
            if (te < 0) return false;
            DateTime t;
            if (!DateTime.TryParse(line.Substring(ti, te - ti), CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out t)) return false;

            string seg = line.Substring(u, Math.Min(700, line.Length - u));
            var e = new UsageEntry();
            e.Time = t;
            e.Model = model;
            e.In = Num(seg, "\"input_tokens\":");
            e.CW = Num(seg, "\"cache_creation_input_tokens\":");
            e.CR = Num(seg, "\"cache_read_input_tokens\":");
            e.Out = Num(seg, "\"output_tokens\":");

            string key = idm.Groups[1].Value;
            UsageEntry prev;
            if (byId.TryGetValue(key, out prev) && prev.Total >= e.Total) return false;
            byId[key] = e;
            return true;
        }
    }

    public class Stats
    {
        public long TIn, TOut, TCW, TCR;
        public int TMsgs;
        public long BlockTokens;
        public DateTime BlockEnd; // UTC
        public bool BlockActive;
        public double BurnPerMin;
        public long LastContext;
        public string Model = "";
        public DateTime LastTime = DateTime.MinValue; // UTC
        public long[] Days = new long[7];
        public string[] DayNames = new string[7];
        public long Today { get { return TIn + TOut + TCW + TCR; } }

        public static Stats Compute(List<UsageEntry> entries, DateTime nowUtc)
        {
            var s = new Stats();
            DateTime today = nowUtc.ToLocalTime().Date;
            for (int d = 0; d < 7; d++) s.DayNames[d] = today.AddDays(d - 6).ToString("ddd", CultureInfo.InvariantCulture).Substring(0, 2);
            DateTime bs = DateTime.MinValue, last = DateTime.MinValue;
            long bt = 0, burn = 0;
            DateTime burnFrom = nowUtc.AddMinutes(-15);
            foreach (UsageEntry e in entries)
            {
                DateTime ld = e.Time.ToLocalTime().Date;
                int di = 6 - (int)(today - ld).TotalDays;
                if (di >= 0 && di <= 6) s.Days[di] += e.Total;
                if (ld == today) { s.TIn += e.In; s.TOut += e.Out; s.TCW += e.CW; s.TCR += e.CR; s.TMsgs++; }
                if (bs == DateTime.MinValue || e.Time >= bs.AddHours(5) || (e.Time - last).TotalHours >= 5)
                {
                    bs = new DateTime(e.Time.Year, e.Time.Month, e.Time.Day, e.Time.Hour, 0, 0, DateTimeKind.Utc);
                    bt = 0;
                }
                bt += e.Total;
                last = e.Time;
                if (e.Time >= burnFrom) burn += e.Total;
            }
            if (entries.Count > 0)
            {
                UsageEntry l = entries[entries.Count - 1];
                s.LastTime = l.Time;
                s.LastContext = l.In + l.CW + l.CR;
                s.Model = l.Model;
            }
            if (bs != DateTime.MinValue && nowUtc < bs.AddHours(5))
            {
                s.BlockActive = true;
                s.BlockTokens = bt;
                s.BlockEnd = bs.AddHours(5);
            }
            s.BurnPerMin = burn / 15.0;
            return s;
        }

        public string Signature(DateTime nowUtc)
        {
            return string.Join("|", new object[] { Today, TMsgs, BlockTokens, BlockActive, (long)BurnPerMin, LastContext, Model,
                string.Join(",", Days), nowUtc.ToLocalTime().ToString("HH:mm"), Monitor.IsActive(this, nowUtc) });
        }
    }

    public static class Render
    {
        // Logical canvas is landscape; Screen35 rotates it onto the 320x480 panel.
        public const int W = 480, H = 320;
        public static readonly Rectangle IconRect = new Rectangle(16, 8, 144, 144);
        public static readonly Rectangle LeftRect = new Rectangle(0, 152, 178, 168);
        public static readonly Rectangle RightRect = new Rectangle(178, 0, 302, 320);
        public static readonly Rectangle FullRect = new Rectangle(0, 0, W, H);

        static readonly Color Bg = Color.FromArgb(24, 24, 22);
        static readonly Color Panel = Color.FromArgb(44, 44, 40);
        static readonly Color Text = Color.FromArgb(245, 244, 238);
        static readonly Color Muted = Color.FromArgb(165, 162, 154);
        public static readonly Color Orange = Color.FromArgb(217, 119, 87);
        static readonly Color CIn = Color.FromArgb(106, 155, 204);
        static readonly Color CCW = Color.FromArgb(185, 162, 224);
        static readonly Color CCR = Color.FromArgb(127, 182, 133);

        static readonly Font FTitle = new Font("Segoe UI Semibold", 22f, GraphicsUnit.Pixel);
        static readonly Font FStatus = new Font("Segoe UI Semibold", 18f, GraphicsUnit.Pixel);
        static readonly Font FClock = new Font("Segoe UI", 38f, FontStyle.Bold, GraphicsUnit.Pixel);
        static readonly Font FDate = new Font("Segoe UI", 16f, GraphicsUnit.Pixel);
        static readonly Font FLabel = new Font("Segoe UI Semibold", 14f, GraphicsUnit.Pixel);
        static readonly Font FBig = new Font("Segoe UI", 56f, FontStyle.Bold, GraphicsUnit.Pixel);
        static readonly Font FRow = new Font("Segoe UI", 17f, GraphicsUnit.Pixel);
        static readonly Font FRowB = new Font("Segoe UI Semibold", 17f, GraphicsUnit.Pixel);
        static readonly Font FMid = new Font("Segoe UI", 28f, FontStyle.Bold, GraphicsUnit.Pixel);
        static readonly Font FSmall = new Font("Segoe UI", 14f, GraphicsUnit.Pixel);

        static readonly float[] RayLen = { 1.0f, 0.70f, 0.90f, 0.64f, 0.97f, 0.76f, 0.93f, 0.68f, 0.88f, 0.79f, 1.0f, 0.72f };
        static readonly float[] RayJit = { 0, 5, -4, 2, -5, 3, 0, -3, 4, -4, 2, -1 };

        public static string Fmt(long v)
        {
            CultureInfo ci = CultureInfo.InvariantCulture;
            if (v >= 1000000000L) return (v / 1e9).ToString("0.00", ci) + "B";
            if (v >= 1000000L) return (v / 1e6).ToString(v >= 100000000L ? "0" : "0.0", ci) + "M";
            if (v >= 1000L) return (v / 1e3).ToString(v >= 100000L ? "0" : "0.0", ci) + "K";
            return v.ToString(ci);
        }

        static void Prep(Graphics g)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        }

        public static void DrawIcon(Graphics g, double t, bool active)
        {
            Prep(g);
            Rectangle r = IconRect;
            using (var b = new SolidBrush(Bg)) g.FillRectangle(b, r);
            float cx = r.X + r.Width / 2f, cy = r.Y + r.Height / 2f;
            float R = r.Width * 0.40f;

            if (active)
            {
                const int a = 40;
                using (var path = new GraphicsPath())
                {
                    path.AddEllipse(cx - R * 1.2f, cy - R * 1.2f, R * 2.4f, R * 2.4f);
                    using (var pg = new PathGradientBrush(path))
                    {
                        pg.CenterColor = Color.FromArgb(a, Orange);
                        pg.SurroundColors = new[] { Color.FromArgb(0, Orange) };
                        g.FillPath(pg, path);
                    }
                }
            }

            // No rotation: pulsing in place keeps per-frame pixel changes (and USB traffic) small.
            const double spin = 0;
            using (var pen = new Pen(Orange, R * 0.17f))
            {
                pen.StartCap = LineCap.Round;
                pen.EndCap = LineCap.Round;
                for (int i = 0; i < 12; i++)
                {
                    double ang = (i * 30 + RayJit[i] + spin) * Math.PI / 180.0;
                    float pulse = active
                        ? 1f + 0.16f * (float)Math.Sin(t * 8 - i * (Math.PI / 6))
                        : 1f + 0.05f * (float)Math.Sin(t * 1.8 + i * 1.3);
                    float len = R * RayLen[i] * pulse;
                    float c = (float)Math.Cos(ang), s = (float)Math.Sin(ang);
                    g.DrawLine(pen, cx + c * R * 0.14f, cy + s * R * 0.14f, cx + c * len, cy + s * len);
                }
            }
        }

        static void Str(Graphics g, string s, Font f, Color c, float x, float y)
        {
            using (var b = new SolidBrush(c)) g.DrawString(s, f, b, x, y);
        }

        static void Right(Graphics g, string s, Font f, Color c, float right, float y)
        {
            using (var b = new SolidBrush(c))
            using (var sf = new StringFormat { Alignment = StringAlignment.Far })
                g.DrawString(s, f, b, new RectangleF(right - 300, y, 300, f.Height + 8), sf);
        }

        static void Center(Graphics g, string s, Font f, Color c, float x0, float x1, float y)
        {
            using (var b = new SolidBrush(c))
            using (var sf = new StringFormat { Alignment = StringAlignment.Center })
                g.DrawString(s, f, b, new RectangleF(x0, y, x1 - x0, f.Height + 8), sf);
        }

        static void RoundRect(Graphics g, Color c, float x, float y, float w, float h)
        {
            if (w <= 0) return;
            float rr = Math.Min(h, w);
            using (var p = new GraphicsPath())
            {
                p.AddArc(x, y, rr, h, 90, 180);
                p.AddArc(x + w - rr, y, rr, h, 270, 180);
                p.CloseFigure();
                using (var b = new SolidBrush(c)) g.FillPath(b, p);
            }
        }

        static string Span(TimeSpan ts)
        {
            if (ts.TotalMinutes < 1) return "<1m";
            if (ts.TotalHours < 1) return ((int)ts.TotalMinutes) + "m";
            return ((int)ts.TotalHours) + "h " + ts.Minutes.ToString("00") + "m";
        }

        public static void DrawStatic(Graphics g, Stats s, DateTime nowUtc)
        {
            Prep(g);
            g.Clear(Bg);
            DateTime now = nowUtc.ToLocalTime();
            bool active = Monitor.IsActive(s, nowUtc);
            CultureInfo ci = CultureInfo.InvariantCulture;

            // ---- Left column: (icon above) title, status, clock
            Center(g, "Claude Code", FTitle, Text, 0, 178, 154);
            string st = active ? "Working" : (s.LastTime == DateTime.MinValue ? "No data" : "Idle " + Span(nowUtc - s.LastTime));
            SizeF sz = g.MeasureString(st, FStatus);
            float sx = (178 - (sz.Width + 16)) / 2;
            using (var b = new SolidBrush(active ? Orange : Muted)) g.FillEllipse(b, sx, 192, 11, 11);
            Str(g, st, FStatus, active ? Text : Muted, sx + 15, 184);
            Center(g, now.ToString("HH:mm", ci), FClock, Text, 0, 178, 212);
            Center(g, now.ToString("ddd d MMM", ci), FDate, Muted, 0, 178, 260);
            string model = s.Model.StartsWith("claude-") ? s.Model.Substring(7) : s.Model;
            Center(g, model, FSmall, Muted, 0, 178, 290);

            using (var p = new Pen(Panel, 2)) g.DrawLine(p, 178, 14, 178, 306);

            // ---- Right column
            const float X = 194, XR = 468;
            Str(g, "TODAY", FLabel, Muted, X, 6);
            Right(g, s.TMsgs.ToString("N0", ci) + " msgs", FSmall, Muted, XR, 6);
            Str(g, Fmt(s.Today), FBig, Text, X - 6, 14);
            Right(g, "tokens", FRow, Muted, XR, 52);

            string[] names = { "Input", "Output", "Cache wr", "Cache rd" };
            long[] vals = { s.TIn, s.TOut, s.TCW, s.TCR };
            Color[] cols = { CIn, Orange, CCW, CCR };
            long tot = Math.Max(1, s.Today);
            for (int i = 0; i < 4; i++)
            {
                float y = 92 + i * 24;
                using (var b = new SolidBrush(cols[i])) g.FillEllipse(b, X, y + 8, 10, 10);
                Str(g, names[i], FRow, Text, X + 15, y);
                RoundRect(g, Panel, 300, y + 9, 96, 8);
                float frac = (float)vals[i] / tot;
                RoundRect(g, cols[i], 300, y + 9, vals[i] > 0 ? Math.Max(8, 96 * frac) : 0, 8);
                Right(g, Fmt(vals[i]), FRowB, Text, XR, y);
            }

            using (var p = new Pen(Panel, 2)) g.DrawLine(p, X, 191, XR, 191);

            // 5-hour window + burn
            const float BX = 342;
            Str(g, "5H WINDOW", FLabel, Muted, X, 195);
            Str(g, "BURN / MIN", FLabel, Muted, BX, 195);
            if (s.BlockActive)
            {
                TimeSpan left = s.BlockEnd - nowUtc;
                Str(g, Fmt(s.BlockTokens), FMid, Text, X - 3, 209);
                float frac = (float)Math.Max(0, Math.Min(1, 1 - left.TotalHours / 5.0));
                RoundRect(g, Panel, X, 249, 84, 7);
                RoundRect(g, Orange, X, 249, Math.Max(7, 84 * frac), 7);
                Str(g, Span(left), FSmall, Orange, X + 88, 242);
            }
            else Str(g, "idle", FMid, Muted, X - 3, 209);
            Str(g, Fmt((long)s.BurnPerMin), FMid, Text, BX - 3, 209);

            // 7-day bars
            long max = 1;
            foreach (long d in s.Days) max = Math.Max(max, d);
            float slot = (XR - X) / 7f, bw = 24, top = 266, hMax = 30;
            for (int i = 0; i < 7; i++)
            {
                float x = X + i * slot + (slot - bw) / 2;
                float h = s.Days[i] > 0 ? Math.Max(3, hMax * s.Days[i] / max) : 2;
                Color c = i == 6 ? Orange : Color.FromArgb(125, 117, 108);
                using (var b = new SolidBrush(c)) g.FillRectangle(b, x, top + hMax - h, bw, h);
                Center(g, s.DayNames[i], FSmall, i == 6 ? Text : Muted, x - 10, x + bw + 10, top + hMax);
            }
        }
    }

    public enum Orientation { Landscape, ReverseLandscape }

    public class Screen35 : IDisposable
    {
        const int DevW = 320, DevH = 480;
        SerialPort sp;
        public Orientation Orient = Orientation.ReverseLandscape;

        public void Open(string port)
        {
            sp = new SerialPort(port, 115200);
            sp.Handshake = Handshake.RequestToSend;
            sp.WriteTimeout = 5000;
            sp.Open();
        }

        void Cmd(int cmd, int x, int y, int ex, int ey)
        {
            var b = new byte[6];
            b[0] = (byte)(x >> 2);
            b[1] = (byte)((((x & 3) << 6) + (y >> 4)) & 0xFF);
            b[2] = (byte)((((y & 15) << 4) + (ex >> 6)) & 0xFF);
            b[3] = (byte)((((ex & 63) << 2) + (ey >> 8)) & 0xFF);
            b[4] = (byte)(ey & 0xFF);
            b[5] = (byte)cmd;
            sp.Write(b, 0, 6);
        }

        public void ScreenOn(int brightnessPct)
        {
            Cmd(109, 0, 0, 0, 0);
            Cmd(110, (int)(255 - brightnessPct / 100.0 * 255), 0, 0, 0);
        }

        // Last RGB565 value sent for each logical pixel; lets us send only changed tiles.
        readonly ushort[] shadow = new ushort[Render.W * Render.H];
        bool shadowValid;

        static ushort[] ToRgb565(Bitmap bmp, Rectangle r)
        {
            BitmapData d = bmp.LockBits(r, ImageLockMode.ReadOnly, PixelFormat.Format24bppRgb);
            var raw = new byte[d.Stride * r.Height];
            Marshal.Copy(d.Scan0, raw, 0, raw.Length);
            int stride = d.Stride;
            bmp.UnlockBits(d);
            var res = new ushort[r.Width * r.Height];
            int k = 0;
            for (int y = 0; y < r.Height; y++)
            {
                int o = y * stride;
                for (int x = 0; x < r.Width; x++, o += 3)
                    res[k++] = (ushort)(((raw[o + 2] & 0xF8) << 8) | ((raw[o + 1] & 0xFC) << 3) | (raw[o] >> 3));
            }
            return res;
        }

        // Sends only the 16x16 tiles of r that differ from what is already on the panel.
        public void SendChanged(Bitmap bmp, Rectangle r)
        {
            if (!shadowValid) { SendRegion(bmp, Render.FullRect); shadowValid = true; return; }
            const int T = 8;
            ushort[] cur = ToRgb565(bmp, r);
            for (int ty = 0; ty < r.Height; ty += T)
            {
                int th = Math.Min(T, r.Height - ty);
                int run = -1;
                for (int tx = 0; tx <= r.Width; tx += T)
                {
                    bool changed = false;
                    if (tx < r.Width)
                    {
                        int tw = Math.Min(T, r.Width - tx);
                        for (int y = ty; y < ty + th && !changed; y++)
                        {
                            int ci = y * r.Width + tx;
                            int si = (r.Y + y) * Render.W + r.X + tx;
                            for (int x = 0; x < tw; x++)
                                if (cur[ci + x] != shadow[si + x]) { changed = true; break; }
                        }
                    }
                    if (changed && run < 0) run = tx;
                    if (!changed && run >= 0)
                    {
                        int end = Math.Min(tx, r.Width);
                        SendRegion(bmp, new Rectangle(r.X + run, r.Y + ty, end - run, th));
                        run = -1;
                    }
                }
            }
        }

        // r is in landscape (480x320) coordinates; pixels are rotated onto the portrait panel.
        public void SendRegion(Bitmap bmp, Rectangle r)
        {
            ushort[] cur = ToRgb565(bmp, r);
            for (int y = 0; y < r.Height; y++)
                Array.Copy(cur, y * r.Width, shadow, (r.Y + y) * Render.W + r.X, r.Width);

            int w = r.Width, h = r.Height;
            bool cw = Orient == Orientation.Landscape;
            // Device rect is h wide, w tall.
            int dx = cw ? DevW - r.Y - h : r.Y;
            int dy = cw ? r.X : DevH - r.X - w;
            var px = new byte[w * h * 2];
            int k = 0;
            for (int b = 0; b < w; b++)
            {
                for (int a = 0; a < h; a++)
                {
                    int u = cw ? b : w - 1 - b;
                    int v = cw ? h - 1 - a : a;
                    int val = cur[v * w + u];
                    px[k++] = (byte)(val & 0xFF);
                    px[k++] = (byte)(val >> 8);
                }
            }
            Cmd(197, dx, dy, dx + h - 1, dy + w - 1);
            int chunk = DevW * 8 * 2;
            for (int off = 0; off < px.Length; off += chunk)
                sp.Write(px, off, Math.Min(chunk, px.Length - off));
        }

        public void Dispose()
        {
            if (sp != null) { try { sp.Close(); } catch { } sp = null; }
        }
    }

    public static class Monitor
    {
        public static bool IsActive(Stats s, DateTime nowUtc)
        {
            return s.LastTime != DateTime.MinValue && (nowUtc - s.LastTime).TotalSeconds < 45;
        }

        public static void Preview(string root, string outPng, double t, bool forceActive)
        {
            var store = new UsageStore(root);
            store.Poll();
            DateTime now = DateTime.UtcNow;
            Stats s = Stats.Compute(store.Entries, now);
            using (var bmp = new Bitmap(Render.W, Render.H, PixelFormat.Format24bppRgb))
            using (var g = Graphics.FromImage(bmp))
            {
                Render.DrawStatic(g, s, now);
                Render.DrawIcon(g, t, forceActive || IsActive(s, now));
                bmp.Save(outPng, ImageFormat.Png);
            }
        }

        public static void Run(string root, string port, int brightness, string orientation)
        {
            Orientation orient = (Orientation)Enum.Parse(typeof(Orientation), orientation, true);
            var store = new UsageStore(root);
            Console.WriteLine("Scanning transcripts...");
            store.Poll();
            Console.WriteLine("Loaded " + store.Entries.Count + " messages. Driving " + port + " (" + orient + "). Ctrl+C to stop.");

            var bmp = new Bitmap(Render.W, Render.H, PixelFormat.Format24bppRgb);
            var g = Graphics.FromImage(bmp);
            var clock = System.Diagnostics.Stopwatch.StartNew();
            DateTime lastPoll = DateTime.MinValue;
            Stats stats = Stats.Compute(store.Entries, DateTime.UtcNow);

            while (true)
            {
                Screen35 scr = new Screen35();
                scr.Orient = orient;
                try
                {
                    scr.Open(port);
                    scr.ScreenOn(brightness);
                    string lastSig = null;
                    int frames = 0;
                    long fpsMark = clock.ElapsedMilliseconds;
                    while (true)
                    {
                        long frameStart = clock.ElapsedMilliseconds;
                        DateTime now = DateTime.UtcNow;
                        if ((now - lastPoll).TotalSeconds >= 1)
                        {
                            store.Poll();
                            stats = Stats.Compute(store.Entries, now);
                            lastPoll = now;
                        }
                        bool active = IsActive(stats, now);
                        string sig = stats.Signature(now);
                        if (sig != lastSig)
                        {
                            Render.DrawStatic(g, stats, now);
                            lastSig = sig;
                        }
                        Render.DrawIcon(g, clock.Elapsed.TotalSeconds, active);
                        scr.SendChanged(bmp, Render.FullRect);

                        frames++;
                        if (clock.ElapsedMilliseconds - fpsMark >= 5000)
                        {
                            Console.WriteLine(DateTime.Now.ToString("HH:mm:ss") + " " +
                                (frames * 1000.0 / (clock.ElapsedMilliseconds - fpsMark)).ToString("0.0") + " fps");
                            frames = 0;
                            fpsMark = clock.ElapsedMilliseconds;
                        }
                        int period = active ? 33 : 50;
                        long wait = period - (clock.ElapsedMilliseconds - frameStart);
                        if (wait > 0) Thread.Sleep((int)wait);
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine(DateTime.Now.ToString("HH:mm:ss") + " screen error: " + ex.Message + " - retrying in 3s");
                    scr.Dispose();
                    Thread.Sleep(3000);
                }
            }
        }
    }
}
