$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze fallita' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Test falliti' }
python -m PyInstaller --noconfirm --clean --onedir --windowed --name VintDesk --icon assets/vintdesk.ico --add-data "assets;assets" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build fallita' }
$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $compiler)) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $compiler = $command.Source }
    else { throw 'Installa Inno Setup 6 prima di creare il setup.' }
}
& $compiler 'installer\vintdesk.iss'
if ($LASTEXITCODE -ne 0) { throw 'Creazione installer fallita' }
Write-Host 'Installer pronto in output\VintDesk-Setup-1.0.0.exe'
