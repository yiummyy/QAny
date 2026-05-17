$ErrorActionPreference = 'Stop'
$file = 'c:\Q\Projects\QAny\QAny产研总结手册.md'

Copy-Item ($file + '.bak') $file -Force

$raw = [System.IO.File]::ReadAllText($file, [System.Text.UTF8Encoding]::new($false))

$nl = "`r`n"

# ============================================================
# Step 1: Capture three-10 content and remove it from three
# ============================================================

$pat1 = '(?s)(\r?\n\*\*\*\r?\n\r?\n## 10\. 评估、部署与运维.*?)(\r?\n\*\*\*\r?\n\r?\n# 四、RAG 实现细节)'
$m1 = [regex]::Match($raw, $pat1)

if (-not $m1.Success) {
    Write-Host 'Step 1 FAILED'
    exit 1
}

$blk1 = $m1.Groups[1].Value
$blk4 = $m1.Groups[2].Value
$body = $blk1 -replace '(?s)\r?\n\*\*\*\r?\n\r?\n## 10\. 评估、部署与运维\s*', ''
$raw = $raw.Replace($blk1 + $blk4, $blk4)
Write-Host 'Step 1 OK'

# ============================================================
# Step 2: Replace old 六 content with three-10 content
# ============================================================

$pat2 = '(?s)(# 六、评测体系.*?)(\r?\n\*\*\*\r?\n\r?\n# 七、成本管理)'
$m2 = [regex]::Match($raw, $pat2)

if (-not $m2.Success) {
    Write-Host 'Step 2 FAILED'
    exit 1
}

$oldSix = $m2.Groups[1].Value
$mk7 = $m2.Groups[2].Value
$newSix = '# 六、评测体系' + $nl + $nl + $body.TrimStart()
$raw = $raw.Replace($oldSix + $mk7, $newSix + $mk7)
Write-Host 'Step 2 OK'

# ============================================================
# Step 3: Merge 6+7 -> 安全与可靠性
# ============================================================

$pat3 = '(?s)(## 6\. 安全与可控性.*?)(\r?\n\*\*\*\r?\n\r?\n## 7\. 可靠性与弹性\s*)(.*?)(\r?\n\*\*\*\r?\n\r?\n## 8\. 性能与成本)'
$m3 = [regex]::Match($raw, $pat3)

if (-not $m3.Success) {
    Write-Host 'Step 3 FAILED'
    exit 1
}

$s6raw = $m3.Groups[1].Value
$s7sep = $m3.Groups[2].Value
$s7raw = $m3.Groups[3].Value
$s8raw = $m3.Groups[4].Value

$s6body = $s6raw -replace '(?s)^## 6\. 安全与可控性\s*', ''
$s7body = $s7raw -replace '(?s)^## 7\. 可靠性与弹性\s*', ''

$merged = '## 安全与可靠性' + $nl + $nl + $s6body.Trim() + $nl + $nl + '***' + $nl + $nl + $s7body.Trim()
$oldBlob = $s6raw + $s7sep + $s7raw
$raw = $raw.Replace($oldBlob + $s8raw, $merged + $s8raw)
Write-Host 'Step 3 OK'

# Write
[System.IO.File]::WriteAllText($file, $raw, [System.Text.UTF8Encoding]::new($false))
Write-Host ('ALL DONE. Lines: ' + ($raw -split "`n").Count)
