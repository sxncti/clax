$ErrorActionPreference = 'Stop'

$python = Get-Command py.exe, python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) { throw 'Instale Python 3.10 ou mais recente antes do CLAX.' }
$pythonArgs = if ($python.Name -eq 'py.exe') { @('-3') } else { @() }
$versionOk = & $python.Source @pythonArgs -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>$null
if ($LASTEXITCODE -ne 0 -or $versionOk -ne '1') { throw 'O CLAX requer Python 3.10 ou mais recente.' }
$claude = Get-Command claude, claude.exe, claude.cmd -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $claude) { throw 'Instale o Claude Code antes do CLAX.' }

$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$destination = Join-Path $env:LOCALAPPDATA 'Programs\CLAX'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'clax.cmd'), (Join-Path $source 'clax.py'), (Join-Path $source 'clax_rings.py') -Destination $destination -Force

& $python.Source @pythonArgs (Join-Path $destination 'clax.py') setup
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar os perfis do CLAX.' }

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$entries = @($userPath -split ';' | Where-Object { $_ })
if ($entries -notcontains $destination) {
    [Environment]::SetEnvironmentVariable('Path', (($entries + $destination) -join ';'), 'User')
}
$env:Path = "$destination;$env:Path"

$menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $menu 'CLAX 5h Rings.lnk'))
$shortcut.TargetPath = $env:ComSpec
$shortcut.Arguments = '/c ""' + (Join-Path $destination 'clax.cmd') + '" rings"'
$shortcut.WorkingDirectory = $destination
$shortcut.Description = 'Widget de limites das contas CLAX'
$shortcut.Save()

Write-Host 'CLAX instalado. Abra um novo PowerShell ou Prompt e rode: clax help'
Write-Host 'Abra o widget pelo Menu Iniciar: CLAX 5h Rings (ou execute: clax rings)'
