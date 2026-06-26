# 猫波信号站 · 视频管线启动器
# 用法：双击运行，输入 YouTube URL 即可
param(
    [string]$url = ""
)

if (-not $url) {
    $url = Read-Host "请输入 YouTube 视频 URL"
}

if (-not $url) {
    Write-Host "未输入 URL，退出" -ForegroundColor Red
    Read-Host "按回车关闭"
    exit 1
}

$pipelineDir = "D:\workspace\猫波信号站"
$slug = Read-Host "输入目录 slug（如 kevin-weil-lenny，回车跳过自动检测）"
$title = Read-Host "输入 B站标题（如 OpenAI CPO Kevin Weil...，回车跳过）"

$cmd = "python `"$pipelineDir\pipeline.py`" all `"$url`""
if ($slug) { $cmd += " --slug `"$slug`"" }
if ($title) { $cmd += " --output-title `"$title`"" }

Write-Host ""
Write-Host "执行: $cmd" -ForegroundColor Yellow
Write-Host ""

Push-Location $pipelineDir
try {
    Invoke-Expression $cmd
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n管线完成！" -ForegroundColor Green
    } else {
        Write-Host "`n管线异常退出 (code: $LASTEXITCODE)" -ForegroundColor Red
    }
} finally {
    Pop-Location
}

Read-Host "按回车关闭"
