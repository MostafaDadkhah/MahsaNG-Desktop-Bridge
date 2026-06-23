param(
    [string]$Bind = "127.0.0.1:18080",
    [string]$Source = "all",
    [string]$Carrier = "all",
    [int]$CacheSeconds = 300,
    [string]$TaskName = "MahsaNGDesktopBridge"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunScript = Join-Path $ProjectDir "run_bridge_windows.ps1"
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $python -and -not $py) {
    throw "Python not found. Install Python 3.10+ from python.org or Microsoft Store, then retry."
}

$PythonBin = $null
if ($python) {
    & $python.Source -c "import cryptography" 2>$null
    if ($LASTEXITCODE -eq 0) { $PythonBin = $python.Source }
}
if (-not $PythonBin -and $py) {
    & $py.Source -3 -c "import cryptography" 2>$null
    if ($LASTEXITCODE -eq 0) { $PythonBin = $py.Source }
}
if (-not $PythonBin) {
    throw "Missing dependency: cryptography. Run: py -3 -m pip install -r requirements.txt"
}

$PowerShellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$ActionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -Bind `"$Bind`" -Source `"$Source`" -Carrier `"$Carrier`" -CacheSeconds `"$CacheSeconds`" -PythonBin `"$PythonBin`""
$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $ActionArgs -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel LeastPrivilege
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started $TaskName for Windows Scheduled Tasks"
Write-Host "Subscription: http://$Bind/sub"
Write-Host "Plain links:   http://$Bind/links"
Write-Host "Health:        http://$Bind/health"
Write-Host "Logs:          $LogDir"
