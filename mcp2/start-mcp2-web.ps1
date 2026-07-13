param(
    [string]$OpenAIKey = "",
    [string]$BackendBaseUrl = "http://127.0.0.1:8000",
    [int]$Port = 8787,
    [string]$Model = "gpt-4.1-mini",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

# Always run from this script's directory so local package resolution is consistent.
Set-Location $PSScriptRoot

$env:MCP2_MODE = "web"
$env:MCP2_BACKEND_BASE_URL = $BackendBaseUrl
$env:MCP2_WEB_PORT = "$Port"
$env:MCP2_DEFAULT_MODEL = $Model

if (-not [string]::IsNullOrWhiteSpace($OpenAIKey)) {
    $env:OPENAI_API_KEY = $OpenAIKey
}

Write-Host "Starting mcp2 web server..."
Write-Host "Directory: $PSScriptRoot"
Write-Host "URL: http://127.0.0.1:$Port"
Write-Host "Backend: $BackendBaseUrl"
Write-Host "Model: $Model"

& $PythonExe -m mcp2.main
