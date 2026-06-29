<#
.SYNOPSIS
    Verify that Agent-Reach's Twitter/X access actually works (live fetch).

.DESCRIPTION
    Self-contained check, independent of the install session. It:
      1. Locates the Agent-Reach venv and the 'twitter' CLI.
      2. Reads twitter_auth_token / twitter_ct0 from ~/.agent-reach/config.yaml
         (via Agent-Reach's own Config loader, which also honours the uppercase
         env-var form TWITTER_AUTH_TOKEN / TWITTER_CT0).
      3. Exports those as TWITTER_AUTH_TOKEN / TWITTER_CT0 -- twitter-cli reads
         them directly (Agent-Reach is a glue layer, not a wrapper).
      4. Runs 'twitter status' (auth check) and a live 'twitter search',
         printing PASS / FAIL for each.

    Exit code: 0 if both checks PASS, 1 otherwise.
    NOTE: ASCII-only on purpose -- Windows PowerShell 5.1 reads BOM-less UTF-8
    scripts as ANSI, which mangles non-ASCII characters.

.PARAMETER Query
    Search term for the live-fetch check. Default: "openai".

.PARAMETER Max
    Max tweets to fetch for the search check. Default: 3.

.PARAMETER Venv
    Path to the Agent-Reach venv. Defaults to $env:AGENT_REACH_VENV, then
    ~/.agent-reach-venv.

.EXAMPLE
    powershell -File scripts\verify_twitter.ps1
    powershell -File scripts\verify_twitter.ps1 -Query "claude ai" -Max 5
#>

[CmdletBinding()]
param(
    [string]$Query = "openai",
    [int]$Max = 3,
    [string]$Venv = $(if ($env:AGENT_REACH_VENV) { $env:AGENT_REACH_VENV } else { Join-Path $env:USERPROFILE ".agent-reach-venv" })
)

$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

function Write-Status($ok, $label, $detail) {
    $mark = if ($ok) { "PASS" } else { "FAIL" }
    $color = if ($ok) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1}" -f $mark, $label) -ForegroundColor $color
    if ($detail) { Write-Host "       $detail" -ForegroundColor DarkGray }
}

Write-Host "Agent-Reach -- Twitter/X verification" -ForegroundColor Cyan
Write-Host ("=" * 40)

# --- Locate venv python + twitter CLI ---------------------------------------
$pythonExe  = Join-Path $Venv "Scripts\python.exe"
$twitterExe = Join-Path $Venv "Scripts\twitter.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Status $false "venv" "Python not found at $pythonExe. Re-run the Agent-Reach install (U1/U2)."
    exit 1
}
if (-not (Test-Path $twitterExe)) {
    $resolved = (Get-Command twitter -ErrorAction SilentlyContinue).Source
    if ($resolved) {
        $twitterExe = $resolved
    } else {
        Write-Status $false "twitter-cli" "Not found. Install with: pip install twitter-cli (into the venv)."
        exit 1
    }
}
$env:PATH = (Join-Path $Venv "Scripts") + ";" + $env:PATH

# --- Read cookies from Agent-Reach config -----------------------------------
# Parse ~/.agent-reach/config.yaml directly. (Reading via `python -c` is fragile
# on Windows PowerShell 5.1, which mangles embedded double quotes when passing
# arguments to native executables.) These are the exact keys that
# `agent-reach configure twitter-cookies` writes.
$cfgPath = Join-Path $env:USERPROFILE ".agent-reach\config.yaml"
$authToken = ""
$ct0 = ""
if (Test-Path $cfgPath) {
    foreach ($line in (Get-Content -LiteralPath $cfgPath)) {
        if ($line -match '^\s*twitter_auth_token\s*:\s*(.+?)\s*$') {
            $authToken = $matches[1].Trim().Trim("'").Trim('"')
        } elseif ($line -match '^\s*twitter_ct0\s*:\s*(.+?)\s*$') {
            $ct0 = $matches[1].Trim().Trim("'").Trim('"')
        }
    }
}
# Fall back to twitter-cli's own env-var convention if not stored in the file.
if (-not $authToken -and $env:TWITTER_AUTH_TOKEN) { $authToken = $env:TWITTER_AUTH_TOKEN }
if (-not $ct0 -and $env:TWITTER_CT0) { $ct0 = $env:TWITTER_CT0 }

