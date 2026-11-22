# Claude Code token monitor for the 3.5" USB screen.
#   .\token-monitor.ps1                 run in this window (Ctrl+C to stop)
#   .\token-monitor.ps1 -Background     run hidden in the background
#   .\token-monitor.ps1 -Stop           stop the background instance
#   .\token-monitor.ps1 -Preview out.png  render one frame to a PNG
param(
    [string]$Port = 'COM6',
    [int]$Brightness = 60,
    [ValidateSet('ReverseLandscape', 'Landscape')]
    [string]$Orientation = 'ReverseLandscape',
    [switch]$Background,
    [switch]$Stop,
    [string]$Preview,
    [switch]$Active
)
$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'token-monitor.pid'

if ($Stop) {
    if (Test-Path $pidFile) {
        $id = Get-Content $pidFile
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Remove-Item $pidFile
        Write-Host "Stopped monitor (PID $id)."
    } else { Write-Host 'No background monitor running.' }
    return
}

if ($Background) {
    $p = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
        '-Port', $Port, '-Brightness', $Brightness, '-Orientation', $Orientation)
    $p.Id | Set-Content $pidFile
    Write-Host "Monitor started in background (PID $($p.Id))."
    return
}

Add-Type -AssemblyName System.Drawing
Add-Type -Path (Join-Path $PSScriptRoot 'TokenMonitor.cs') -ReferencedAssemblies System.Drawing, System
$root = Join-Path $env:USERPROFILE '.claude\projects'

if ($Preview) {
    [ClaudeScreen.Monitor]::Preview($root, [IO.Path]::GetFullPath($Preview), 0.4, [bool]$Active)
    Write-Host "Saved $Preview"
    return
}

[ClaudeScreen.Monitor]::Run($root, $Port, $Brightness, $Orientation)
