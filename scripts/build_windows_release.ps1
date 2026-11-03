<#
.SYNOPSIS
Build an unsigned Windows x64 candidate zip without touching existing dist/.
.DESCRIPTION
Requires x64 Windows Python 3.10+ with Tk and requirements-build.txt installed:
  python -m pip install -r requirements-build.txt
  ./scripts/build_windows_release.ps1 -ExpectedVersion 0.3.0
Use -PythonExe <venv python.exe> for an explicit interpreter. Version always comes
from version.py; ExpectedVersion is an optional guard, never a version override.
Every invocation owns a new directory under ignored .vm_gate/release_artifacts.
No downloads, external unpacker binaries, user data or local documents are copied.
This is a repeatable build recipe, not a claim of byte-identical Windows binaries.
#>
[CmdletBinding()]
param(
    [string]$PythonExe = 'python',
    [string]$ExpectedVersion = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows x64 is required.' }
$PythonExe = (Get-Command $PythonExe -ErrorAction Stop).Source
$projectRoot = Split-Path -Parent $PSScriptRoot

# Parse version literals without importing arbitrary project code or user state.
$versionCode = @'
import ast, pathlib, struct, sys
if sys.platform != "win32" or struct.calcsize("P") != 8:
    raise SystemExit("Use an x64 Windows Python interpreter")
tree = ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
          if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
print(values["APP_VERSION"])
'@
$version = $versionCode | & $PythonExe -I -B - (Join-Path $projectRoot 'version.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not read version.py with x64 Windows Python.' }
$version = "$version".Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(rc\d+)?$') { throw "Unsupported version: $version" }
if ($ExpectedVersion -and $ExpectedVersion -cne $version) {
    throw "version.py APP_VERSION is $version; expected $ExpectedVersion. No version was changed."
}
& $PythonExe -I -B -c 'import PyInstaller, tkinter; tkinter.Tcl()'
if ($LASTEXITCODE -ne 0) { throw 'Install requirements-build.txt and a Python distribution with Tk first.' }

$artifactRoot = Join-Path $projectRoot '.vm_gate/release_artifacts'
[void][System.IO.Directory]::CreateDirectory($artifactRoot)
# GUID and CreateDirectory without -Force ensure historical outputs are never reused.
$runDirectory = Join-Path $artifactRoot ("windows-" + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $runDirectory) { throw 'Build directory already exists.' }
[void](New-Item -ItemType Directory -Path $runDirectory)
$sourceDirectory = Join-Path $runDirectory 'source'
$distDirectory = Join-Path $runDirectory 'dist'
$workDirectory = Join-Path $runDirectory 'work'
$releaseName = "GameArchiveManager-$version-windows-x64"
$zipPath = Join-Path $runDirectory "$releaseName.zip"

# Staging is an exact product-source allowlist, independent of dirty local files,
# config.json, password stores, archives, documentation and tools/*.exe or *.dll.
$stageCode = @'
import pathlib, shutil, sys
root, stage = map(pathlib.Path, sys.argv[1:])
packages = {"analyzer", "application", "cleanup", "config", "coordinator", "execution",
            "extractor", "gui", "history", "logging_system", "organizer", "password",
            "pipeline", "recovery", "report", "rules", "scanner", "security", "task", "tools"}
files = [root / "main.py", root / "version.py", root / "LICENSE"]
for package in sorted(packages):
    files.extend(sorted((root / package).rglob("*.py")))
for source in files:
    if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
        raise SystemExit("Source path escapes repository")
    if any(part == "__pycache__" for part in source.parts):
        continue
    target = stage / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
(stage / "gui_launcher.py").write_text("from gui.app import main\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
'@
$stageCode | & $PythonExe -I -B - $projectRoot $sourceDirectory
if ($LASTEXITCODE -ne 0) { throw 'Product-source staging failed.' }

# The existing spec builds a console main.py only. Keep it untouched and generate
# this dual-entrypoint spec inside the invocation-owned build directory instead.
$spec = @'
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks.tcl_tk import tcltk_info
import os
if not tcltk_info.available:
    raise RuntimeError('Working Tcl/Tk is required; refusing a GUI-less package')
gui = Analysis([os.path.join(SPECPATH, 'gui_launcher.py')], pathex=[SPECPATH], binaries=[], datas=[], hiddenimports=[])
cli = Analysis([os.path.join(SPECPATH, 'main.py')], pathex=[SPECPATH], binaries=[], datas=[], hiddenimports=[])
gui_pyz = PYZ(gui.pure)
cli_pyz = PYZ(cli.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True,
              name='GameArchiveManager', console=False, debug=False, strip=False, upx=False)
cli_exe = EXE(cli_pyz, cli.scripts, [], exclude_binaries=True,
              name='GameArchiveManager-CLI', console=True, debug=False, strip=False, upx=False)
COLLECT(gui_exe, cli_exe, gui.binaries, cli.binaries, gui.datas, cli.datas,
        name='RELEASE_DIRECTORY', strip=False, upx=False)
'@
$spec = $spec.Replace('RELEASE_DIRECTORY', $releaseName)
$specPath = Join-Path $sourceDirectory 'candidate.spec'
[System.IO.File]::WriteAllText($specPath, $spec, [System.Text.UTF8Encoding]::new($false))

$previousCache = $env:PYINSTALLER_CONFIG_DIR
try {
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $runDirectory 'pyinstaller-cache'
    Push-Location $projectRoot
    try {
        & $PythonExe -I -B -m PyInstaller --distpath $distDirectory --workpath $workDirectory $specPath
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed; invocation directory retained for inspection.' }
    } finally { Pop-Location }
} finally { $env:PYINSTALLER_CONFIG_DIR = $previousCache }

$releaseDirectory = Join-Path $distDirectory $releaseName
Copy-Item -LiteralPath (Join-Path $sourceDirectory 'LICENSE') -Destination $releaseDirectory
# Fail closed if the PyInstaller result ever gains an external archive binary.
$inspectCode = @'
import pathlib, struct, sys
root = pathlib.Path(sys.argv[1])
for required in ("_internal/_tkinter.pyd", "_internal/_tcl_data/init.tcl", "_internal/_tk_data/tk.tcl"):
    assert (root / required).is_file(), "Missing bundled Tk runtime: " + required
for filename, expected in (("GameArchiveManager.exe", 2), ("GameArchiveManager-CLI.exe", 3)):
    data = (root / filename).read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    assert data[:2] == b"MZ" and data[pe:pe+4] == b"PE\0\0", filename
    assert struct.unpack_from("<H", data, pe + 4)[0] == 0x8664, "Expected x64 PE"
    assert struct.unpack_from("<H", data, pe + 24 + 68)[0] == expected, "Wrong GUI/console subsystem"
for file in root.rglob("*"):
    assert not file.is_symlink(), "Unexpected symlink"
    name = file.name.lower()
    assert name not in {"7z.exe", "7za.exe", "7zz.exe", "7z.dll", "7za.dll", "7zxa.dll", "unrar.exe", "winrar.exe", "lz4.exe"}, "External unpacker in package"
    assert file.suffix.lower() != ".exe" or file.relative_to(root).as_posix() in {"GameArchiveManager.exe", "GameArchiveManager-CLI.exe"}, "Unexpected executable"
    assert name not in {"config.json", "task_history.json", ".env"}, "Local state in package"
print("PASS x64 GUI/console PE subsystems and package boundary")
'@
$inspectCode | & $PythonExe -I -B - $releaseDirectory
if ($LASTEXITCODE -ne 0) { throw 'Candidate package inspection failed.' }

# Use CreateNew rather than Compress-Archive -Force: an existing zip cannot be replaced.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $releaseDirectory, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)
$checksumPath = "$zipPath.sha256"
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText($checksumPath, "$hash  $releaseName.zip`n", [System.Text.Encoding]::ASCII)
if ($env:GITHUB_OUTPUT) {
    @("version=$version", "zip_path=$zipPath", "checksum_path=$checksumPath") |
        Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append
}
Write-Output "Candidate version: $version"
Write-Output "Zip: $zipPath"
Write-Output "SHA-256: $hash"