if (-not $authToken -or -not $ct0) {
    Write-Status $false "cookies" "No twitter_auth_token / twitter_ct0 in ~/.agent-reach/config.yaml."
    Write-Host  '       Fix: agent-reach configure twitter-cookies "auth_token=...; ct0=..."' -ForegroundColor Yellow
    Write-Host  "       Export the header string from a dedicated/burner X account via Cookie-Editor." -ForegroundColor Yellow
    exit 1
}
$env:TWITTER_AUTH_TOKEN = $authToken
$env:TWITTER_CT0        = $ct0
$authPrev = $authToken.Substring(0, [Math]::Min(6, $authToken.Length))
$ct0Prev  = $ct0.Substring(0, [Math]::Min(6, $ct0.Length))
Write-Status $true "cookies" ("loaded auth_token={0}... ct0={1}..." -f $authPrev, $ct0Prev)

$statusOk = $false
$searchOk = $false

# --- Check 1: authenticated session -----------------------------------------
try {
    $statusOut = (& $twitterExe status 2>&1 | Out-String)
    if ($statusOut -match "ok:\s*true") {
        $statusOk = $true
        Write-Status $true "status" "twitter status -> ok: true"
    } else {
        Write-Status $false "status" ("twitter status did not report ok: true. Output:`n" + $statusOut.Trim())
    }
} catch {
    Write-Status $false "status" ("twitter status errored: " + $_.Exception.Message)
}

# --- Check 2: live search fetch ---------------------------------------------
if ($statusOk) {
    try {
        $searchRaw = (& $twitterExe search $Query -n $Max --json 2>&1 | Out-String)
        $code = $LASTEXITCODE
        $count = 0
        $sample = $null

        # Trim any leading log noise before the JSON payload.
        $jsonStart = $searchRaw.IndexOfAny([char[]]@('[', '{'))
        $jsonText = if ($jsonStart -ge 0) { $searchRaw.Substring($jsonStart) } else { $searchRaw }

        try {
            $parsed = $jsonText | ConvertFrom-Json
            $items = if ($parsed -is [System.Array]) { $parsed }
                     elseif ($parsed.tweets) { $parsed.tweets }
                     elseif ($parsed.data)   { $parsed.data }
                     elseif ($parsed.results) { $parsed.results }
                     else { @($parsed) }
            $count = @($items).Count
            if ($count -gt 0) {
                $first = @($items)[0]
                $sample = $first.text
                if (-not $sample) { $sample = $first.full_text }
                if (-not $sample) { $sample = $first.content }
            }
        } catch {
            # JSON did not parse -- fall back to exit code + non-empty output.
            if ($code -eq 0 -and $searchRaw.Trim()) { $count = 1 }
        }

        if ($count -ge 1) {
            $searchOk = $true
            $preview = if ($sample) { ($sample -replace "\s+", " ").Trim() } else { "(no text field; raw output received)" }
            if ($preview.Length -gt 160) { $preview = $preview.Substring(0, 160) + "..." }
            Write-Status $true "search" ("'{0}' returned {1} tweet(s). Sample: {2}" -f $Query, $count, $preview)
        } else {
            Write-Status $false "search" ("'{0}' returned no tweets. Output:`n{1}" -f $Query, $searchRaw.Trim())
        }
    } catch {
        Write-Status $false "search" ("search errored: " + $_.Exception.Message)
    }
} else {
    Write-Status $false "search" "skipped (status check failed -- fix auth first)"
}

# --- Summary ----------------------------------------------------------------
Write-Host ("=" * 40)
if ($statusOk -and $searchOk) {
    Write-Host "RESULT: PASS -- Twitter/X fetching works." -ForegroundColor Green
    exit 0
} else {
    Write-Host "RESULT: FAIL -- see messages above." -ForegroundColor Red
    Write-Host "If this machine's sandbox blocks network, retry in your own shell:" -ForegroundColor Yellow
    Write-Host "  ! powershell -File scripts\verify_twitter.ps1" -ForegroundColor Yellow
    exit 1
}
