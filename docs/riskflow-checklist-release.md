# RiskFlow — Checklist de release (maintenance)

Dernière modification : 20/11/2026 à 10:31 par Nathan

À dérouler à **chaque** release (`vX.Y.Z`). Contexte : `docs/riskflow-deploiement.md` (Docker sur un PC Windows, un seul utilisateur, accès depuis ce PC uniquement, `127.0.0.1:8000`).

Plan :
1. Développement, avant la création de la release
2. Création de la release sur Git
3. Déploiement sur Docker en production
4. Vérification post-déploiement
5. Cookbook : commandes et procédures utiles

Les points marqués **(1re release)** ne se font qu'une fois, à la mise en service initiale ; ils sont regroupés dans la section 5.8.

---

## 1. Développement (avant la création de la release)

Tout se passe sur `develop`, sous WSL2, avec `config.settings.dev` et la base `riskflow_dev` (jamais sur la base réelle).

### 1.1 Périmètre
- [ ] Le périmètre de la release est arrêté : fonctionnalités et corrections incluses, limites connues notées.
- [ ] Aucun texte de test, « TODO », « lorem ipsum » ou libellé anglais oublié dans les templates :
  ```bash
  grep -rniE "todo|fixme|lorem|xxx" apps/*/templates
  ```
- [ ] Les écarts entre la doc et le code sont corrigés (le code fait foi ; mettre la doc à jour si besoin).

### 1.2 Qualité du code
- [ ] `develop` est propre et poussé (`git status` vide, `git log origin/develop..develop` vide).
- [ ] La CI est **verte** sur le dernier commit de `develop` (lint, format, docstrings des tests, `makemigrations --check`, tests, couverture ≥ 70 %).
- [ ] Reproduire en local :
  ```bash
  uv run ruff check apps config
  ```
  ```bash
  uv run ruff format --check apps config
  ```
  ```bash
  uv run ruff check --select D1 apps/*/tests
  ```
  ```bash
  uv run python manage.py makemigrations --check --dry-run
  ```
  ```bash
  uv run coverage run manage.py test --settings=config.settings.test && uv run coverage report
  ```
- [ ] Aucun `print()`, `breakpoint()`, `pdb` ou code de débogage :
  ```bash
  grep -rnE "print\(|breakpoint\(|import pdb" apps config --include=*.py | grep -v tests
  ```
