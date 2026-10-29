<#
.SYNOPSIS
    Safely stops the Aether Mark-1 backend listening on port 8765.

.DESCRIPTION
    Locates the process that owns the listening socket on port 8765, verifies
    that its command line actually belongs to Aether (project path / aether /
    uvicorn / --mode web), and only then terminates it together with its child
    processes. Never kills unrelated Python processes.

.PARAMETER Port
    TCP port to inspect (default 8765).

.PARAMETER Force
    When set, skip the interactive confirmation prompt.

.NOTES
    Exit codes:
      0 - Aether backend stopped (or was not running).
      1 - A process occupies the port but does NOT look like Aether -> NOT killed.
      2 - Unexpected error.
#>
param(
    [int]$Port = 8765,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Info($msg) { Write-Host "[INFO]  $msg" }
function Write-Warn($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

try {
    # 1. Find listening connection on the port.
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conn) {
        Write-Info "No process is listening on port $Port. Nothing to stop."
        exit 0
    }

    # There can be multiple (rare). Take the first owning PID.
    $ownerPid = $conn[0].OwningProcess
    if (-not $ownerPid -or $ownerPid -eq 0) {
        Write-Warn "Could not resolve owning process for port $Port."
        exit 1
    }

    # 2. Inspect the process command line.
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Warn "PID $ownerPid no longer exists."
        exit 0
    }

    $cmdLine = $proc.CommandLine
    if ([string]::IsNullOrWhiteSpace($cmdLine)) {
        $cmdLine = "<empty>"
    }

    Write-Info "Port $Port is owned by PID $ownerPid"
    Write-Info "Command line: $cmdLine"

    # 3. Verify it really is Aether.
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $isAether = $false
    $reasons = @()

    if ($cmdLine -match [regex]::Escape($projectRoot)) { $isAether = $true; $reasons += "project path" }
    if ($cmdLine -match "(?i)aether")                    { $isAether = $true; $reasons += "aether" }
    if ($cmdLine -match "(?i)uvicorn")                  { $isAether = $true; $reasons += "uvicorn" }
    if ($cmdLine -match "(?i)--mode\s+web")             { $isAether = $true; $reasons += "--mode web" }
    if ($cmdLine -match "(?i)server\.py")               { $isAether = $true; $reasons += "server.py" }

    if (-not $isAether) {
        Write-Err "The process on port $Port does NOT look like Aether."
        Write-Err "Refusing to kill it for safety. (matched none of: project path, 'aether', 'uvicorn', '--mode web', 'server.py')"
        Write-Err "If this is really Aether, stop it manually: taskkill /PID $ownerPid /T /F"
        exit 1
    }

    Write-Info "Verified as Aether backend (matched: $($reasons -join ', '))."

    # 4. Confirm (unless Force).
    if (-not $Force) {
        $answer = Read-Host "Stop Aether backend PID $ownerPid? [y/N]"
        if ($answer -notmatch "^(y|yes)$") {
            Write-Info "Cancelled by user. No process was stopped."
            exit 0
        }
    }

    # 5. Terminate process tree.
    Write-Info "Stopping PID $ownerPid (and child processes)..."
    & taskkill /PID $ownerPid /T /F 2>&1 | Out-Null
    Start-Sleep -Seconds 2

    # 6. Verify it actually stopped.
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) {
        Write-Warn "Port $Port is still in use after kill attempt (PID $($still[0].OwningProcess))."
        exit 1
    }
    Write-Info "Aether backend stopped. Port $Port is free."
    exit 0
}
catch {
    Write-Err "Unexpected error: $($_.Exception.Message)"
    exit 2
}