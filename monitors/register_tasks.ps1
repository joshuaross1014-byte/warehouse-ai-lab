<#
  Register the ops monitors as Windows Scheduled Tasks.
  Runs as the current user (they need cached DB/API creds), only when logged on.

  Usage:
    powershell -ExecutionPolicy Bypass -File register_tasks.ps1 -Python "C:\path\to\python.exe"

  Re-running overwrites the existing tasks (-Force). Times use minutes off :00
  to avoid the top-of-hour stampede. Adjust the price-gap time to fire BEFORE
  your morning regional import.
#>
param(
  [string]$Python = "python.exe"
)

$dir = $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

function Reg($name, $script, $trigger) {
  $a = New-ScheduledTaskAction -Execute $Python -Argument $script -WorkingDirectory $dir
  Register-ScheduledTask -TaskName $name -Action $a -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Output "registered: $name"
}

# hourly, 24/7 (import errors)
$tImp = New-ScheduledTaskTrigger -Once -At "00:07" -RepetitionInterval (New-TimeSpan -Hours 1)

# hourly, ops hours 06:07-20:07 (wave health)
$tWave = New-ScheduledTaskTrigger -Daily -At "06:07"
$tWave.Repetition = (New-ScheduledTaskTrigger -Once -At "06:07" `
  -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 14)).Repetition

# daily fixed times
$tPrice = New-ScheduledTaskTrigger -Daily -At "10:43"   # set BEFORE your morning import
$tBot   = New-ScheduledTaskTrigger -Daily -At "07:12"

Reg "OpsMonitor-WMS-Import-Errors" "monitor_wms_import_errors.py" $tImp
Reg "OpsMonitor-Wave-Health"       "monitor_wave_health.py"       $tWave
Reg "OpsMonitor-SO-Price-Gap"      "monitor_so_price_gap.py"      $tPrice
Reg "OpsMonitor-Bot-Health"        "monitor_bot_health.py"        $tBot
