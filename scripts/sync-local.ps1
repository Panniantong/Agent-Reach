# Fork only: brings this checkout's main up to date with the fork on GitHub (origin/main).
# Safe to run unattended: it only fast-forwards, and skips when the checkout is on another
# branch, has uncommitted changes or has local commits not yet pushed. When pyproject.toml
# changes, it reinstalls the editable Agent Reach so new dependencies are picked up.
#
# Register it once to run daily:  powershell -ExecutionPolicy Bypass -File scripts\sync-local.ps1 -Register
param([switch]$Register)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$log = Join-Path $env:USERPROFILE '.agent-reach\fork-sync.log'
$taskName = 'AgentReach-fork-sync'

function Write-Log([string]$message) {
    $line = '{0:yyyy-MM-dd HH:mm}  {1}' -f (Get-Date), $message
    New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Output $line
}

if ($Register) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 10:00
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Description 'Trae los cambios del fork de Agent Reach a la carpeta local (solo fast-forward).' -Force | Out-Null
    Write-Output "Tarea '$taskName' registrada: cada día a las 10:00 (o al encender el PC si se pasó la hora)."
    exit 0
}

function Invoke-Git([string[]]$arguments) {
    $out = & git -C $repo @arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($arguments -join ' '): $out" }
    return $out
}

try {
    $branch = Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')
    if ($branch -ne 'main') { Write-Log "Omitido: la carpeta está en la rama '$branch', no en main."; exit 0 }
    if (Invoke-Git @('status', '--porcelain')) { Write-Log 'Omitido: hay cambios sin guardar en un commit.'; exit 0 }

    Invoke-Git @('fetch', '--quiet', 'origin', 'main') | Out-Null
    $ahead = [int](Invoke-Git @('rev-list', '--count', 'origin/main..HEAD'))
    if ($ahead -gt 0) { Write-Log "Omitido: hay $ahead commit(s) locales sin subir (git push)."; exit 0 }
    $behind = [int](Invoke-Git @('rev-list', '--count', 'HEAD..origin/main'))
    if ($behind -eq 0) { Write-Log 'Ya al día.'; exit 0 }

    $before = Invoke-Git @('rev-parse', 'HEAD')
    Invoke-Git @('merge', '--ff-only', '--quiet', 'origin/main') | Out-Null
    Write-Log "Actualizado: $behind commit(s) nuevos."

    if (Invoke-Git @('diff', '--name-only', $before, 'HEAD', '--', 'pyproject.toml', 'constraints.txt')) {
        $uv = (Get-Command uv -ErrorAction Stop).Source
        & $uv tool install --force --editable $repo 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'uv tool install falló' }
        Write-Log 'Dependencias cambiadas: Agent Reach reinstalado.'
    }
} catch {
    Write-Log "Error: $_"
    exit 1
}
