# RiskFlow — Déploiement local (Docker sur PC Windows)

Dernière modification : 20/11/2026 à 10:31 par Nathan

Un seul utilisateur, un seul PC, accès uniquement depuis ce PC (<http://localhost:8000>). Pas d'hébergement en ligne.

## Installation de zéro
1. Windows : activer WSL2, installer Docker Desktop (Settings > General : « Start Docker Desktop when you sign in »). Activer l'ouverture de session automatique si le PC redémarre seul.
2. Installer Git, cloner le dépôt dans un dossier sans espace ni accent (ex. `C:\RiskFlow\app`) : `git checkout <dernier tag>`.
3. Copier `.env.example` en `.env` : `SECRET_KEY` (longue chaîne aléatoire), `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `INSEE_API_KEY`. Ne jamais valider ce fichier.
4. `docker compose build`, `docker compose up -d db`, `docker compose run --rm web python manage.py migrate`, `docker compose run --rm web python manage.py createsuperuser`, `docker compose up -d`.
5. Vérifier <http://localhost:8000/auth/login/> et que le port n'est pas joignable depuis un autre appareil.

## Mise à jour
Sur `develop` on code et la CI valide ; merge sur `main`, puis tag `vX.Y.Z`. Sur le PC : `.\scripts\update.ps1 -Tag vX.Y.Z` (sauvegarde, build, migrations, test de santé ; retour automatique au tag précédent en cas d'échec).

## Sauvegarde
`.\scripts\backup.ps1 -Destination D:\RiskFlowBackups` : dump PostgreSQL (`riskflow.dump`) et archive des médias (`media.tar`), 14 sauvegardes conservées. À planifier chaque jour (Planificateur de tâches Windows, action « Démarrer un programme » : `powershell.exe -File C:\RiskFlow\app\scripts\backup.ps1`). Copier le dossier de sauvegarde sur un autre support (disque externe, cloud synchronisé). Un volume Docker n'est pas une sauvegarde.

## Restauration (à tester une fois)
```powershell
docker compose up -d db
docker compose cp D:\RiskFlowBackups\<date>\riskflow.dump db:/tmp/riskflow.dump
docker compose exec db pg_restore -U <DB_USER> -d <DB_NAME> --clean --if-exists /tmp/riskflow.dump
docker compose cp D:\RiskFlowBackups\<date>\media.tar web:/tmp/media.tar
docker compose exec web tar -C /data -xf /tmp/media.tar
docker compose up -d
```

## Dépannage
- `docker compose ps` / `docker compose logs -f web` ; fichier `riskflow.log` dans le volume `logs`.
- Page d'erreur 400 : vérifier `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
- CSS absent : l'image a été construite sans `tailwind build` ; refaire `docker compose build --no-cache`.
- Géocodage / Sirene en erreur : pas d'Internet ; `GEOCODING_ENABLED=0` dans `.env`.

## Entretien
- Revue mensuelle : correctifs de sécurité Django (`uv lock --upgrade`, tests, tag), mise à jour de l'image de base (`docker compose build --pull`).
- PostgreSQL : version majeure épinglée dans `compose.yaml` (16) ; une montée de version se fait par dump puis restauration dans un nouveau volume.
- Python 3.12 est supporté jusqu'en 2028.
- Pas de développement sur la base réelle : coder sous WSL2 avec `config.settings.dev` et la base `riskflow_dev`.