- [ ] Aucun `console.log` oublié dans les JS (`visit_form.js`, `address_autocomplete.js`, `address_map.js`, modale d'envoi de médias).
- [ ] Relecture du diff depuis la dernière release :
  ```bash
  git diff --stat <dernier-tag>..develop
  ```
  Optionnel : `/code-review` et `/security-review` sur la branche.

### 1.3 Migrations
- [ ] Un seul changement structurel par migration (jamais renommer une app et un modèle ensemble).
- [ ] Les migrations nouvelles sont relues (opérations destructrices, migrations de données, durée sur une base réelle).
- [ ] Elles s'appliquent sur une **copie de la base de production** (voir 5.5, restauration dans `riskflow_dev`) et pas seulement sur une base vide.
- [ ] Une migration destructrice ou irréversible est signalée dans les notes de release (le retour arrière automatique de `update.ps1` ne défait **pas** les migrations).

### 1.4 Sécurité et dépendances
- [ ] Dépendances à jour sur les correctifs de sécurité (Django en particulier), puis tests relancés :
  ```bash
  uv lock --upgrade && uv sync
  ```
- [ ] Audit des vulnérabilités connues :
  ```bash
  uvx pip-audit
  ```
- [ ] Aucun secret dans le diff (clé INSEE, mots de passe, `SECRET_KEY`) ; `.env` jamais commité :
  ```bash
  git log --all --full-history -- .env
  ```
- [ ] Aucune donnée utilisateur rendue avec `|safe` / `mark_safe` sans échappement :
  ```bash
  grep -rnE "\|safe|mark_safe|autoescape off" apps
  ```
- [ ] Toute nouvelle vue a `@htmx_login_required` (sauf connexion) et passe par les services filtrés sur le propriétaire (404 pour un autre utilisateur) ; toute vue qui modifie des données refuse le GET.
- [ ] Nouvelles variables d'environnement ajoutées à `.env.example` **et** signalées dans les notes de release (à reporter dans le `.env` de production).
- [ ] Dépendances de dev absentes de l'image (`uv sync --no-dev` dans le `Dockerfile`).

### 1.5 Recette en développement
Sur les parcours touchés par la release, au minimum :
- [ ] Nouvelles fonctionnalités et corrections vérifiées à la main (tablette si c'est l'usage terrain).
- [ ] Non-régression rapide : connexion, création d'un dossier, saisie d'une visite (y compris coupure réseau puis reprise), ajout d'un média, export PDF, thème clair/sombre.
- [ ] Cloisonnement : un second compte ne voit rien du premier (404).
- [ ] Sans Internet : pas de page 500 (`GEOCODING_ENABLED=0`).

### 1.6 Préparation documentaire
- [ ] `pyproject.toml` : `version` mise à jour.
- [ ] `CHANGELOG.md` (ou notes de release) : fonctionnalités, corrections, migrations, nouvelles variables d'environnement, limites connues.
- [ ] `README.md` à jour si l'installation, la mise à jour ou la sauvegarde ont changé.
- [ ] `docs/riskflow-roadmap.md` mis à jour (sprint clôturé, leçons apprises).

---

## 2. Création de la release sur Git

- [ ] CI verte sur `develop`, notes de release prêtes.
- [ ] Ouvrir la PR `develop` → `main` ; CI verte sur la PR :
  ```bash
  gh pr create --base main --head develop --title "Release vX.Y.Z"
  ```
- [ ] Merger la PR (merge commit, comme pour la PR #1).
- [ ] Mettre `main` à jour en local et vérifier qu'il est propre :
  ```bash
  git checkout main && git pull && git status
  ```
- [ ] Poser le tag **annoté** sur `main` et le pousser :
  ```bash
  git tag -a vX.Y.Z -m "RiskFlow vX.Y.Z" && git push origin vX.Y.Z
  ```
- [ ] Optionnel : release GitHub depuis le tag :
  ```bash
  gh release create vX.Y.Z --notes-file CHANGELOG.md
  ```
- [ ] Revenir sur `develop` et y reporter `main` si besoin (`git checkout develop && git merge main`).
- [ ] Optionnel : `main` protégée sur GitHub (PR obligatoire, CI requise).
- [ ] Le dépôt GitHub reste **privé** (le dossier `docs/` est ignoré par Git).

---

## 3. Déploiement sur Docker en production (PC Windows)

Prérequis : Docker Desktop démarré, dépôt propre sur le PC (le script refuse des modifications locales), accès Internet pour le build.

### 3.1 Avant de lancer
- [ ] Notes de release relues : migrations, nouvelles variables d'environnement.
- [ ] `.env` de production complété si de nouvelles variables sont requises (jamais de valeurs de dev, jamais commité).
- [ ] Espace disque suffisant (images, volumes, dossier de sauvegarde `D:`).
- [ ] Application fermée côté utilisateur (pas de visite en cours de saisie : une visite non synchronisée reste dans le `localStorage` du navigateur et sera renvoyée, mais autant éviter).
- [ ] Noter le tag actuellement en production (`git describe --tags`) : c'est le point de retour.

### 3.2 Mise à jour
- [ ] Lancer le script (sauvegarde, build, migrations, test de santé, retour automatique en cas d'échec) :
  ```powershell
  .\scripts\update.ps1 -Tag vX.Y.Z
  ```
- [ ] Le script se termine par « RiskFlow est à jour (vX.Y.Z) ».
- [ ] En cas d'échec : lire le message, vérifier que le retour au tag précédent a eu lieu, puis voir 5.6 (retour arrière). Si les migrations de la release ont modifié la base, **restaurer la sauvegarde** indiquée par le script.
- [ ] Conserver le chemin de la sauvegarde faite par le script (dossier daté dans `D:\RiskFlowBackups`) jusqu'à la validation post-déploiement.

---

## 4. Vérification post-déploiement (sur le PC de production)

### 4.1 Technique
- [ ] Conteneurs `web` et `db` à l'état `Up` :
  ```bash
  docker compose ps
  ```
- [ ] Version déployée : `git describe --tags` donne `vX.Y.Z`, et l'image est étiquetée `riskflow:X.Y.Z` (`docker images`).
- [ ] <http://localhost:8000/auth/login/> répond 200.
- [ ] Aucune erreur au démarrage ni 500 dans les logs :
  ```bash
  docker compose logs --tail 100 web
  ```
- [ ] Migrations toutes appliquées :
  ```bash
  docker compose run --rm web python manage.py showmigrations | grep "\[ \]"
  ```
  (aucune ligne attendue)
- [ ] Check de déploiement : seuls les avertissements assumés (HTTP sur localhost : `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) :
  ```bash
  docker compose run --rm web python manage.py check --deploy
  ```
- [ ] Conteneur en utilisateur non root :
  ```bash
  docker compose exec web whoami
  ```
  (attendu : `riskflow`)
- [ ] Les volumes `pgdata`, `media`, `logs` sont conservés (données et médias d'avant la mise à jour toujours présents).

### 4.2 Fonctionnel (smoke test, 10 minutes)
- [ ] Page stylée (CSS Tailwind présent). Si un ancien CSS reste affiché : forcer le rechargement (Ctrl+F5).
- [ ] Connexion, dashboard, recherche globale.
- [ ] Ouvrir un dossier existant : onglets, visites, recommandations, médias (miniature et ouverture d'un fichier).
- [ ] Ouvrir une visite existante : réponses intactes ; saisie d'un champ enregistrée.
- [ ] Export PDF vierge d'une visite (WeasyPrint, accents, police).
- [ ] Sirene : recherche par SIRET fonctionnelle (clé de production).
- [ ] Géoplateforme : autocomplétion d'adresse et carte.
- [ ] Les nouveautés de la release fonctionnent (reprendre les points de la section 1.5).
- [ ] Pages d'erreur 404 propres, en français, sans trace technique.

### 4.3 Sécurité
- [ ] Port publié sur `127.0.0.1` uniquement : `http://<ip du PC>:8000` ne répond pas depuis un autre appareil. PostgreSQL (5432) non publié.
- [ ] Un média n'est pas accessible hors connexion (URL ouverte en navigation privée → page de connexion).

### 4.4 Sauvegarde
- [ ] Sauvegarde manuelle réalisée **après** la mise à jour et vérifiée (`riskflow.dump` et `media.tar` non vides) :
  ```powershell
  .\scripts\backup.ps1 -Destination D:\RiskFlowBackups
  ```
- [ ] La sauvegarde planifiée tourne toujours (dernier dossier daté dans `D:\RiskFlowBackups`) et la copie hors du PC est à jour.

### 4.5 Suivi dans les jours qui suivent
- [ ] Surveiller les logs (`docker compose logs -f web`, erreurs 500).
- [ ] Noter dans `docs/riskflow-roadmap.md` les retours du terrain et les bugs trouvés ; corrections via `fix/<app>:` puis nouvelle release mineure.
- [ ] Après quelques jours sans incident : supprimer les anciennes images (`docker image prune`) et clore la release.

---

## 5. Cookbook : commandes et procédures utiles

### 5.1 Docker au quotidien
```bash
docker compose ps
```
```bash
docker compose logs -f web
```
```bash
docker compose up -d
```
```bash
docker compose restart web
```
```bash
docker compose down
```
**Ne jamais** ajouter `-v` à `down` : cela supprime les volumes (base, médias, logs).

Journal applicatif : `riskflow.log` dans le volume `logs`. Shell dans le conteneur :
```bash
docker compose exec web bash
```
Console Django et commandes de gestion :
```bash
docker compose exec web python manage.py shell
```
```bash
docker compose run --rm web python manage.py <commande>
```

### 5.2 Build
```bash
docker compose build
```
Image étiquetée avec la version : `RISKFLOW_VERSION=X.Y.Z` défini avant le build (le script `update.ps1` le fait ; sans cela l'image est `riskflow:latest`).
```bash
docker compose build --pull
```
Reconstruction complète (CSS absent, image douteuse) :
```bash
docker compose build --no-cache
```
Test depuis un clone propre (pas depuis le dossier de dev) :
```bash
git clone <dépôt> /tmp/riskflow-release && cd /tmp/riskflow-release && git checkout vX.Y.Z && docker compose build --no-cache
```

### 5.3 Sauvegarde
Manuelle (dump PostgreSQL `riskflow.dump` + archive `media.tar`, 14 sauvegardes conservées) :
```powershell
.\scripts\backup.ps1 -Destination D:\RiskFlowBackups
```
- Le dossier de destination est daté (`yyyyMMdd-HHmmss`). Le disque `D:` doit exister, sinon passer `-Destination`. `-Keep` règle la rotation.
- **Planification** : Planificateur de tâches Windows, action « Démarrer un programme » : `powershell.exe -File C:\RiskFlow\app\scripts\backup.ps1`, une fois par jour.
- **Copie hors du PC** : disque externe ou dossier cloud synchronisé. Un volume Docker n'est pas une sauvegarde.
- **`.env` de production** : sauvegardé à part, en lieu sûr (gestionnaire de mots de passe).
- BitLocker activé sur le PC (la base et les médias contiennent des données clients).

### 5.4 Restauration
Remplace la base et les médias par ceux d'une sauvegarde (`<date>` = dossier daté) :
```powershell
docker compose up -d db
```
```powershell
docker compose cp D:\RiskFlowBackups\<date>\riskflow.dump db:/tmp/riskflow.dump
```
```powershell
docker compose exec db pg_restore -U <DB_USER> -d <DB_NAME> --clean --if-exists /tmp/riskflow.dump
```
```powershell
docker compose cp D:\RiskFlowBackups\<date>\media.tar web:/tmp/media.tar
```
```powershell
docker compose exec web tar -C /data -xf /tmp/media.tar
```
```powershell
docker compose up -d
```
Ensuite : connexion, ouverture d'un dossier, d'une visite et d'un média. **À tester de bout en bout au moins une fois** et après toute évolution de la procédure.

### 5.5 Restaurer la production dans la base de dev (tester une migration)
Pour valider une migration sur des données réelles sans toucher à la production : restaurer le `riskflow.dump` dans la base `riskflow_dev` (WSL2), puis `uv run python manage.py migrate`. Ne jamais l'inverse (pas de développement sur la base réelle).

### 5.6 Retour arrière
- **Échec pendant `update.ps1`** : le script revient seul au tag précédent (`git checkout`, build, `migrate`, `up -d`) et affiche le chemin de la dernière sauvegarde.
- **Les migrations ne sont pas défaites automatiquement** : si la base est incohérente avec l'ancien code, restaurer la sauvegarde (5.4) **après** être revenu au tag précédent.
- **Retour manuel** (régression détectée après coup) :
  ```powershell
  git fetch --tags
  ```
  ```powershell
  git checkout vX.Y.Z-précédent
  ```
  ```powershell
  $env:RISKFLOW_VERSION = "X.Y.Z-précédent"; docker compose build; docker compose up -d
  ```
  puis restauration de la sauvegarde d'avant la mise à jour si la release comportait des migrations.
- Un correctif d'urgence passe par `fix/<app>:` sur `develop`, un nouveau tag mineur et `update.ps1`, pas par une modification sur le PC de production.

### 5.7 Dépannage
- `docker compose ps` / `docker compose logs -f web`, fichier `riskflow.log` (volume `logs`).
- **Erreur 400** : vérifier `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` (vides ou `localhost` / `127.0.0.1`).
- **CSS absent** : image construite sans `tailwind build` → `docker compose build --no-cache`.
- **Ancien CSS après mise à jour** : cache navigateur (Ctrl+F5) ; option : `CompressedManifestStaticFilesStorage` dans `local.py`.
- **Export PDF en erreur** : Pango absent de l'image (installé par le `Dockerfile`).
- **Géocodage / Sirene en erreur** : pas d'Internet ; `GEOCODING_ENABLED=0` dans `.env` (puis `docker compose up -d`).
- **Dépôt « modifications locales »** (refus de `update.ps1`) : `git status`, valider ou annuler.
- **Générer une nouvelle `SECRET_KEY`** :
  ```bash
  uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
  (invalide les sessions en cours).

### 5.8 Première installation **(1re release)**
Le script `update.ps1` sert aux mises à jour, pas à la première installation.
- [ ] Prérequis : WSL2, Docker Desktop (démarrage à l'ouverture de session), Git, pare-feu Windows actif.
- [ ] Dépôt cloné dans un dossier sans espace ni accent (ex. `C:\RiskFlow\app`), sur le tag : `git checkout vX.Y.Z`.
- [ ] `.env` créé à partir de `.env.example` avec des valeurs **neuves** : `SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (fort, propre à cette installation), `INSEE_API_KEY` (idéalement une clé dédiée).
  ```bash
  docker compose build
  ```
  ```bash
  docker compose up -d db
  ```
  ```bash
  docker compose run --rm web python manage.py migrate
  ```
  ```bash
  docker compose run --rm web python manage.py createsuperuser
  ```
  ```bash
  docker compose up -d
  ```
- [ ] Redémarrage automatique vérifié (redémarrer le PC : l'application revient seule, `restart: unless-stopped`).
- [ ] Sauvegarde planifiée, copie hors du PC et **restauration testée** avant de saisir des données réelles.
- [ ] Recette complète sur la machine de production (clients, contacts, dossiers, templates, visites, recommandations, médias, thème, pages d'erreur, navigateurs cibles).

### 5.9 Entretien régulier
- **Revue mensuelle** : correctifs de sécurité Django (`uv lock --upgrade`, tests, nouvelle release), `docker compose build --pull` (images de base épinglées : `python:3.12-slim`, `postgres:16`, `uv:0.8`).
- **PostgreSQL** : version majeure épinglée à 16 ; une montée de version se fait par dump puis restauration dans un nouveau volume.
- **Python 3.12** supporté jusqu'en 2028.
- Contrôler régulièrement le dernier dossier de sauvegarde, l'espace disque (volume `media`, quota de 1 Go par dossier) et la copie hors du PC.
