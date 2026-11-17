<#
.SYNOPSIS
    Met à jour RiskFlow vers un tag Git, avec sauvegarde préalable et retour arrière.
.EXAMPLE
    .\scripts\update.ps1 -Tag v1.2.0
#>
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Backups = "D:\RiskFlowBackups"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (git status --porcelain) { throw "Le dépôt a des modifications locales : les valider ou les annuler d'abord." }
$previous = (git describe --tags --exact-match 2>$null)
if (-not $previous) { $previous = (git rev-parse HEAD) }

# 1. Sauvegarde
& "$PSScriptRoot\backup.ps1" -Destination $Backups
$lastBackup = (Get-ChildItem $Backups -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName

function Deploy($ref) {
    git fetch --tags
    git checkout $ref
    $env:RISKFLOW_VERSION = ($ref -replace '^v', '')
    docker compose build
    docker compose up -d db
    docker compose run --rm web python manage.py migrate --noinput
    docker compose up -d
}

try {
    Deploy $Tag
    # Test de santé : la page de connexion doit répondre
    Start-Sleep -Seconds 8
    $status = (Invoke-WebRequest -Uri "http://localhost:8000/auth/login/" -UseBasicParsing).StatusCode
    if ($status -ne 200) { throw "Test de santé : code $status" }
    Write-Host "RiskFlow est à jour ($Tag)."
}
catch {
    Write-Warning "Echec : $_"
    Write-Warning "Retour à $previous."
    Deploy $previous
    Write-Warning "Les migrations de $Tag peuvent avoir modifié la base : si elle est incohérente, restaurer $lastBackup (voir docs/riskflow-deploiement.md)."
    exit 1
}
