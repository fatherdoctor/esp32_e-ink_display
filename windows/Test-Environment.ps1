[CmdletBinding()]
param([string]$PythonPath = 'python')
$ErrorActionPreference = 'Stop'
Write-Output 'Read-only prerequisites check; does not open Outlook or read appointments.'
& $PythonPath --version
& $PythonPath -c "import importlib.util; print({m: importlib.util.find_spec(m) is not None for m in ('bleak', 'win32com', 'pythoncom', 'cryptography')})"
$outlookType = [Type]::GetTypeFromProgID('Outlook.Application')
Write-Output ('Classic Outlook COM registration: ' + ($null -ne $outlookType))
Get-Service bthserv -ErrorAction SilentlyContinue | Select-Object Name, Status
Write-Output 'Radio availability and corporate Bluetooth policy still require a real BLE trial.'
