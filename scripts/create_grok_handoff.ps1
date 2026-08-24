[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$sourceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$statePath = Join-Path $sourceRoot "project_state.json"
$entryPath = Join-Path $sourceRoot "GROK_START_HERE.md"

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "project_state.json was not found. Run this script from the project copy."
}
if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
    throw "GROK_START_HERE.md was not found. Handoff source is incomplete."
}

Push-Location $sourceRoot
try {
    Write-Host "[1/5] Running automated tests..."
    & py -B -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) {
        throw "Automated tests failed. Handoff package was not created."
    }

    Write-Host "[2/5] Verifying project state..."
    & py scripts/verify_project_state.py
    if ($LASTEXITCODE -ne 0) {
        throw "Project state verification failed. Handoff package was not created."
    }

    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $packageName = "GameArchiveManager-$($state.project.version)-RC-Grok-Handoff-$timestamp"
    $outputRoot = Join-Path $sourceRoot "handoff_output"
    $stagingRoot = Join-Path $outputRoot $packageName
    $zipPath = Join-Path $outputRoot "$packageName.zip"

    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    $excludedTopDirectories = @(
        ".git",
        ".vm_gate",
        "build",
        "build_rc_validation",
        "dist",
        "dist_rc_validation",
        "handoff_output"
    )
    $excludedExactFiles = @(
        "config.json",
        "task_history.json"
    )
    $excludedExtensions = @(
        ".exe", ".dll", ".lib", ".pdb", ".pyc", ".pyo", ".log", ".zip", ".rar", ".7z", ".lz4"
    )

    Write-Host "[3/5] Copying sanitized project files..."
    $sourceFiles = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force
    foreach ($file in $sourceFiles) {
        $relative = [System.IO.Path]::GetRelativePath($sourceRoot, $file.FullName)
        $segments = $relative -split '[\\/]'
        $top = $segments[0]

        if ($excludedTopDirectories -contains $top) { continue }
        if ($top -like ".build_venv*") { continue }
        if ($segments -contains "__pycache__") { continue }
        if ($segments -contains ".pytest_cache") { continue }
        if ($relative -like "tools\lz4_win64_v1_10_0\*") { continue }
        if ($relative -like "logs\*" -and $relative -ne "logs\__init__.py") { continue }
        if ($excludedExactFiles -contains $file.Name) { continue }
        if ($excludedExtensions -contains $file.Extension.ToLowerInvariant()) { continue }

        $destination = Join-Path $stagingRoot $relative
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }

    $forbiddenBinaries = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Where-Object {
        $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".lib")
    }
    if ($forbiddenBinaries) {
        throw "External binary found in sanitized handoff: $($forbiddenBinaries.FullName -join ', ')"
    }

    $forbiddenRuntimeData = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Where-Object {
        $_.Extension -eq ".log" -or $_.Name -in @("config.json", "task_history.json")
    }
    if ($forbiddenRuntimeData) {
        throw "Runtime data found in sanitized handoff: $($forbiddenRuntimeData.FullName -join ', ')"
    }

    Write-Host "[4/5] Creating auditable manifest..."
    $manifestFiles = @()
    foreach ($file in (Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Sort-Object FullName)) {
        $manifestFiles += [ordered]@{
            path = [System.IO.Path]::GetRelativePath($stagingRoot, $file.FullName).Replace('\\', '/')
            size = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

    $manifest = [ordered]@{
        schema_version = 1
        created_at = (Get-Date).ToString("o")
        purpose = "Grok Build project takeover"
        project = [ordered]@{
            name = $state.project.name
            version = $state.project.version
            build_type = $state.project.build_type
            phase = $state.project.phase
        }
        verification = [ordered]@{
            automated_tests = "PASS"
            test_count = $state.test_baseline.last_verified_count
            project_state = "PASS"
            clean_windows_11_vm = $state.release_gates.clean_windows_11_vm
            release_readiness = if ($state.release_gates.clean_windows_11_vm) { "RECHECK_REQUIRED" } else { "NO-GO" }
        }
        exclusions = @(
            "VM gate materials and password fixtures",
            "runtime logs/history/user config",
            "build environments and build artifacts",
            "external tool binaries",
            "caches and Git metadata"
        )
        files = $manifestFiles
    }
    $manifestJson = $manifest | ConvertTo-Json -Depth 8
    $manifestJson | Out-File -LiteralPath (Join-Path $stagingRoot "HANDOFF_MANIFEST.json") -Encoding utf8

    Write-Host "[5/5] Creating ZIP..."
    Compress-Archive -LiteralPath $stagingRoot -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()

    Write-Host ""
    Write-Host "HANDOFF_READY"
    Write-Host "Folder: $stagingRoot"
    Write-Host "ZIP:    $zipPath"
    Write-Host "SHA256: $zipHash"
    Write-Host ""
    Write-Host "Upload the ZIP to Grok Build, then paste GROK_INITIAL_PROMPT.md as the first instruction."
}
finally {
    Pop-Location
}
