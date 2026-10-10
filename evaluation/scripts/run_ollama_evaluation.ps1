param(
    [Parameter(Mandatory = $true)]
    [string]$Model
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ollamaApi = "http://localhost:11434"
$openAiCompat = "$ollamaApi/v1"

Write-Host "== InsightFlow AI: strict Ollama evaluation ==" -ForegroundColor Cyan
Write-Host "Repository: $root"
Write-Host "Requested model: $Model"

try {
    $tags = Invoke-RestMethod -Uri "$ollamaApi/api/tags" -TimeoutSec 5
} catch {
    throw "Cannot reach Ollama at $ollamaApi. Start Ollama on this laptop, then retry. Original error: $($_.Exception.Message)"
}

$installed = @($tags.models | ForEach-Object { $_.name })
if ($installed -notcontains $Model) {
    Write-Host "Installed Ollama models:"
    $installed | ForEach-Object { Write-Host " - $_" }
    throw "Model '$Model' is not installed exactly as named. Pull it with 'ollama pull <model>' or rerun with -Model matching the list above."
}

try {
    $apiModels = Invoke-RestMethod -Uri "$openAiCompat/models" -TimeoutSec 10
} catch {
    throw "Ollama's OpenAI-compatible endpoint is not responding at $openAiCompat. Update Ollama and verify the local server."
}

$apiNames = @($apiModels.data | ForEach-Object { $_.id })
if ($apiNames.Count -gt 0 -and $apiNames -notcontains $Model) {
    Write-Host "Models exposed by Ollama's /v1/models endpoint:"
    $apiNames | ForEach-Object { Write-Host " - $_" }
    throw "The selected model is not listed by the OpenAI-compatible endpoint. Use the exact exposed model id."
}

$env:LLM_PROVIDER = "local"
$env:LLM_MODEL = $Model
$env:LLM_BASE_URL = $openAiCompat
$env:LLM_STRICT_MODE = "true"
$env:DATABASE_URL = "sqlite:///$($root.Replace('\','/'))/backend/data/insightflow.db"

Push-Location $root
try {
    Write-Host ""
    Write-Host "[1/6] Install backend dependencies"
    python -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    Write-Host ""
    Write-Host "[2/6] Seed deterministic demo database"
    python backend/data/seed.py
    if ($LASTEXITCODE -ne 0) { throw "Database seeding failed." }

    Write-Host ""
    Write-Host "[3/6] Rebuild benchmark ground truth"
    python evaluation/scripts/prepare_dataset.py
    if ($LASTEXITCODE -ne 0) { throw "Benchmark preparation failed." }

    Write-Host ""
    Write-Host "[4/6] Run model-backed reliability benchmark (strict mode)"
    python evaluation/scripts/run_evaluation.py
    if ($LASTEXITCODE -ne 0) { throw "Model-backed benchmark failed. Strict mode prevents silent offline fallback." }

    Write-Host ""
    Write-Host "[5/6] Calculate metrics and run ablation"
    python evaluation/scripts/calculate_metrics.py
    if ($LASTEXITCODE -ne 0) { throw "Metric calculation failed." }
    python evaluation/scripts/run_ablation.py
    if ($LASTEXITCODE -ne 0) { throw "Confidence ablation failed." }

    Write-Host ""
    Write-Host "[6/6] Regenerate figures"
    python evaluation/scripts/generate_figures.py
    if ($LASTEXITCODE -ne 0) { throw "Figure generation failed." }

    Write-Host ""
    Write-Host "SUCCESS: model-backed evaluation completed."
    Write-Host "Results: $root\evaluation\results"
    Write-Host "Figures: $root\evaluation\figures"
    Write-Host "Inspect raw_results.csv and ablation.json before changing paper claims."
} finally {
    Pop-Location
}
