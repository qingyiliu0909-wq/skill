<#
.SYNOPSIS
    Find line numbers in a VBA module by pattern matching.
.DESCRIPTION
    Searches a VBA module for lines matching a regex pattern and outputs
    the line numbers. Use to locate insertion/modification points.
.PARAMETER XlsmPath
    Full path to the .xlsm file.
.PARAMETER ModuleName
    Name of the VBA module to search.
.PARAMETER Pattern
    Regex pattern to match (PowerShell regex syntax).
.PARAMETER FirstOnly
    If set, return only the first matching line number.
.EXAMPLE
    .\find_line.ps1 "C:\myfile.xlsm" "Module1" "Function MyFunc"
    .\find_line.ps1 "C:\myfile.xlsm" "Module2" "Dim SkipColumnNames" -FirstOnly
#>

param(
    [Parameter(Mandatory=$true)][string]$XlsmPath,
    [Parameter(Mandatory=$true)][string]$ModuleName,
    [Parameter(Mandatory=$true)][string]$Pattern,
    [switch]$FirstOnly
)

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
    $wb = $excel.Workbooks.Open($XlsmPath)
    $vbProj = $wb.VBProject
    
    $mod = $null
    ForEach ($comp in $vbProj.VBComponents) {
        if ($comp.Name -eq $ModuleName) { $mod = $comp.CodeModule; break }
    }
    if (-not $mod) {
        Write-Error "Module '$ModuleName' not found"
        return
    }
    
    $totalLines = $mod.CountOfLines
    $found = @()
    for ($i = 1; $i -le $totalLines; $i++) {
        $line = $mod.Lines($i, 1)
        if ($line -match $Pattern) {
            $found += $i
            Write-Output "$($i): $($line.TrimEnd("```r```n").Substring(0, [Math]::Min(80, $line.Length)))"
            if ($FirstOnly) { break }
        }
    }
    
    Write-Output "`nFound $($found.Count) match(es)"
    if ($found.Count -eq 0) { exit 1 }
    
    $wb.Close($false)
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
