[CmdletBinding()]
param(
    [string]$TapdUrl = 'https://www.tapd.cn/',
    [ValidateSet('edge', 'chrome', 'chromium')]
    [string]$Browser
)

$ErrorActionPreference = 'Stop'
$script:ToolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$setupArgs = @{}
if ($Browser) {
    $setupArgs.Browser = $Browser
}

& (Join-Path $script:ToolRoot 'Setup-TapdReader.ps1') @setupArgs

Push-Location $script:ToolRoot
try {
    $nodeArgs = @('.\scripts\login.js', '--url', $TapdUrl)
    if ($Browser) {
        $nodeArgs += @('--browser', $Browser)
    }

    & node @nodeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "TAPD login flow failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
