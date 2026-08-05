$ErrorActionPreference = "Stop"
$date = (Get-Date).ToString("yyyy-MM-dd")
Write-Output "=== run-curation: $date ==="

$promptFile = "D:\workspace\猫波信号站\tools\curation-prompt.txt"
$prompt = Get-Content $promptFile -Raw -Encoding UTF8
# Inject current date into prompt
$prompt = $prompt -replace "YYYY-MM-DD", $date

Write-Output "Step 1/3: Running curation agent..."

# Write prompt to temp file (UTF-8 no BOM — cmd.exe < redirect reads as UTF-8 with chcp 65001)
$tmpFile = "$env:TEMP\catwave-curation-$date.txt"
[System.IO.File]::WriteAllText($tmpFile, $prompt, [System.Text.UTF8Encoding]::new($false))

$logPath = "D:\workspace\_output\猫波信号站\视频\_curation\agent-$date.log"

# Use System.Diagnostics.Process with cmd.exe — bypasses all PowerShell encoding issues
# chcp 65001 ensures > redirect writes UTF-8, < reads UTF-8
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c chcp 65001 > nul && claude --print --model deepseek-v4-flash --permission-mode bypassPermissions --output-format text < `"$tmpFile`" > `"$logPath`" 2>&1"
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)
$proc.WaitForExit()
$agentExit = $proc.ExitCode

Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue

if ($agentExit -ne 0) {
    Write-Output "FATAL: Curation agent exited with code $agentExit"
    if (Test-Path $logPath) {
        $logContent = Get-Content $logPath -Raw -Encoding UTF8
        if ($logContent) { Write-Output $logContent }
    }
    exit 1
}

# Validate agent output
if (-not (Test-Path $logPath)) {
    Write-Output "FATAL: Agent log not produced at $logPath"
    exit 1
}
Write-Output "Agent log: $logPath ($((Get-Item $logPath).Length) bytes)"

Write-Output "Step 2/4: Onboarding to Feishu..."
& python "D:\workspace\猫波信号站\tools\onboard_to_feishu.py" $date
if ($LASTEXITCODE -ne 0) {
    Write-Output "FATAL: onboard-to-feishu failed with exit code $LASTEXITCODE"
    exit 1
}

Write-Output "Step 3/4: Deploying catwave data..."
& python "D:\workspace\evopearl-data\sync_catwave.py"
if ($LASTEXITCODE -ne 0) {
    Write-Output "FATAL: sync-catwave failed with exit code $LASTEXITCODE"
    exit 1
}

Write-Output "Step 4/4: Post-curation check..."
$curationFile = "D:\workspace\_output\猫波信号站\视频\_curation\$date.json"
if (Test-Path $curationFile) {
    $curation = Get-Content $curationFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $finalCount = $curation.final_count
    if ($finalCount -eq 0) {
        $notes = $curation.notes
        $qualityNote = if ($notes.quality_note) { $notes.quality_note } else { "curator 未提供原因" }
        $notifyPayload = @{
            title = "猫波选题 $date · 本期无候选"
            content = "final_count = 0`n扫描源：$($curation.scanned_sources) 个`n原因：$qualityNote"
            bot = "jinhua-cat"
        }
        $payloadFile = "$env:TEMP\catwave-notify.json"
        $payloadJson = $notifyPayload | ConvertTo-Json -Depth 5 -Compress
        [System.IO.File]::WriteAllText($payloadFile, $payloadJson, [System.Text.UTF8Encoding]::new($false))
        & node "C:\Users\Administrator\.scheduler\feishu-notify.js" --payload-file $payloadFile
        if ($LASTEXITCODE -ne 0) {
            Write-Output "WARN: feishu notify failed (exit=$LASTEXITCODE)"
        }
        Remove-Item $payloadFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Output "OK: $finalCount candidates, skip empty-notify"
    }
} else {
    Write-Output "WARN: curation file not found, skip notify check"
}

Write-Output "=== run-curation done ==="
