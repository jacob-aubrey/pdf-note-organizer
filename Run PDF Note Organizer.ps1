# Launch the source app with its own Python and configured development library.
$organizerPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $organizerPython -PathType Leaf)) {
    $organizerPython = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
}
$organizerEntry = Join-Path $PSScriptRoot 'PDF Note Organizer.py'
if (-not (Test-Path -LiteralPath $organizerPython -PathType Leaf)) {
    Write-Error 'The project virtual environment is missing. Follow the setup instructions in README.md.'
    return
}

$organizerPreviousData = $env:PDF_NOTES_DATA_DIR
$organizerPreviousMigration = $env:PDF_NOTES_SKIP_LEGACY_IMPORT
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not $env:PDF_NOTES_DATA_DIR) {
        $env:PDF_NOTES_DATA_DIR = Join-Path $PSScriptRoot '.local-data'
        $organizerLegacyData = Join-Path (Split-Path $PSScriptRoot -Parent) '.local-data'
        if (Test-Path -LiteralPath $organizerLegacyData -PathType Container) {
            $env:PDF_NOTES_DATA_DIR = $organizerLegacyData
        }
        $env:PDF_NOTES_SKIP_LEGACY_IMPORT = '1'
    }
    & $organizerPython $organizerEntry
}
finally {
    [Environment]::SetEnvironmentVariable('PDF_NOTES_DATA_DIR', $organizerPreviousData, 'Process')
    [Environment]::SetEnvironmentVariable('PDF_NOTES_SKIP_LEGACY_IMPORT', $organizerPreviousMigration, 'Process')
    Pop-Location
}
