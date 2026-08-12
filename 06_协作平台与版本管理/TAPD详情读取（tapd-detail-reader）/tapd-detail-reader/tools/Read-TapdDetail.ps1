[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TapdUrl,

    [ValidateSet('edge', 'chrome', 'chromium')]
    [string]$Browser
)

$ErrorActionPreference = 'Stop'
$script:ToolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:PlaywrightPackage = Join-Path $script:ToolRoot 'node_modules\playwright\package.json'

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found. Please install Node.js first.'
}

if (-not (Test-Path $script:PlaywrightPackage)) {
    throw 'TapdDetailReader dependencies are missing. Run .\.claude\skills\tapd-detail-reader\tools\Setup-TapdReader.ps1 first.'
}

Push-Location $script:ToolRoot
try {
    $nodeArgs = @('.\scripts\read-detail.js', '--url', $TapdUrl)
    if ($Browser) {
        $nodeArgs += @('--browser', $Browser)
    }

    & node @nodeArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 10) {
        throw 'TAPD login is required. Run .\.claude\skills\tapd-detail-reader\tools\Login-Tapd.ps1 first to refresh the cached session.'
    }

    if ($exitCode -ne 0) {
        throw "Read-TapdDetail failed with exit code $exitCode."
    }
}
finally {
    Pop-Location
}
