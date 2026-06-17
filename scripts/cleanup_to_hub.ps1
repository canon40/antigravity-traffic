# SEO 허브(permacoat.shop) 전용으로 login2 슬림화
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$keepBats = @(
    "run.bat", "run_install.bat", "run_seo_hub_verify.bat", "rank_daily.bat",
    "run_programs_check.bat", "traffic_once.bat"
)

$keepRootPy = @(
    "app.py", "hub_runtime.py", "rank_tracker.py", "rank_persistence.py",
    "seo_checker.py", "seo_content_builder.py", "keyword_analyzer.py",
    "javis_programs.py", "javis_serverless.py", "app_resources.py", "programs_check.py"
)

$removeDirs = @(
    "shorts_factory", "content_factory", "drawer", "super_agents", "sangseopage", "n8n", "wiki", "javis",
    "generated_images", "drafts", "dist", ".tmp", "build", "security_vault", "sql",
    "docs\shorts", "docs\store_detail", "docs\detail_page", "docs\shopping_shorts",
    "docs\video_evolution", "docs\guides", "docs\checklists", "docs\integrations",
    "data\shorts_factory", "data\content_factory", "data\blog", "data\ops", "data\super_agents",
    "vercel_traffic\api", "vercel_traffic\public", "vercel_traffic\docs"
)

foreach ($d in $removeDirs) {
    $p = Join-Path $root $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "removed dir $d" }
}

Get-ChildItem $root -Directory -Filter "browser_data_*" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Directory -Filter "web_browser_*" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Directory -Filter "verify_*" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem $root -Filter "*.bat" -File | Where-Object { $keepBats -notcontains $_.Name } | Remove-Item -Force
Get-ChildItem $root -Filter "*.py" -File | Where-Object { $keepRootPy -notcontains $_.Name } | Remove-Item -Force

$removeRootFiles = @(
    "api\proxy.py", "vercel_traffic\vercel.json", "vercel_traffic\README.md",
    "vercel_traffic\requirements.txt", "scripts\naver_blog_diagnose.py",
    "AGENTS.md", "AGENT_PIPELINE.md", "BUILD_README.txt", "CODEX_DRAWER.md", "LOOP.md",
    "accounts.json.example", "blog_auto.spec", "blog_auto_public.spec",
    "config.py", "requirements-local.txt", "requirements-vercel.txt",
    "Procfile", "Dockerfile", ".dockerignore", "readme.md"
)
foreach ($f in $removeRootFiles) {
    $p = Join-Path $root $f
    if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue; Write-Host "removed $f" }
}

$dataKeep = @("rank_hub_state.json", "rank_history_seed.json", "programs_catalog.json")
Get-ChildItem (Join-Path $root "data") -File -ErrorAction SilentlyContinue | Where-Object { $dataKeep -notcontains $_.Name } | Remove-Item -Force

Get-ChildItem $root -Filter "*.log" -File | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Filter "_*.json" -File | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Filter "*.spec" -File | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "cleanup done"
