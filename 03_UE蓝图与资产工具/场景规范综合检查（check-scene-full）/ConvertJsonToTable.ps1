param(
    [Parameter(Mandatory=$true)]
    [string]$JsonPath
)

$MdPath = [System.IO.Path]::ChangeExtension($JsonPath, ".md")
$raw = [System.IO.File]::ReadAllText($JsonPath, [System.Text.Encoding]::UTF8)
$data = $raw | ConvertFrom-Json

$sb = New-Object System.Text.StringBuilder

function Get-DisplayWidth {
    param([string]$s)
    $w = 0
    foreach ($c in $s.ToCharArray()) {
        $code = [int]$c
        if (($code -ge 0x2E80 -and $code -le 0x9FFF) -or
            ($code -ge 0xF900 -and $code -le 0xFAFF) -or
            ($code -ge 0xFF00 -and $code -le 0xFF60) -or
            ($code -ge 0xFFE0 -and $code -le 0xFFE6)) {
            $w += 2
        } else {
            $w += 1
        }
    }
    return $w
}

function PadRightByDisplay {
    param([string]$s, [int]$targetWidth)
    $dw = Get-DisplayWidth $s
    $pad = $targetWidth - $dw
    if ($pad -lt 0) { $pad = 0 }
    return $s + (" " * $pad)
}

function Write-Table {
    param($items, [System.Text.StringBuilder]$builder, [string[]]$headers, [scriptblock]$rowFunc)

    $allRows = New-Object System.Collections.ArrayList
    [void]$allRows.Add($headers)

    foreach ($r in $items) {
        $row = & $rowFunc $r
        [void]$allRows.Add($row)
    }

    $colCount = $headers.Count
    $colWidths = New-Object int[] $colCount
    foreach ($row in $allRows) {
        for ($c = 0; $c -lt $colCount; $c++) {
            $dw = Get-DisplayWidth "$($row[$c])"
            if ($dw -gt $colWidths[$c]) {
                $colWidths[$c] = $dw
            }
        }
    }

    $isFirst = $true
    foreach ($row in $allRows) {
        $cells = New-Object System.Collections.ArrayList
        for ($c = 0; $c -lt $colCount; $c++) {
            [void]$cells.Add((PadRightByDisplay "$($row[$c])" $colWidths[$c]))
        }
        [void]$builder.AppendLine("| " + ($cells -join " | ") + " |")
        if ($isFirst) {
            $sepCells = New-Object System.Collections.ArrayList
            for ($c = 0; $c -lt $colCount; $c++) {
                [void]$sepCells.Add("-" * $colWidths[$c])
            }
            [void]$builder.AppendLine("| " + ($sepCells -join " | ") + " |")
            $isFirst = $false
        }
    }
}

[void]$sb.AppendLine("# Scene Full Check Results")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("- **CheckTime**: $($data.CheckTime)")
[void]$sb.AppendLine("- **TotalChecked**: $($data.TotalChecked)")
[void]$sb.AppendLine("- **Error**: $($data.TotalErrors)")
[void]$sb.AppendLine("- **Warning**: $($data.TotalWarnings)")
[void]$sb.AppendLine("- **Info**: $($data.TotalInfo)")
[void]$sb.AppendLine("")

if ($data.Results.Count -eq 0) {
    [void]$sb.AppendLine("All checks passed.")
    [System.IO.File]::WriteAllText($MdPath, $sb.ToString(), [System.Text.Encoding]::UTF8)
    Write-Host "Table written to: $MdPath"
    exit 0
}

$checkTypes = @("LevelBounds", "Mobility", "Batching", "ReflectionSphere", "CrossLevel", "Decal", "SimpleRuntimeActor", "Layer", "LevelProxy")

$errorItems = New-Object System.Collections.ArrayList
$warningItems = New-Object System.Collections.ArrayList
$infoItems = New-Object System.Collections.ArrayList

foreach ($r in $data.Results) {
    if ($r.Severity -eq "Error") {
        [void]$errorItems.Add($r)
    } elseif ($r.Severity -eq "Warning") {
        [void]$warningItems.Add($r)
    } else {
        [void]$infoItems.Add($r)
    }
}

if ($errorItems.Count -gt 0) {
    [void]$sb.AppendLine("## Error (must fix): $($errorItems.Count)")
    [void]$sb.AppendLine("")
    Write-Table -items $errorItems -builder $sb -headers @("#", "LevelName", "CheckType", "RuleType", "ActorName", "Description") -rowFunc {
        param($r)
        @("$($errorItems.IndexOf($r) + 1)", "$($r.LevelName)", "$($r.CheckType)", "$($r.RuleType)", $(if ($r.ActorName) { "$($r.ActorName)" } else { "-" }), "$($r.Description)")
    }
    [void]$sb.AppendLine("")
}

if ($warningItems.Count -gt 0) {
    [void]$sb.AppendLine("## Warning (attention): $($warningItems.Count)")
    [void]$sb.AppendLine("")
    Write-Table -items $warningItems -builder $sb -headers @("#", "LevelName", "CheckType", "RuleType", "ActorName", "Description") -rowFunc {
        param($r)
        @("$($warningItems.IndexOf($r) + 1)", "$($r.LevelName)", "$($r.CheckType)", "$($r.RuleType)", $(if ($r.ActorName) { "$($r.ActorName)" } else { "-" }), "$($r.Description)")
    }
    [void]$sb.AppendLine("")
}

if ($infoItems.Count -gt 0) {
    [void]$sb.AppendLine("## Info: $($infoItems.Count)")
    [void]$sb.AppendLine("")
    Write-Table -items $infoItems -builder $sb -headers @("#", "LevelName", "CheckType", "RuleType", "Description") -rowFunc {
        param($r)
        @("$($infoItems.IndexOf($r) + 1)", "$($r.LevelName)", "$($r.CheckType)", "$($r.RuleType)", "$($r.Description)")
    }
    [void]$sb.AppendLine("")
}

[System.IO.File]::WriteAllText($MdPath, $sb.ToString(), [System.Text.Encoding]::UTF8)
Write-Host "Table written to: $MdPath"
