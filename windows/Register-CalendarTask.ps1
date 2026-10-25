[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PythonwPath,
    [string]$TaskName = 'Inkplate Calendar Sync'
)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPathResolved = (Resolve-Path -LiteralPath $PythonwPath).Path
$scriptPath = Join-Path $projectPath 'sync_calendar.py'
$logPath = Join-Path $projectPath 'sync.log'
if ([IO.Path]::GetFileName($pythonPathResolved) -ne 'pythonw.exe') {
    throw 'Use your virtual environment pythonw.exe for quiet operation.'
}
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonPathResolved -WorkingDirectory $projectPath `
    -Argument ('"{0}" --log "{1}"' -f $scriptPath, $logPath)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
if ($PSCmdlet.ShouldProcess($TaskName, 'Register logon task for current user')) {
    # No -Force: an existing task must be reviewed instead of silently replaced.
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description 'Local Outlook calendar to Inkplate over BLE'
    Write-Output 'Registered. Start it in Task Scheduler after completing foreground pairing.'
}
