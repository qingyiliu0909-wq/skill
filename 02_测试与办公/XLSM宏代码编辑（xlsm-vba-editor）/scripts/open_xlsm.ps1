<#
.SYNOPSIS
    Open an xlsm file via Excel COM and print module information.
.DESCRIPTION
    Opens the specified xlsm, lists all VBA components with line counts,
    and optionally outputs details for a specific module.
.PARAMETER XlsmPath
    Full path to the .xlsm file.
.PARAMETER ModuleName
    If specified, prints additional details for this module.
.EXAMPLE
    .\open_xlsm.ps1 "C:\myfile.xlsm"
    .\open_xlsm.ps1 "C:\myfile.xlsm" -ModuleName "Module1"
#>

param(
    [Parameter(Mandatory=$true)][string]$XlsmPath,
    [string]$ModuleName
)

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
    $wb = $excel.Workbooks.Open($XlsmPath)
    Write-Output "File: $XlsmPath"
    Write-Output "ReadOnly: $($wb.ReadOnly)"
    
    $vbProj = $wb.VBProject
    Write-Output "`nVBA Components:"
    
    $target = $null
    ForEach ($comp in $vbProj.VBComponents) {
        $lines = $comp.CodeModule.CountOfLines
        Write-Output "  $($comp.Name) (Type=$($comp.Type)): $lines lines"
        if ($ModuleName -and $comp.Name -eq $ModuleName) {
            $target = $comp.CodeModule
        }
    }
    
    if ($target) {
        Write-Output "`nModule '$ModuleName' detail:"
        Write-Output "  Total lines: $($target.CountOfLines)"
        Write-Output "  First 5 non-empty lines:"
        $shown = 0
        for ($i = 1; $i -le $target.CountOfLines -and $shown -lt 5; $i++) {
            $line = $target.Lines($i, 1).TrimEnd("`r`n")
            if ($line.Trim()) {
                Write-Output "    $($i): $($line.Substring(0, [Math]::Min(80, $line.Length)))"
                $shown++
            }
        }
    }
    
    $wb.Close($false)
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
