# Project-local Python bootstrap. ASCII so Windows PowerShell 5.1 reads it reliably.
param([string]$ProjectRoot = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$PythonVersion = '3.13.12'
$PythonHash = '9089c1f0d720f7c913cd4caf600e6761b0a4d5b90ccf34229fe418ff64a5da5f'
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$PythonRoot = Join-Path $RuntimeRoot ('python-' + $PythonVersion)
$PythonExe = Join-Path $PythonRoot 'python.exe'
$Stage = $null
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Windows x64 is required.'
    }
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    if (-not (Test-Path $PythonExe)) {
        Write-Host '[1/3] Downloading private Python runtime (32 MB, first run only)...'
        $Stage = Join-Path $RuntimeRoot ('python-install-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $Stage | Out-Null
        $Archive = Join-Path $Stage 'python.zip'
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 180 -Uri ('https://www.python.org/ftp/python/' + $PythonVersion + '/python-' + $PythonVersion + '-amd64.zip') -OutFile $Archive
        if ((Get-FileHash $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PythonHash) {
            throw 'Python download checksum mismatch. Nothing was installed.'
        }
        Write-Host '[2/3] Extracting verified Python runtime...'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Unpacked = Join-Path $Stage 'unpacked'
        [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Unpacked)
        if (-not (Test-Path (Join-Path $Unpacked 'python.exe'))) { throw 'Invalid Python package.' }
        if (Test-Path $PythonRoot) { Remove-Item -Recurse -Force $PythonRoot }
        Move-Item $Unpacked $PythonRoot
    }
    # Ignore registry, global Python, PYTHONPATH and user-site packages.
    $SearchPaths = @('.', 'Lib', 'DLLs', 'Lib/site-packages', [IO.Path]::GetFullPath($ProjectRoot), 'import site')
    [IO.File]::WriteAllLines((Join-Path $PythonRoot 'python313._pth'), $SearchPaths, (New-Object Text.UTF8Encoding($false)))
    $ReqFile = Join-Path $ProjectRoot 'requirements.txt'
    $ReqHash = (Get-FileHash $ReqFile -Algorithm SHA256).Hash
    $Marker = Join-Path $PythonRoot 'dependencies.sha256'
    $HaveHash = if (Test-Path $Marker) { (Get-Content $Marker -Raw).Trim() } else { '' }
    if ($HaveHash -ne $ReqHash) {
        Write-Host '[3/3] Preparing private Python dependencies...'
        & $PythonExe -X utf8 -m pip --isolated install --disable-pip-version-check --no-warn-script-location --only-binary=:all: -r $ReqFile
        if ($LASTEXITCODE -ne 0) { throw 'Dependency preparation failed. See the message above.' }
        & $PythonExe -X utf8 -c 'import sys; print(sys.executable); print(sys.path); import serial.tools.list_ports, py7zr, amsrfid.web'
        if ($LASTEXITCODE -ne 0) { throw 'Private runtime import validation failed.' }
        $ReqHash | Set-Content -Encoding ASCII $Marker
    }
    Write-Host '[OK] Private runtime ready. Existing Python/ProxSpace installations are not used.'
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($Stage -and (Test-Path $Stage)) { Remove-Item -Recurse -Force $Stage }
}
