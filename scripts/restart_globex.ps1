# Restarts the entire local Globex stack from deterministic working directories.
$projectRoot = Split-Path -Parent $PSScriptRoot
$stopScript = Join-Path $PSScriptRoot 'stop_globex_services.ps1'
$backendScript = Join-Path $PSScriptRoot 'run_qwen_backend.ps1'
$frontendRoot = Join-Path $projectRoot 'frontend'

# .env is authoritative for local runs as well; load it before validating the API key.
. (Join-Path $PSScriptRoot 'load_env.ps1')

if ([string]::IsNullOrWhiteSpace($env:LLM_API_KEY)) {
    throw 'LLM_API_KEY is missing. Define LLM_API_KEY in the project .env file.'
}

if (-not (Test-Path (Join-Path $frontendRoot 'node_modules\.bin\vite.cmd'))) {
    throw 'Frontend dependencies are missing. Run npm ci in the frontend directory first.'
}

& $stopScript

Start-Process `
    -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $backendScript) `
    -WorkingDirectory $projectRoot

Start-Process `
    -FilePath 'cmd.exe' `
    -ArgumentList @('/k', 'npm run dev') `
    -WorkingDirectory $frontendRoot

Write-Host 'Globex restart requested. Backend initializes on port 8000 before it becomes ready.'
