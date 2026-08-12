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

function CountOf {
    param($obj)
    if ($null -eq $obj) { return 0 }
    if ($obj -is [System.Array]) { return $obj.Length }
    if ($obj.PSObject.Properties.Match('Count').Count -gt 0) { return [int]$obj.Count }
    return @($obj).Count
}

$uniq = $data.UniqueGrandTotals
$sumPL = $data.SumOfPerLevel

[void]$sb.AppendLine("# Scene Memory Check Results (GetResourceSizeBytes)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("- **MainLevel**: $($data.MainLevel)")
[void]$sb.AppendLine("- **Platform**: $($data.Platform)")
[void]$sb.AppendLine("- **MemoryMode**: $($data.MemoryMode)")
[void]$sb.AppendLine("- **IncludeEngineRefs**: $($data.IncludeEngineRefs)")
[void]$sb.AppendLine("- **CheckTime**: $($data.CheckTime)")
[void]$sb.AppendLine("- **SubLevelCount**: $($data.SubLevelCount)")
if ($null -ne $data.LoadFailedPackageCount) {
    [void]$sb.AppendLine("- **LoadFailedPackageCount**: $($data.LoadFailedPackageCount)")
}
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## UniqueGrandTotals (cross-sublevel deduplicated)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("- **StaticMesh**: $($uniq.StaticMeshMemoryHuman)  (UniqueMeshes=$($uniq.UniqueStaticMeshCount))")
[void]$sb.AppendLine("- **Texture**: $($uniq.TextureMemoryHuman)  (UniqueTexPkgs=$($uniq.UniqueTexturePackageCount))")
[void]$sb.AppendLine("- **Material**: $($uniq.MaterialMemoryHuman)  (UniqueMatPkgs=$($uniq.UniqueMaterialPackageCount))")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## SumOfPerLevel (shared resources counted multiple times)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("- **StaticMesh**: $($sumPL.StaticMeshMemoryHuman)")
[void]$sb.AppendLine("- **Texture**: $($sumPL.TextureMemoryHuman)")
[void]$sb.AppendLine("- **Material**: $($sumPL.MaterialMemoryHuman)")
[void]$sb.AppendLine("")

$levels = $data.Levels
if ((CountOf $levels) -eq 0) {
    [void]$sb.AppendLine("No sub-levels found.")
    [System.IO.File]::WriteAllText($MdPath, $sb.ToString(), [System.Text.Encoding]::UTF8)
    Write-Host "Table written to: $MdPath"
    exit 0
}

function Write-TopSubLevelsTable {
    param(
        [string]$title,
        $rows,
        [System.Text.StringBuilder]$builder
    )
    [void]$builder.AppendLine("## $title")
    [void]$builder.AppendLine("")
    if ((CountOf $rows) -eq 0) {
        [void]$builder.AppendLine("(empty)")
        [void]$builder.AppendLine("")
        return
    }
    $idx = 0
    $indexed = @()
    foreach ($r in $rows) {
        $idx++
        $indexed += [pscustomobject]@{
            Rank = $idx
            LevelName = $r.LevelName
            StaticMesh = $r.StaticMeshMemoryHuman
            Texture = $r.TextureMemoryHuman
            Material = $r.MaterialMemoryHuman
            Total = $r.TotalMemoryHuman
        }
    }
    Write-Table -items $indexed -builder $builder -headers @("#", "LevelName", "StaticMesh", "Texture", "Material", "Total") -rowFunc {
        param($r)
        @("$($r.Rank)", "$($r.LevelName)", "$($r.StaticMesh)", "$($r.Texture)", "$($r.Material)", "$($r.Total)")
    }
    [void]$builder.AppendLine("")
}

$top = $data.TopSubLevels
if ($null -ne $top) {
    Write-TopSubLevelsTable -title "Top5 Sub-Levels by Total Memory" -rows $top.ByTotalMemoryBytes -builder $sb
    Write-TopSubLevelsTable -title "Top5 Sub-Levels by StaticMesh Memory" -rows $top.ByStaticMeshMemoryBytes -builder $sb
    Write-TopSubLevelsTable -title "Top5 Sub-Levels by Texture Memory" -rows $top.ByTextureMemoryBytes -builder $sb
    Write-TopSubLevelsTable -title "Top5 Sub-Levels by Material Memory" -rows $top.ByMaterialMemoryBytes -builder $sb
}

function Write-TopAssetsTable {
    param(
        [string]$title,
        $rows,
        [System.Text.StringBuilder]$builder
    )
    [void]$builder.AppendLine("## $title")
    [void]$builder.AppendLine("")
    if ((CountOf $rows) -eq 0) {
        [void]$builder.AppendLine("(empty)")
        [void]$builder.AppendLine("")
        return
    }
    $idx = 0
    $indexed = @()
    foreach ($r in $rows) {
        $idx++
        $indexed += [pscustomobject]@{
            Rank = $idx
            AssetName = $r.AssetName
            PackageName = $r.PackageName
            Memory = $r.MemoryHuman
        }
    }
    Write-Table -items $indexed -builder $builder -headers @("#", "AssetName", "PackageName", "Memory") -rowFunc {
        param($r)
        @("$($r.Rank)", "$($r.AssetName)", "$($r.PackageName)", "$($r.Memory)")
    }
    [void]$builder.AppendLine("")
}

$assets = $data.TopAssets
if ($null -ne $assets) {
    Write-TopAssetsTable -title "Top5 StaticMesh Assets (Global Dedup, Memory)" -rows $assets.ByStaticMeshMemoryBytes -builder $sb
    Write-TopAssetsTable -title "Top5 Texture Assets (Global Dedup, Memory)" -rows $assets.ByTextureMemoryBytes -builder $sb
    Write-TopAssetsTable -title "Top5 Material Assets (Global Dedup, Memory)" -rows $assets.ByMaterialMemoryBytes -builder $sb
}

[void]$sb.AppendLine("## Sub-Level Memory Summary")
[void]$sb.AppendLine("")

$idx = 0
$levelRows = @()
foreach ($r in $levels) {
    $idx++
    $levelRows += [pscustomobject]@{
        Rank = $idx
        LevelName = $r.LevelName
        StaticMesh = $r.StaticMeshMemoryHuman
        Texture = $r.TextureMemoryHuman
        Material = $r.MaterialMemoryHuman
        Total = $r.TotalMemoryHuman
        UniqueMesh = $r.UniqueStaticMeshCount
        TexPkgs = $r.TexturePackageCount
        MatPkgs = $r.MaterialPackageCount
    }
}

Write-Table -items $levelRows -builder $sb -headers @("#", "LevelName", "StaticMesh", "Texture", "Material", "Total", "UniqueMesh", "TexPkgs", "MatPkgs") -rowFunc {
    param($r)
    @("$($r.Rank)", "$($r.LevelName)", "$($r.StaticMesh)", "$($r.Texture)", "$($r.Material)", "$($r.Total)", "$($r.UniqueMesh)", "$($r.TexPkgs)", "$($r.MatPkgs)")
}
[void]$sb.AppendLine("")

foreach ($r in $levels) {
    [void]$sb.AppendLine("## Top5 LOD0 Triangles: $($r.LevelName)")
    [void]$sb.AppendLine("")

    $top5Tris = $r.Top5MeshesByLOD0TrianglesWeighted
    if ((CountOf $top5Tris) -eq 0) {
        [void]$sb.AppendLine("No StaticMesh found in this level.")
        [void]$sb.AppendLine("")
    } else {
        $mi = 0
        $meshRows = @()
        foreach ($m in $top5Tris) {
            $mi++
            $meshRows += [pscustomobject]@{
                Rank = $mi
                Pkg = $m.StaticMeshPackage
                Tris = $m.LOD0TrianglesWeighted
                Memory = $m.MemoryHuman
            }
        }

        Write-Table -items $meshRows -builder $sb -headers @("#", "StaticMeshPackage", "LOD0TrianglesWeighted", "Memory") -rowFunc {
            param($t)
            @("$($t.Rank)", "$($t.Pkg)", "$($t.Tris)", "$($t.Memory)")
        }
        [void]$sb.AppendLine("")
    }

    [void]$sb.AppendLine("## Top5 Memory-Weighted Meshes: $($r.LevelName)")
    [void]$sb.AppendLine("")

    $top5Mem = $r.Top5MeshesByMemoryWeighted
    if ((CountOf $top5Mem) -eq 0) {
        [void]$sb.AppendLine("No StaticMesh found in this level.")
        [void]$sb.AppendLine("")
        continue
    }

    $mi = 0
    $memRows = @()
    foreach ($m in $top5Mem) {
        $mi++
        $memRows += [pscustomobject]@{
            Rank = $mi
            Pkg = $m.StaticMeshPackage
            Weighted = $m.MemoryWeightedHuman
            Single = $m.MemoryHuman
        }
    }

    Write-Table -items $memRows -builder $sb -headers @("#", "StaticMeshPackage", "MemoryWeighted", "MemorySingle") -rowFunc {
        param($t)
        @("$($t.Rank)", "$($t.Pkg)", "$($t.Weighted)", "$($t.Single)")
    }
    [void]$sb.AppendLine("")
}

[System.IO.File]::WriteAllText($MdPath, $sb.ToString(), [System.Text.Encoding]::UTF8)
Write-Host "Table written to: $MdPath"
