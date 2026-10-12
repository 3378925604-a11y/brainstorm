# doctor.ps1 - read-only self check (ASCII-only message to avoid PS 5.1 encoding issues)
$ErrorActionPreference = 'SilentlyContinue'
$fail = 0
$warn = 0

function OK($m)   { Write-Host "[OK  ] $m" -ForegroundColor Green }
function WARN($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow; $script:warn++ }
function BAD($m)  { Write-Host "[FAIL] $m" -ForegroundColor Red;    $script:fail++ }

Write-Host "=== brain-storm doctor ===" -ForegroundColor Cyan

# 1. config file present
if (Test-Path "$PSScriptRoot\config.json") { OK "config.json present" } else { BAD "config.json missing" }

# 2. config parses
try {
    $cfg = Get-Content "$PSScriptRoot\config.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    OK "config.json is valid JSON"
    if ($cfg.agents -and $cfg.agents.Count -gt 0) { OK ("agents count: " + $cfg.agents.Count) }
    else { BAD "agents array is empty" }
} catch { BAD ("config.json parse error: " + $_.Exception.Message); $cfg = $null }

# 3. credential file
if (Test-Path "$PSScriptRoot\config.local.json") { OK "config.local.json present" }
else { WARN "config.local.json absent (copy config.local.json.example and fill it)" }

# 4. no plaintext secrets in config.json
if (Test-Path "$PSScriptRoot\config.json") {
    $raw = Get-Content "$PSScriptRoot\config.json" -Raw
    if ($raw -match '(?i)"[^"]*(appsecret|oauthtoken|apikey|api_key|appkey|app_key|access_token|refresh_token|secret|token|credential|authorization|cookie)[^"]*"\s*:\s*"[^"]+') { BAD "config.json looks like it holds a plaintext secret" }
    else { OK "config.json has no plaintext secret" }
}

# 5. gitignore covers credentials
if (Test-Path "$PSScriptRoot\.gitignore") {
    $gi = Get-Content "$PSScriptRoot\.gitignore" -Raw
    if ($gi -match 'config\.local\.json') { OK ".gitignore covers config.local.json" }
    else { BAD ".gitignore does not cover config.local.json" }
} else { WARN ".gitignore missing" }

# 6. room file
$room = if ($cfg -and $cfg.room.file) { Join-Path $PSScriptRoot $cfg.room.file } else { Join-Path $PSScriptRoot "room.jsonl" }
if (Test-Path $room) { OK ("room file exists: " + $room) } else { WARN ("room file not created yet: " + $room) }

# 7. dingtalk credential fields
if (Test-Path "$PSScriptRoot\config.local.json") {
    try {
        $loc = Get-Content "$PSScriptRoot\config.local.json" -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($loc.dingtalk.appKey -and $loc.dingtalk.appSecret) { OK "dingtalk credential fields filled" }
        else { WARN "dingtalk credential fields empty" }
    } catch { WARN "config.local.json parse error" }
}

# 8. wakeup commands resolvable
if ($cfg) {
    foreach ($a in $cfg.agents) {
        $cmd = $a.wakeup.command
        if (-not $cmd) { BAD ("agent " + $a.name + " has no wakeup.command"); continue }
        if (Get-Command $cmd -ErrorAction SilentlyContinue) { OK ("wakeup command ok: " + $cmd + " (" + $a.name + ")") }
        else { WARN ("wakeup command not in PATH: " + $cmd + " (" + $a.name + ")") }
    }
}

# 9. core scripts present
foreach ($f in @("brainstorm\room.py", "brainstorm\watcher.py", "brainstorm\bridge.py", "brainstorm\config.py")) {
    if (Test-Path "$PSScriptRoot\$f") { OK ("core script: " + $f) } else { BAD ("core script missing: " + $f) }
}

# 10. python
if (Get-Command python -ErrorAction SilentlyContinue) { OK ("python: " + (python --version 2>&1)) }
else { BAD "python not in PATH" }

# 11. git
if (Get-Command git -ErrorAction SilentlyContinue) {
    OK ("git: " + (git --version 2>$null))
    if (Test-Path "$PSScriptRoot\.git") { OK "git repo initialized" } else { WARN "not a git repo yet (git init)" }
} else { WARN "git not in PATH" }

Write-Host ""
if ($fail -eq 0) { Write-Host ("doctor PASS (" + $warn + " warnings)") -ForegroundColor Green } else { Write-Host ("doctor FAIL: " + $fail + " failed, " + $warn + " warnings") -ForegroundColor Red }
exit $fail
