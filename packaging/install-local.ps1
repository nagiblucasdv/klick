<#
Instala o Klick neste computador direto do código (sem gerar .exe):
atalhos no Menu Iniciar, iniciar com o Windows e a tecla PrintScreen liberada para ele.

    .\packaging\install-local.ps1               # instala e abre
    .\packaging\install-local.ps1 -Desktop      # também cria atalho na área de trabalho
    .\packaging\install-local.ps1 -Uninstall    # remove atalhos e o início automático

Usa o .venv do projeto; se a pasta do projeto mudar de lugar, rode de novo.
O instalador de verdade (build.ps1) usa os mesmos nomes de atalho e substitui estes.
#>
param(
    [switch]$Desktop,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$dataDir = Join-Path $env:LOCALAPPDATA "Klick"
$icon = Join-Path $dataDir "klick.ico"
$programs = [Environment]::GetFolderPath("Programs")
$shortcuts = @{
    (Join-Path $programs "Klick.lnk") = ""
    (Join-Path $programs "Klick - Histórico.lnk") = "--history"
}
if ($Desktop) { $shortcuts[(Join-Path ([Environment]::GetFolderPath("Desktop")) "Klick.lnk")] = "" }
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$keyboardKey = "HKCU:\Control Panel\Keyboard"

function Stop-Klick {
    # Só o Klick rodando a partir deste .venv; outros Pythons ficam em paz.
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*-m klick*" -and $_.ExecutablePath -like "$root*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

if ($Uninstall) {
    Stop-Klick
    $all = @($shortcuts.Keys) + (Join-Path ([Environment]::GetFolderPath("Desktop")) "Klick.lnk")
    $all | Where-Object { Test-Path $_ } | Remove-Item -Force
    Remove-ItemProperty $runKey -Name "Klick" -ErrorAction SilentlyContinue
    Remove-ItemProperty $keyboardKey -Name "PrintScreenKeyForSnippingEnabled" -ErrorAction SilentlyContinue
    Write-Host "Klick removido (histórico e preferências mantidos em $dataDir)."
    return
}

if (-not (Test-Path $pythonw)) { throw "Venv não encontrado. Rode: py -m venv .venv; .venv\Scripts\pip install -e ." }

New-Item -ItemType Directory -Force $dataDir | Out-Null
$iconTmp = Join-Path $env:TEMP "klick-icon"
& $python (Join-Path $PSScriptRoot "prepare.py") $iconTmp | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o ícone" }
Copy-Item (Join-Path $iconTmp "klick.ico") $icon -Force

$shell = New-Object -ComObject WScript.Shell
foreach ($path in $shortcuts.Keys) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $pythonw
    $link.Arguments = ("-m klick " + $shortcuts[$path]).Trim()
    $link.WorkingDirectory = $root
    $link.IconLocation = $icon
    $link.Description = "Klick: captura de tela"
    $link.Save()
}

Set-ItemProperty $runKey -Name "Klick" -Value "`"$pythonw`" -m klick --startup"
# Sem isso o Windows 11 abre a Ferramenta de Captura junto com o Klick (vale após sair e entrar na conta).
Set-ItemProperty $keyboardKey -Name "PrintScreenKeyForSnippingEnabled" -Value 0 -Type DWord

Stop-Klick
Start-Process $pythonw -ArgumentList "-m", "klick" -WorkingDirectory $root
Write-Host "Klick instalado e aberto (ícone na bandeja). Atalhos: Menu Iniciar > Klick."
