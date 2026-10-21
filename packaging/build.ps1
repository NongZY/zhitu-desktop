param([string]$InnoCompiler = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$buildPython = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
Push-Location $projectRoot
try {
    & npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build/pyinstaller packaging/zhitu.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
    Copy-Item -LiteralPath packaging/TESTING.txt -Destination 'dist/ZhiTu-0.2.0-test.1/使用说明.txt'
    if ($InnoCompiler) {
        & $InnoCompiler packaging/installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    }
} finally { Pop-Location }
