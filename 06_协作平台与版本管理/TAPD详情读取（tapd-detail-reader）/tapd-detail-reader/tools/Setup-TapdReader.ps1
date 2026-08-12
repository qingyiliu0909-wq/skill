[CmdletBinding()]
param(
    [ValidateSet('edge', 'chrome', 'chromium')]
    [string]$Browser
)

$ErrorActionPreference = 'Stop'
$script:ToolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:PlaywrightPackage = Join-Path $script:ToolRoot 'node_modules\playwright\package.json'

function Get-NpmCommand {
    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCmd) {
        return $npmCmd.Source
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        return $npm.Source
    }

    throw 'npm was not found. Please install Node.js and npm first.'
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found. Please install Node.js first.'
}

if (-not (Test-Path $script:PlaywrightPackage)) {
    $npmCommand = Get-NpmCommand
    Push-Location $script:ToolRoot
    try {
        $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
        & $npmCommand install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

$nodeArgs = @('.\scripts\ensure-browser.js')
if ($Browser) {
    $nodeArgs += @('--browser', $Browser)
}

Push-Location $script:ToolRoot
try {
    & node @nodeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Browser setup failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
