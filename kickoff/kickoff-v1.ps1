<#
kickoff-v1: a V1 player run, the laptop side (the V1 successor of v4-hand\kickoff\kickoff.ps1).

  kickoff-v1.cmd                       fresh V1 map, then DeepSeek on agent\prompts\core-v1.md
  kickoff-v1.cmd -Prompt NAME          ... on agent\prompts\NAME.md
  kickoff-v1.cmd -NoReset              no new map (the run folder and DeepSeek only)
  kickoff-v1.cmd -NoLaunch             no DeepSeek (the map and the run folder only)
  kickoff-v1.cmd -Player claude        the run folder for a Claude Code player (its CLAUDE.md);
                                       no DeepSeek: the Claude session is started in the folder

Steps: stop earlier runs (as computah); deploy the toolkit at the commit (HEAD) to the host as
its own dir fk-v5-<sha>, never over another; the host side, run from that dir:
kickoff-v1.sh <sha> <run> (a fresh world-3 map from the fk-play scenario, the kit, the rules,
the plant built by robots, the map saved and kept; see its header for every server change); the
run folder C:\fk-player\runs\<time>-<prompt> from new_run.py (everything from the same commit);
then DeepSeek as computah through C:\fk-player\launch.ps1, whose preflight and first message
come from the run's launch.json; then the feed window.
#>
param([string]$Prompt = "core-v1", [switch]$NoReset, [switch]$NoLaunch, [string]$Sha = "HEAD",
      [ValidateSet("deepseek", "claude")][string]$Player = "deepseek")
if ($Player -eq "claude") { $NoLaunch = $true }
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$v5 = Split-Path -Parent $here
$feed = Join-Path (Split-Path -Parent $v5) "v4-hand\kickoff\feed.js"
$P = "C:\fk-player"
$sha = (git -C $v5 rev-parse --short $Sha).Trim()
if ($LASTEXITCODE -ne 0) { throw "no commit $Sha in $v5" }
$dirty = git -C $v5 status --short -- fkcore agent kickoff scenario
if ($dirty) { Write-Host "note: uncommitted changes in v5; the run uses the commit $sha, not them" }
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$name = "$stamp-$Prompt"
$run = Join-Path $P "runs\$name"

# one run at a time: an earlier session would share the world with this one
runas /savecred /user:computah "powershell -NoProfile -ExecutionPolicy Bypass -File $P\stop.ps1"
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -match "feed\.(py|js)" } |
    ForEach-Object { taskkill /T /F /PID $_.ProcessId 2>$null | Out-Null }

# the toolkit on the host, pinned for the run (cmd pipes the tar's bytes; PowerShell would not)
$tk = "/home/computah/factorio/fk-v5-$sha"
cmd /c "git -C `"$v5`" archive --format=tar $sha | ssh computah-ct `"test -d $tk/fkcore || (mkdir -p $tk && tar -x -C $tk)`""
if ($LASTEXITCODE -ne 0) { throw "toolkit deploy to $tk failed" }
Write-Host "toolkit: $tk"

if (-not $NoReset) {
    ssh computah-ct "bash $tk/kickoff/kickoff-v1.sh $sha $name"
    if ($LASTEXITCODE -ne 0) { throw "kickoff-v1.sh failed (exit $LASTEXITCODE)" }
}

# the run's folder, from the same commit
python (Join-Path $here "new_run.py") $run --prompt $Prompt --sha $sha --player $Player
if ($LASTEXITCODE -ne 0) { throw "new_run.py failed" }
# the folder is made by this (Admin) account; DSH's sandbox, running as computah, rewrites the
# workspace ACL at start (kickoff.ps1, 2026-10-18 09:53)
icacls $run /grant "computah:(OI)(CI)F" /T /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw "could not give computah the run folder $run" }
Write-Host "workspace: $run"
if ($NoLaunch) { exit 0 }

runas /savecred /user:computah "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File $P\launch.ps1 -Run $run"
$pre = Join-Path $run "preflight.txt"
$t0 = Get-Date
while (-not (Test-Path $pre) -and ((Get-Date) - $t0).TotalSeconds -lt 240) { Start-Sleep 2 }
if (-not (Test-Path $pre)) { throw "no preflight result after 4 minutes (see $run)" }
$res = Get-Content -Raw $pre
if ($res -notmatch "^ok") { Write-Host "Preflight FAILED:`n$res"; exit 1 }
Write-Host "Preflight ok: DeepSeek is playing V1 as computah."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "chcp 65001 > `$null; node '$feed' '$run'"
Write-Host "feed window open; run: $run"
