# Overrides model settings for this backend process only. No API key is written to disk.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# .env is authoritative and supplies LLM_* / EMBEDDING_* / QUEUE_ENABLED for local runs too.
. (Join-Path $PSScriptRoot 'load_env.ps1')

if ([string]::IsNullOrWhiteSpace($env:LLM_API_KEY)) {
    throw 'LLM_API_KEY is missing. Define LLM_API_KEY in the project .env file.'
}

# Fallbacks only: any value .env already defines keeps the .env value.
if ([string]::IsNullOrWhiteSpace($env:LLM_BASE_URL)) { $env:LLM_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1' }
if ([string]::IsNullOrWhiteSpace($env:LLM_MODEL)) { $env:LLM_MODEL = 'qwen3.7-plus' }
if ([string]::IsNullOrWhiteSpace($env:LLM_FALLBACK_MODEL)) { $env:LLM_FALLBACK_MODEL = 'qwen3.7-flash' }
if ([string]::IsNullOrWhiteSpace($env:EMBEDDING_BASE_URL)) { $env:EMBEDDING_BASE_URL = $env:LLM_BASE_URL }
if ([string]::IsNullOrWhiteSpace($env:EMBEDDING_API_KEY)) { $env:EMBEDDING_API_KEY = $env:LLM_API_KEY }
if ([string]::IsNullOrWhiteSpace($env:EMBEDDING_MODEL)) { $env:EMBEDDING_MODEL = 'text-embedding-v4' }
if ([string]::IsNullOrWhiteSpace($env:EMBEDDING_DIM)) { $env:EMBEDDING_DIM = '1024' }
if ([string]::IsNullOrWhiteSpace($env:QUEUE_ENABLED)) { $env:QUEUE_ENABLED = '0' }

uv run uvicorn app.presentation.server:app --port 8000