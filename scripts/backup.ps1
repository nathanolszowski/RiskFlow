<#
.SYNOPSIS
    Sauvegarde RiskFlow : dump PostgreSQL + copie des médias.
.DESCRIPTION
    A lancer depuis la racine du dépôt (ou via le Planificateur de tâches).
    -Destination : dossier de sauvegarde, idéalement sur un autre disque ou synchronisé.
    Conserve les -Keep dernières sauvegardes.
#>
param(
    [string]$Destination = "D:\RiskFlowBackups",
    [int]$Keep = 14
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Variables DB_* lues dans .env
$envVars = @{}
Get-Content .env | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $envVars[$k.Trim()] = $v.Trim()
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $Destination $stamp
New-Item -ItemType Directory -Path $target -Force | Out-Null

# Dump au format custom (restauration avec pg_restore), écrit dans le conteneur puis copié
docker compose exec -T db pg_dump -U $envVars["DB_USER"] -d $envVars["DB_NAME"] -Fc -f /tmp/riskflow.dump
docker compose cp db:/tmp/riskflow.dump (Join-Path $target "riskflow.dump")
docker compose exec -T db rm /tmp/riskflow.dump

# Médias : copie du volume dans une archive
docker compose exec -T web tar -C /data -cf /tmp/media.tar media
docker compose cp web:/tmp/media.tar (Join-Path $target "media.tar")
docker compose exec -T web rm /tmp/media.tar

# Rotation
Get-ChildItem $Destination -Directory | Sort-Object Name -Descending |
    Select-Object -Skip $Keep | Remove-Item -Recurse -Force

Write-Host "Sauvegarde terminée : $target"
