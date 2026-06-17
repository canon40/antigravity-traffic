# Canon4040 Autoblog GUI launcher (PowerShell — @ 경로에서도 안전)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pyw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not (Test-Path $pyw)) { $pyw = $py }

$check = & $py (Join-Path $PSScriptRoot "blog_single_instance.py") --check 2>$null
if ($LASTEXITCODE -eq 0) {
    & $py -c "from blog_single_instance import focus_existing_window; focus_existing_window()" 2>$null
    Write-Host "Autoblog가 이미 실행 중입니다. 기존 창을 활성화했습니다."
    exit 0
}

$env:BLOG_API_SPARING = "0"
$env:BLOG_TEXT_PROVIDER = "gemini"
$env:BLOG_IMAGE_PROVIDER = "genai"
$env:BLOG_LIGHT_GUI = "1"
$env:BLOG_LAZY_TABS = "1"
$env:BLOG_JAVIS_BRIDGE = "0"
$env:BLOG_DEFER_BROWSER = "1"
$env:BLOG_BROWSER_PER_ROUND = "1"
$env:BLOG_UNLOAD_AFTER_JOB = "1"

Start-Process -FilePath $pyw -ArgumentList (Join-Path $PSScriptRoot "blog_main.py") -WorkingDirectory $PSScriptRoot
Write-Host "Autoblog GUI를 시작했습니다."
