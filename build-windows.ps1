$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze fallita' }
# Pilcrow Rounded (Indian Type Foundry, Free Font License): incorporabile nell'app, ma non ridistribuibile
# nel repository. La build lo scarica da Fontshare; senza font l'app usa Segoe UI.
$fonts = Join-Path $PSScriptRoot 'assets\fonts'
if (-not (Test-Path (Join-Path $fonts 'PilcrowRounded-Bold.otf'))) {
    New-Item -ItemType Directory -Force $fonts | Out-Null
    $zip = Join-Path $env:TEMP 'pilcrow-rounded.zip'
    $unpacked = Join-Path $env:TEMP 'pilcrow-rounded'
    Invoke-WebRequest 'https://api.fontshare.com/v2/fonts/download/pilcrow-rounded' -OutFile $zip
    Expand-Archive $zip $unpacked -Force
    foreach ($name in 'PilcrowRounded-Regular.otf', 'PilcrowRounded-Bold.otf') {
        Copy-Item (Get-ChildItem $unpacked -Recurse -Filter $name | Select-Object -First 1).FullName $fonts
    }
    Copy-Item (Get-ChildItem $unpacked -Recurse -Filter 'FFL.txt' | Select-Object -First 1).FullName (Join-Path $fonts 'LICENZA-FONT.txt')
}
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Test falliti' }
python -m PyInstaller --noconfirm --clean --onedir --windowed --name VintDesk --icon assets/vintdesk.ico --add-data "assets;assets" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build fallita' }
$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $compiler)) { $compiler = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $compiler)) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $compiler = $command.Source }
    else { throw 'Installa Inno Setup 6 prima di creare il setup.' }
}
& $compiler 'installer\vintdesk.iss'
if ($LASTEXITCODE -ne 0) { throw 'Creazione installer fallita' }
Write-Host 'Installer pronto in output\VintDesk-Setup-1.3.0.exe'
