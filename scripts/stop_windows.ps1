$ContainerName = "finally"

$running = docker ps -q --filter "name=$ContainerName"
if ($running) {
    Write-Host "Stopping FinAlly container..."
    docker stop $ContainerName
    docker rm $ContainerName
    Write-Host "Done. Data volume preserved."
} else {
    Write-Host "No running FinAlly container found."
}
