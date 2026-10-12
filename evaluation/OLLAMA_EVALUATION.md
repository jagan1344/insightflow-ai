# Model-backed evaluation with local Ollama

The GitHub Actions research workflow intentionally uses `LLM_PROVIDER=offline`; a hosted GitHub runner cannot access Ollama running on your laptop. Do not call those results model-backed.

## Requirements

- Windows 10/11 with Python 3.11 recommended.
- Ollama installed and running on this laptop.
- One model already pulled locally.
- Enough RAM/VRAM for the selected model.

## 1. Check Ollama

Open PowerShell and run:

```powershell
ollama --version
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

If the model you want is not installed, choose a model that fits your laptop and pull it, for example:

```powershell
ollama pull qwen2.5:3b
```

This is only an example; the model's quality and speed depend on your hardware. Your laptop has a Ryzen 5 CPU, so start with a small quantized model if you do not have a suitable GPU.

## 2. Run the strict evaluation

From the repository root (the folder containing `backend` and `evaluation`):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\evaluation\scripts\run_ollama_evaluation.ps1 -Model "qwen2.5:3b"
```

Replace `qwen2.5:3b` with the exact model name shown by `ollama list` and `/v1/models`.

The script checks the local Ollama API, sets `LLM_PROVIDER=local`, configures the OpenAI-compatible endpoint, enables `LLM_STRICT_MODE=true`, rebuilds the deterministic demo database and benchmark, runs the benchmark and ablation, and regenerates figures. Strict mode raises an error if the provider cannot initialize or a model request fails, rather than silently replacing model responses with the offline stub.

## 3. Review the outputs

Look in:

- `evaluation/results/raw_results.csv` — per-question outputs and decisions.
- `evaluation/results/results.json` — structured per-question outputs.
- `evaluation/results/metrics.json` — aggregate metrics (if emitted by the current metrics script).
- `evaluation/results/ablation.json` and `ablation.csv` — confidence-weighting comparison.
- `evaluation/figures/` — regenerated figures.

Before using any metric in a paper, verify the actual row count, which questions have gold SQL, failures, confidence scores, and whether the benchmark's expected results are independently correct. A single 27-question development benchmark is not a held-out test set and cannot establish general reliability.

## Privacy and cost

This setup sends prompts to the Ollama service on your own machine, not to OpenAI. Keep the Ollama endpoint bound to localhost and do not expose port 11434 to the public internet. Model downloads may use internet bandwidth; inference is local.

The script reseeds `backend/data/insightflow.db` and regenerates evaluation outputs. Back up any local database or results you want to keep before running it.
