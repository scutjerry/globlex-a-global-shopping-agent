# Loads the project root .env into this process so that local (non-Docker) runs use exactly
# the same configuration as the containers. .env is authoritative: it overwrites values
# inherited from the machine, so a stray machine-level variable cannot change behavior.
# Values are never printed, so secrets stay out of the console and out of logs.
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'

if (-not (Test-Path $envFile)) {
    throw "No .env file found at $envFile. Create it from .env.example first."
}

foreach ($line in [System.IO.File]::ReadAllLines($envFile)) {
    $text = $line.Trim()
    if ($text.Length -eq 0) { continue }
    if ($text.StartsWith('#')) { continue }

    $index = $text.IndexOf('=')
    if ($index -lt 1) { continue }

    # Tolerate "KEY = value" spacing, which cmd's for /f parser does not handle.
    $key = $text.Substring(0, $index).Trim()
    $value = $text.Substring($index + 1).Trim()
    if ($key.Length -eq 0) { continue }

    # Drop an unquoted trailing comment, matching how Docker Compose reads the same file.
    $comment = $value.IndexOf(' #')
    if ($comment -ge 0) { $value = $value.Substring(0, $comment).Trim() }

    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}