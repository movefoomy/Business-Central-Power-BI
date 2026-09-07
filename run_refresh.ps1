<#
  Hourly runner for refresh.py, invoked by the "BC Sales Margin Refresh" scheduled task.

  Appends a timestamped, indented block to refresh.log for every run and trims the log
  so it cannot grow without bound. Exits with refresh.py's own exit code, so a failed
  run shows as "Last Run Result" other than 0x0 in Task Scheduler.

  If refresh.py fails (BC unreachable, credentials rejected), it raises before writing
  anything, so the previous good dashboard.html and data.json are left untouched.

  On success it commits the regenerated dashboard.html and pushes it, which is what
  makes the Vercel site refresh: Vercel rebuilds on every push to the tracked branch.
  Business Central is on-prem behind a self-signed cert, so no cloud cron can fetch it
  -- this machine is the only thing that can, and pushing is how the result gets out.
  A push failure is logged but never fails the task: the local dashboard is still good.
#>

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

$log     = Join-Path $PSScriptRoot 'refresh.log'
$keep    = 1000   # lines of history to retain
$stamp   = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Where the published site builds from. Change these two if the deploy moves.
$remote  = 'dashboard'
$branch  = 'main'

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

# Publish. Only on a clean refresh -- never push a build the sanity gate rejected.
if ($code -eq 0) {
    # Fail fast rather than block the unattended task on a credential prompt.
    $env:GIT_TERMINAL_PROMPT = '0'
    $env:GCM_INTERACTIVE     = 'never'

    $entry += '  '
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        $entry += '  Publish skipped: git not on PATH'
    } else {
        & git add -- dashboard.html 2>&1 | Out-Null
        & git diff --cached --quiet -- dashboard.html
        if ($LASTEXITCODE -eq 0) {
            $entry += '  Publish skipped: dashboard.html unchanged'
        } else {
            $push = & git commit -m "Refresh dashboard data ($stamp)" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $entry += '  Publish FAILED at commit:'
                foreach ($line in $push) { $entry += '    ' + ($line -replace '\s+$', '') }
            } else {
                $push = & git push $remote $branch 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $entry += "  Published to $remote/$branch - Vercel will redeploy"
                } else {
                    $entry += "  Publish FAILED at push (commit is local, next run retries):"
                    foreach ($line in $push) { $entry += '    ' + ($line -replace '\s+$', '') }
                }
            }
        }
    }
}

Add-Content -LiteralPath $log -Value $entry -Encoding utf8

# Trim to the most recent $keep lines.
$lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
if ($lines.Count -gt $keep) {
    Set-Content -LiteralPath $log -Value $lines[-$keep..-1] -Encoding utf8
}

exit $code
