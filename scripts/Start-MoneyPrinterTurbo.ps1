param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.local.yml"
$webUrl = "http://127.0.0.1:8501/"
$healthUrl = "http://127.0.0.1:8501/_stcore/health"

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker was not found. Start or install Docker Desktop first."
    }
    if (-not (Test-Path -LiteralPath $composeFile)) {
        throw "The deployment file was not found: $composeFile"
    }

    & docker compose -f $composeFile up -d | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker services failed to start. Check that Docker Desktop is running."
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        throw "The services started, but the WebUI was not ready within 30 seconds."
    }

    if (-not $NoOpen) {
        Start-Process $webUrl
    }
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        $_.Exception.Message,
        "MoneyPrinterTurbo startup failed",
        "OK",
        "Error"
    ) | Out-Null
    exit 1
}
