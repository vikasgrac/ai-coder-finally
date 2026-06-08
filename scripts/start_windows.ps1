param([switch]$Build)

$ContainerName = "finally"
$ImageName = "finally"
$VolumeName = "finally-data"
$Port = 8000
$EnvFile = Join-Path $PSScriptRoot "..\\.env"

if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env file not found at $EnvFile. Copy .env.example and add your API keys."
}

if ($Build -or -not (docker image inspect $ImageName 2>$null)) {
    Write-Host "Building Docker image..."
    docker build -t $ImageName (Join-Path $PSScriptRoot "..")
}

$running = docker ps -q --filter "name=$ContainerName"
if ($running) {
    Write-Host "Stopping existing container..."
    docker stop $ContainerName | Out-Null
    docker rm $ContainerName | Out-Null
}

$args = @("-d", "--name", $ContainerName, "-p", "${Port}:8000", "-v", "${VolumeName}:/app/db")
if (Test-Path $EnvFile) {
    $args += @("--env-file", $EnvFile)
}
$args += $ImageName

docker run @args

Write-Host ""
Write-Host "FinAlly is running at http://localhost:$Port"
Start-Sleep 2
Start-Process "http://localhost:$Port"
