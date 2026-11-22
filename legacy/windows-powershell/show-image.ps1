# Displays an image on a 3.5" Turing-style USB smart screen (rev A protocol, 320x480).
# Usage: .\show-image.ps1 [-Image path] [-Port COM6] [-Brightness 0-100]
param(
    [string]$Image,
    [string]$Port = 'COM6',
    [int]$Brightness = 60
)
Add-Type -AssemblyName System.Drawing

$W = 320; $H = 480

if (-not $Image) {
    $Image = Get-ChildItem 'C:\Windows\Web\Wallpaper' -Recurse -Include *.jpg, *.png -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Image -or -not (Test-Path $Image)) { throw "Image not found: $Image" }
Write-Host "Image: $Image"

function Send-Cmd($sp, [int]$cmd, [int]$x = 0, [int]$y = 0, [int]$ex = 0, [int]$ey = 0) {
    $b = [byte[]]::new(6)
    $b[0] = ($x -shr 2) -band 0xFF
    $b[1] = ((($x -band 3) -shl 6) + ($y -shr 4)) -band 0xFF
    $b[2] = ((($y -band 15) -shl 4) + ($ex -shr 6)) -band 0xFF
    $b[3] = ((($ex -band 63) -shl 2) + ($ey -shr 8)) -band 0xFF
    $b[4] = $ey -band 0xFF
    $b[5] = $cmd
    $sp.Write($b, 0, 6)
}

# Scale with crop-to-fill into 320x480 portrait
$src = [System.Drawing.Image]::FromFile((Resolve-Path $Image))
if ($src.Width -gt $src.Height) { $src.RotateFlip([System.Drawing.RotateFlipType]::Rotate90FlipNone) }
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = 'HighQualityBicubic'
$scale = [Math]::Max($W / $src.Width, $H / $src.Height)
$dw = $src.Width * $scale; $dh = $src.Height * $scale
$g.DrawImage($src, ($W - $dw) / 2, ($H - $dh) / 2, $dw, $dh)
$g.Dispose(); $src.Dispose()

# Convert to RGB565 little-endian
$rect = New-Object System.Drawing.Rectangle 0, 0, $W, $H
$data = $bmp.LockBits($rect, 'ReadOnly', [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$raw = [byte[]]::new($data.Stride * $H)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $raw, 0, $raw.Length)
$stride = $data.Stride
$bmp.UnlockBits($data); $bmp.Dispose()

$px = [byte[]]::new($W * $H * 2)
$i = 0
for ($yy = 0; $yy -lt $H; $yy++) {
    $row = $yy * $stride
    for ($xx = 0; $xx -lt $W; $xx++) {
        $o = $row + $xx * 3   # BGR
        $v = (($raw[$o + 2] -band 0xF8) -shl 8) -bor (($raw[$o + 1] -band 0xFC) -shl 3) -bor ($raw[$o] -shr 3)
        $px[$i] = $v -band 0xFF; $px[$i + 1] = $v -shr 8; $i += 2
    }
}

$sp = New-Object System.IO.Ports.SerialPort $Port, 115200
$sp.Handshake = 'RequestToSend'
$sp.WriteTimeout = 5000
$sp.Open()
try {
    Send-Cmd $sp 109                                              # SCREEN_ON
    Send-Cmd $sp 110 ([int](255 - ($Brightness / 100) * 255))     # SET_BRIGHTNESS (inverted)
    Send-Cmd $sp 197 0 0 ($W - 1) ($H - 1)                        # DISPLAY_BITMAP
    $chunk = $W * 8 * 2
    for ($off = 0; $off -lt $px.Length; $off += $chunk) {
        $sp.Write($px, $off, [Math]::Min($chunk, $px.Length - $off))
    }
    Write-Host "Sent to $Port."
} finally { $sp.Close() }
