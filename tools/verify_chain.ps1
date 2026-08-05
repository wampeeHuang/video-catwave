$ErrorActionPreference = "Stop"
$date = if ($args[0]) { $args[0] } else { (Get-Date).ToString("yyyy-MM-dd") }
Write-Output "=== verify-chain: $date ==="

$failures = @()
$warnings = @()

# ── Gate 1: Curation → Catwave 一致性 ──
$curationPath = "D:\workspace\_output\猫波信号站\视频\_curation\$date.json"
$catwavePath = "D:\workspace\evopearl-data\data\catwave\$date.json"

if (-not (Test-Path $curationPath)) {
    $failures += "GATE1: curation file not found: $curationPath"
} elseif (-not (Test-Path $catwavePath)) {
    $failures += "GATE1: catwave output not found: $catwavePath"
} else {
    try {
        $curation = Get-Content $curationPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $catwave = Get-Content $catwavePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $curCount = @($curation.candidates).Count
        $catCount = @($catwave.videos).Count
        if ($curCount -ne $catCount) {
            $failures += "GATE1: curation has $curCount candidates, catwave has $catCount videos — mismatch"
        } else {
            Write-Output "GATE1 PASS: $curCount candidates = $catCount videos"
        }
    } catch {
        $failures += "GATE1: failed to parse JSON: $_"
    }
}

# ── Gate 2: 今日候选飞书状态验收 ──
# Today's candidates must be in Feishu and status != 候选.
# Step 2a: check record_ids are present in curation JSON
$todaySlugs = @{}
$missingRid = @()
foreach ($c in $curation.candidates) {
    $slug = $c.slug
    $rid = $c.record_id
    if ($slug) { $todaySlugs[$slug] = $true }
    if (-not $rid -or $rid.Length -lt 5) { $missingRid += $slug }
}
if ($missingRid.Count -gt 0) {
    $failures += "GATE2: $($missingRid.Count) candidate(s) missing record_id — Feishu onboarding may have failed: $($missingRid -join ', ')"
}

# Step 2b: query Feishu for records still 候选, cross-ref with today's slugs
$tmpDir = "$env:TEMP\chain-verify"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$filterJson = '{"logic":"and","conditions":[["状态","==",["候选"]]]}'
[System.IO.File]::WriteAllText("$tmpDir\filter.json", $filterJson, [System.Text.UTF8Encoding]::new($false))

$batContent = "@echo off`r`nchcp 65001 > nul`r`ncd /d `"$tmpDir`"`r`nlark-cli base +record-list --base-token F7E8bJie5aX3BvsZz1Xc9KiznNb --table-id tblIs359fHfIapwd --as bot --limit 200 --format json --filter-json @filter.json --field-id Slug --field-id 状态 > records.json 2>&1`r`nexit /b %ERRORLEVEL%"
$batPath = "$tmpDir\_run.bat"
[System.IO.File]::WriteAllText($batPath, $batContent, [System.Text.UTF8Encoding]::new($false))

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c `"$batPath`""
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)
$proc.WaitForExit()

if ($proc.ExitCode -ne 0) {
    $warnings += "GATE2: lark-cli failed (exit $($proc.ExitCode)) — cannot verify Feishu status"
} else {
    $raw = Get-Content "$tmpDir\records.json" -Raw -Encoding UTF8
    try {
        $resp = $raw | ConvertFrom-Json
        if ($resp.ok) {
            $feishuCandidateSlugs = @{}
            foreach ($row in $resp.data.data) {
                $fslug = $row[0]
                if ($fslug) {
                    $feishuCandidateSlugs[$fslug] = $true
                    # Also match without date prefix (orchestrator strips YYYYMMDD_)
                    $noDate = $fslug -replace '^\d{8}_', ''
                    $feishuCandidateSlugs[$noDate] = $true
                }
            }
            $stuckSlugs = @()
            foreach ($slug in $todaySlugs.Keys) {
                $noDateSlug = $slug -replace '^\d{8}_', ''
                if ($feishuCandidateSlugs.ContainsKey($slug) -or $feishuCandidateSlugs.ContainsKey($noDateSlug)) {
                    $stuckSlugs += $slug
                }
            }
            if ($stuckSlugs.Count -gt 0) {
                $failures += "GATE2: $($stuckSlugs.Count) today candidate(s) still '候选' in Feishu: $($stuckSlugs -join ', ')"
            } else {
                Write-Output "GATE2 PASS: 0 today candidates stuck at 候选"
            }
        } else {
            $warnings += "GATE2: lark-cli error: $($resp.error.message)"
        }
    } catch {
        $warnings += "GATE2: failed to parse Feishu response"
    }
}
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

# ── Gate 3: 状态面板更新时间 ──
$panelPath = "D:\workspace\_output\猫波信号站\视频\状态面板.html"
if (-not (Test-Path $panelPath)) {
    $failures += "GATE3: status panel not found: $panelPath"
} else {
    $panelDate = (Get-Item $panelPath).LastWriteTime.ToString("yyyy-MM-dd")
    if ($panelDate -ne $date) {
        $failures += "GATE3: status panel last updated $panelDate, expected $date"
    } else {
        Write-Output "GATE3 PASS: status panel updated today ($panelDate)"
    }
}

# ── Result ──
Write-Output ""
Write-Output "=== verify-chain result ==="
Write-Output "Failures: $($failures.Count)"
foreach ($f in $failures) { Write-Output "  FAIL: $f" }
Write-Output "Warnings: $($warnings.Count)"
foreach ($w in $warnings) { Write-Output "  WARN: $w" }

if ($failures.Count -gt 0) {
    Write-Output ""
    Write-Output "ACTION: Sending Feishu alert..."

    $alertLines = @()
    $alertLines += "链路校验失败 · $date"
    $alertLines += ""
    foreach ($f in $failures) { $alertLines += "❌ $f" }
    foreach ($w in $warnings) { $alertLines += "⚠️ $w" }
    $alertBody = $alertLines -join "`n"

    $alertPayload = @{
        title = "猫波链路校验失败 · $date"
        content = $alertBody
        bot = "jinhua-cat"
    }
    $payloadFile = "$env:TEMP\chain-verify-alert.json"
    $payloadJson = $alertPayload | ConvertTo-Json -Depth 5 -Compress
    [System.IO.File]::WriteAllText($payloadFile, $payloadJson, [System.Text.UTF8Encoding]::new($false))
    & node "C:\Users\Administrator\.scheduler\feishu-notify.js" --payload-file $payloadFile
    if ($LASTEXITCODE -ne 0) {
        Write-Output "WARN: Feishu alert failed (exit=$LASTEXITCODE)"
    } else {
        Write-Output "Feishu alert sent"
    }
    Remove-Item $payloadFile -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Output "ALL GATES PASSED"
exit 0
