param(
    [string]$TaskName = "MahsaNGDesktopBridge"
)

$ErrorActionPreference = "SilentlyContinue"
Stop-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Stopped and removed $TaskName from Windows Scheduled Tasks"
