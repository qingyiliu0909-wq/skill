<#
.SYNOPSIS
    Inject a VBA function into an xlsm module from a text file.
.DESCRIPTION
    Reads VBA code from a file (one line per row), inserts it at the specified
    line. The file should contain VBA code with Chinese text that will be 
    preserved because PowerShell reads the file as UTF-8 and passes UTF-16 to COM.
    
    NOTE: This is only safe for ASCII-only or small amounts of Chinese text.
    For large Chinese content, write the code directly in PowerShell inline strings.
.PARAMETER XlsmPath
    Full path to the .xlsm file.
.PARAMETER ModuleName
    Name of the VBA module to modify.
.PARAMETER FunctionFile
    Path to a text file containing VBA code (one line = one VBA line).
.PARAMETER InsertAfterLine
    Line number to insert AFTER (0 = insert at beginning).
.EXAMPLE
    .\inject_function.ps1 "C:\myfile.xlsm" "Module2" "new_func.txt" 994
#>

param(
    [Parameter(Mandatory=$true)][string]$XlsmPath,
    [Parameter(Mandatory=$true)][string]$ModuleName,
    [Parameter(Mandatory=$true)][string]$FunctionFile,
    [Parameter(Mandatory=$true)][int]$InsertAfterLine
)

# Read VBA code from file (UTF-8, preserve BOM if present)
$vbaLines = Get-Content -Path $FunctionFile -Encoding UTF8

if ($vbaLines.Count -eq 0) {
    Write-Error "Function file is empty"
    exit 1
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
    $wb = $excel.Workbooks.Open($XlsmPath)
    if ($wb.ReadOnly) {
        Write-Error "File is read-only"
        $wb.Close($false)
        exit 1
    }
    
    $vbProj = $wb.VBProject
    $mod = $null
    ForEach ($comp in $vbProj.VBComponents) {
        if ($comp.Name -eq $ModuleName) { $mod = $comp.CodeModule; break }
    }
    if (-not $mod) {
        Write-Error "Module '$ModuleName' not found"
        $wb.Close($false)
        exit 1
    }
    
    Write-Output "Module '$ModuleName': $($mod.CountOfLines) lines before"
    Write-Output "Inserting $($vbaLines.Count) lines after line $InsertAfterLine"
    
    for ($j = 0; $j -lt $vbaLines.Count; $j++) {
        $mod.InsertLines($InsertAfterLine + $j + 1, $vbaLines[$j])
    }
    
    Write-Output "Module now: $($mod.CountOfLines) lines"
    
    $before = (Get-Item $XlsmPath).LastWriteTime
    $wb.Save()
    $after = (Get-Item $XlsmPath).LastWriteTime
    
    if ($before -eq $after) {
        Write-Warning "Timestamp did NOT change after save!"
    } else {
        Write-Output "Saved successfully ($before -> $after)"
    }
    
    $wb.Close($false)
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
