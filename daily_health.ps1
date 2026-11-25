<#
.SYNOPSIS
    Runs the daily health data jobs with default arguments:
      1. ../copy_datalog/copy_oscar.py
      2. ../copy_datalog/copy_somnotrace.py
      3. main.py (Oura export)

    All scripts run with the "oura" conda environment's Python. Each one runs from its
    own folder so relative paths (.env, oura.csv, token file) resolve correctly.
    A failure in one script does not stop the others.

    If the Oura export writes at least one row, oura.csv is opened right away,
    without waiting for the remaining jobs.

    When launched from File Explorer (double-click on daily_health.cmd, or
    "Run with PowerShell"), the window waits for a key press before closing.
#>

$ErrorActionPreference = 'Stop'

$python = Join-Path $env:USERPROFILE 'anaconda3\envs\oura\python.exe'
$ouraDir = $PSScriptRoot
$datalogDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'copy_datalog'

$jobs = @(
    @{ Name = 'Oura export';     Dir = $ouraDir;    Script = 'main.py'; OpenOnExport = (Join-Path $ouraDir 'oura.csv') }
    @{ Name = 'OSCAR copy';      Dir = $datalogDir; Script = 'copy_oscar.py' }
    @{ Name = 'SomnoTrace copy'; Dir = $datalogDir; Script = 'copy_somnotrace.py' }
)

function Test-LaunchedFromExplorer {
    # Walk up the parent process chain (powershell -> cmd -> explorer, or powershell -> explorer).
    try {
        $id = $PID
        for ($i = 0; $i -lt 3; $i++) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $id"
            if (-not $proc) { return $false }
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)"
            if (-not $parent) { return $false }
            if ($parent.Name -ieq 'explorer.exe') { return $true }
            if ($parent.Name -inotin @('cmd.exe', 'powershell.exe', 'pwsh.exe')) { return $false }
            $id = $parent.ProcessId
        }
    } catch { }
    return $false
}

$failed = @()

if (-not (Test-Path $python)) {
    Write-Host "Python not found: $python" -ForegroundColor Red
    $failed += 'all (missing Python)'
} else {
    foreach ($job in $jobs) {
        Write-Host ''
        Write-Host "=== $($job.Name): $($job.Script) ===" -ForegroundColor Cyan
        Push-Location $job.Dir
        try {
            # -u: unbuffered so output appears live while it is also captured.
            & $python -u $job.Script | Tee-Object -Variable output | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Host "$($job.Name) failed (exit code $LASTEXITCODE)" -ForegroundColor Red
                $failed += $job.Name
            } elseif ($job.OpenOnExport) {
                $exported = $output | Select-String -Pattern 'Exported (\d+) total rows' | Select-Object -Last 1
                if ($exported -and [int]$exported.Matches[0].Groups[1].Value -ge 1) {
                    Invoke-Item $job.OpenOnExport
                }
            }
        } catch {
            Write-Host "$($job.Name) failed: $_" -ForegroundColor Red
            $failed += $job.Name
        } finally {
            Pop-Location
        }
    }
}

Write-Host ''
if ($failed.Count -eq 0) {
    Write-Host 'All jobs completed successfully.' -ForegroundColor Green
    $exitCode = 0
} else {
    Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red
    $exitCode = 1
}

if (Test-LaunchedFromExplorer) {
    Write-Host ''
    Write-Host 'Press any key to exit...'
    [void][System.Console]::ReadKey($true)
}

exit $exitCode
