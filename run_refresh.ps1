<#
  Hourly runner for refresh.py, invoked by the "BC Sales Margin Refresh" scheduled task.

  Appends a timestamped, indented block to refresh.log for every run and trims the log
  so it cannot grow without bound. Exits with refresh.py's own exit code, so a failed
  run shows as "Last Run Result" other than 0x0 in Task Scheduler.

  If refresh.py fails (BC unreachable, credentials rejected), it raises before writing
  anything, so the previous good dashboard.html and data.json are left untouched.
#>

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

$log     = Join-Path $PSScriptRoot 'refresh.log'
$keep    = 1000   # lines of history to retain
$stamp   = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Prefer the interpreter the task was set up with; fall back to whatever is on PATH.
$py = 'C:\Python314\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) {
        $py = $found.Source
    } else {
        Add-Content -LiteralPath $log -Encoding utf8 `
            -Value "===== $stamp  FAILED: no Python interpreter found ====="
        exit 9009
    }
}

$output = & $py 'refresh.py' 2>&1
$code   = $LASTEXITCODE
$status = if ($code -eq 0) { 'OK' } else { "FAILED (exit $code)" }

$entry = @("===== $stamp  $status =====")
foreach ($line in $output) { $entry += '  ' + ($line -replace '\s+$', '') }
Add-Content -LiteralPath $log -Value $entry -Encoding utf8

# Trim to the most recent $keep lines.
$lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
if ($lines.Count -gt $keep) {
    Set-Content -LiteralPath $log -Value $lines[-$keep..-1] -Encoding utf8
}

exit $code
