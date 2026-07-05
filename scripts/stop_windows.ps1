# Stop and remove the FinAlly container. Leaves the data volume intact. Idempotent.
$ErrorActionPreference = "Stop"

$Container = "finally"

docker rm -f $Container *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Stopped and removed '$Container'."
} else {
    Write-Host "'$Container' is not running."
}
Write-Host "Data volume 'finally-data' preserved."
