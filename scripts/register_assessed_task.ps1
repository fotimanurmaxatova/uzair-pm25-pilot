
# Registers the hourly ASSESSED collection task (approved window: 2 Nov 00:05 to 8 Nov 23:05, Asia/Tashkent).
# Run once in PowerShell from the repo root, AFTER the collector is committed and tagged:
#   powershell -ExecutionPolicy Bypass -File scripts\register_assessed_task.ps1
# The laptop clock/time zone must be Tashkent (tzutil /g -> "West Asia Standard Time").
# 168 hourly triggers = 168 x 8 cities = 1,344 maximum rows. Missed hours stay gaps (no catch-up run).
$root = (Resolve-Path "$PSScriptRoot\..").Path
$action   = New-ScheduledTaskAction -Execute "$root\scripts\run_collect_assessed.bat"
$trigger  = New-ScheduledTaskTrigger -Once -At ([datetime]"2026-11-02 00:05") `
            -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 168)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun `
            -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "UzAir-assessed-collect" -Action $action -Trigger $trigger -Settings $settings -Force
Get-ScheduledTask -TaskName "UzAir-assessed-collect" | Get-ScheduledTaskInfo
