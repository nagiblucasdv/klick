<#
Gera o instalador do Klick: dist\Klick-Setup-<versão>.exe

    .\packaging\build.ps1                 # usa o ffmpeg do PATH (winget install Gyan.FFmpeg.Essentials)
    .\packaging\build.ps1 -SkipTests
    .\packaging\build.ps1 -FfmpegDir C:\ffmpeg-essentials_build

Usa um venv próprio (.venv-build, criado na primeira vez) com Python 3.12: o PyInstaller cai com
erros aleatórios no 3.14. Precisa do Inno Setup 6 (winget install JRSoftware.InnoSetup).
#>
param(
    [string]$FfmpegDir,
    [string]$PythonVersion = "3.12",
    [switch]$SkipTests
)

# Não "Stop": no PowerShell 5.1 o log que PyInstaller/pytest mandam ao stderr viraria erro.
# Cada passo é conferido pelo código de saída em Check.
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $root ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"
$build = Join-Path $root "build"

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what falhou (código $LASTEXITCODE)" } }

if (-not (Test-Path $python)) {
    Step "Criando .venv-build com Python $PythonVersion"
    py "-$PythonVersion" -m venv $venv
    Check "py -$PythonVersion -m venv (instale com: winget install Python.Python.$PythonVersion)"
}
Step "Dependências"
& $python -m pip install -q --disable-pip-version-check -e "$root[dev]" pyinstaller
Check "pip install"

# --- ffmpeg: pasta do build "essentials" do gyan.dev (bin\ffmpeg.exe + LICENSE) -------------------
if (-not $FfmpegDir) {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "ffmpeg não encontrado. Rode: winget install Gyan.FFmpeg.Essentials (ou passe -FfmpegDir)" }
    $exe = Get-Item $cmd.Source
    if ($exe.LinkType) { $exe = Get-Item $exe.Target }  # o winget põe um link simbólico no PATH
    $FfmpegDir = $exe.Directory.Parent.FullName
}
$ffmpegExe = Join-Path $FfmpegDir "bin\ffmpeg.exe"
$ffmpegLicense = Join-Path $FfmpegDir "LICENSE"
if (-not (Test-Path $ffmpegExe) -or -not (Test-Path $ffmpegLicense)) { throw "Esperava bin\ffmpeg.exe e LICENSE em $FfmpegDir" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado. Rode: winget install JRSoftware.InnoSetup" }

Push-Location $root
try {
    if (-not $SkipTests) {
        Step "Testes"
        & $python -m pytest -q tests
        Check "pytest"
    }

    Step "Modelos do RapidOCR"
    # Baixa os modelos para dentro do pacote rapidocr; o PyInstaller leva junto e o app nunca baixa nada.
    & $python -c "from rapidocr import RapidOCR; RapidOCR(params={'Global.log_level': 'warning'})"
    Check "RapidOCR"

    Step "Ícone e versão"
    $version = (& $python packaging\prepare.py $build | Select-Object -Last 1).Trim()
    Check "prepare.py"

    Step "ffmpeg ($FfmpegDir)"
    New-Item -ItemType Directory -Force (Join-Path $build "ffmpeg") | Out-Null
    Copy-Item $ffmpegExe, $ffmpegLicense (Join-Path $build "ffmpeg") -Force

    Step "PyInstaller"
    & $python -m PyInstaller packaging\klick.spec --noconfirm --clean --log-level WARN `
        --distpath dist --workpath (Join-Path $build "pyinstaller")
    Check "PyInstaller"

    Step "Autoteste do executável"
    # Confere dentro do Klick.exe empacotado: fontes, ícones e os dois motores de leitura.
    $selftest = Start-Process (Join-Path $root "dist\Klick\Klick.exe") -ArgumentList "--selftest" -Wait -PassThru
    if ($selftest.ExitCode -ne 0) { throw "Autoteste do executável falhou (código $($selftest.ExitCode))" }

    Step "Inno Setup"
    & $iscc /Q "/DAppVersion=$version" packaging\klick.iss
    Check "ISCC"

    $setup = Get-Item (Join-Path $root "dist\Klick-Setup-$version.exe")
    Step ("Pronto: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB))
}
finally {
    Pop-Location
}
