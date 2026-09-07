# Overnight AutoLab launcher (Windows)
$ErrorActionPreference = "Stop"
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')

Set-Location $PSScriptRoot\..

# Prefer staying awake on AC power while the lab runs
powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change hibernate-timeout-ac 0 | Out-Null

Write-Host "Starting 6-hour AutoLab supervisor..."
& .\.venv\Scripts\python.exe autolab\supervisor.py --hours 6
