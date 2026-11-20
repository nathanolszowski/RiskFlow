# RiskFlow — Architecture technique et modèle de données

Dernière modification : 17/11/2026 (stack et dépendances) à 11:26 par Nathan

## Stack

| Couche | Choix | Version utilisée | Raison |
|---|---|---|---|
| Langage | Python | 3.12 (`.python-version`) | Supporté jusqu'en 2028 |
| Backend | Django | 6.0.6 | Vitesse de développement, panel d'administration natif |
| Architecture | Couche services | — | Isoler la logique métier et préparer la migration vers une API |
| Base de données | PostgreSQL, via `psycopg[binary]` | PostgreSQL 16 (dev, CI et Docker), psycopg 3.3.4 | `JSONB` natif pour les formulaires d'inspection dynamiques ; `pgvector` pour les vecteurs (prévu) |
| Frontend | HTMX, via `django-htmx` | HTMX 1.9.10 (CDN unpkg), django-htmx 1.27.0 | Navigation par étapes sans rechargement, sauvegarde automatique à la saisie, sans JavaScript complexe |
| JavaScript | Vanilla JS, sans build | — | Seulement là où HTMX ne suffit pas : enregistrement à la volée et file `localStorage` des visites, contrôle avant envoi des médias, autocomplétion d'adresse, carte |
| Cartographie | Leaflet + tuiles WMTS de la Géoplateforme IGN | Leaflet 1.9.4 (CDN unpkg) | Carte des adresses de clients et de dossiers, sans clé |
| CSS | Tailwind CSS via `django-tailwind` | Tailwind 4.3.3 (binaire standalone via `pytailwindcss`, sans npm), django-tailwind 4.5.0 | Prototypage rapide, gros boutons terrain, thèmes clair/sombre par variables CSS (pas de daisyUI) |
| Validation | Pydantic | 2.13.4 | Valide la structure JSON des modèles de visite (à la place de `jsonschema`) |
| PDF | WeasyPrint (Pango requis) | 70.0 | Export PDF vierge d'un formulaire de visite, puis rapports, depuis des templates HTML |
| Fichiers | Système de fichiers local (`MEDIA_ROOT`), Pillow | Pillow 13.0.0 | Un seul utilisateur, un seul PC : volume Docker, sauvegardé avec la base ; compression, orientation, miniatures, lecture EXIF |
| Géographie | Géoplateforme IGN (géocodage, itinéraire `bdtopo-osrm`) | API publiques, sans clé | Certification des adresses et estimation des trajets ; Mapbox et Nominatim écartés |
| Serveur d'application | gunicorn | 27.0.1 | 2 workers, timeout 120 s, dans le conteneur `web` |
| Fichiers statiques | WhiteNoise | 6.12.0 | Sert CSS et JS dans Docker sans serveur web devant gunicorn |
| Conteneurs | Docker Compose | `python:3.12-slim`, `postgres:16`, uv 0.8 | Installation et mises à jour reproductibles sur le PC Windows |
| IA | Gemini | non intégré (prévu) | Accès gratuit limité, dont des modèles d'embeddings pour le RAG interne |
| Outillage | `uv`, Ruff, coverage | uv 0.8, Ruff 0.17.1, coverage 7.16.2 | Paquets et projet (`pyproject.toml`, `uv.lock`), lint et formatage, couverture |
| CI | GitHub Actions | — | Lint, format, docstrings des tests, migrations, tests, couverture ≥ 70 %, build de l'image |

### Dépendances Python

Dépendances d'exécution (`[project.dependencies]`, versions résolues dans `uv.lock`) :

| Paquet | Version | Usage |
|---|---|---|
| `django` | 6.0.6 | Framework |
| `django-htmx` | 1.27.0 | `request.htmx`, middleware HTMX |
| `django-json-widget` | 2.1.1 | Édition du JSON des modèles de visite dans l'admin |
| `django-tailwind[cookiecutter,honcho,reload]` | 4.5.0 | App `theme`, commandes `tailwind dev` / `tailwind build` ; tire `pytailwindcss` 0.3.1 (binaire standalone), `honcho` 2.0.0 (Procfile du mode dev) et `django-browser-reload` 1.21.0 (dev uniquement : ajouté par `dev.py`, retiré des settings de test) |
| `gunicorn` | 27.0.1 | Serveur WSGI de l'image Docker |
| `pillow` | 13.0.0 | Traitement des images (`medias/services/images.py`) |
| `psycopg[binary]` | 3.3.4 | Pilote PostgreSQL |
| `pydantic` | 2.13.4 | Schémas des templates de visite (`inspections/validators.py`) |
| `python-dotenv` | 1.2.2 | Lecture de `.env` |
| `requests` | 2.34.2 | Appels HTTP : Sirene, `id.insee.fr`, Géoplateforme |
| `weasyprint` | 70.0 | Génération PDF (`inspections/services/visit_pdf.py`) ; tire `pydyf`, `tinycss2`, `cssselect2`, `tinyhtml5`, `fonttools`, `pyphen`, `cffi` |
| `whitenoise` | 6.12.0 | Statiques en `config.settings.local` |

Dépendances de développement (groupe `dev`, absentes de l'image : `uv sync --no-dev`) :

| Paquet | Version | Usage |
|---|---|---|
| `coverage` | 7.16.2 | Couverture des tests (seuil 70 % en CI) |
| `django-stubs` | 6.1.2 | Annotations de typage de Django |
| `factory-boy` | 3.3.3 | Données de test (`tests/factories.py` de chaque app) |
| `ruff` | 0.17.1 | Lint (`E`, `F`, `I`, `RUF100`, `TC`), formatage, docstrings Google des tests (`D1`) |

Dépendances système : Pango (`libpango-1.0-0`, `libpangoft2-1.0-0`) et une police (`fonts-dejavu-core`) pour WeasyPrint, installées dans le `Dockerfile` ; en local sous WSL : `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`.

Ressources front chargées par CDN (unpkg, versions épinglées) : `htmx.org@1.9.10` dans `core/base.html`, `leaflet@1.9.4` (CSS et JS) dans les pages dossier et client. Elles exigent un accès à Internet.

Abandonnées ou non retenues : `django-storages[s3]` et `boto3` (stockage S3 / R2, retiré avec l'hébergement en ligne), `jsonschema` (remplacée par Pydantic).

### APIs externes

| Service | Clé | Usage |
|---|---|---|
| API Sirene (INSEE) | `INSEE_API_KEY` | Pré-remplir et actualiser un client depuis son SIRET : établissement, siège social, état administratif, activité NAF 2025 (`crm/services/company.py`) |
| Nomenclatures `id.insee.fr` (JSON-LD) | aucune | Libellé NAF 2025 (`crm/services/naf.py`) |
| Géoplateforme IGN — géocodage (`data.geopf.fr/geocodage`) | aucune | Certification et autocomplétion des adresses (`core/services/geo/geocoding.py`) |
| Géoplateforme IGN — itinéraire (`data.geopf.fr/navigation/itineraire`, ressource `bdtopo-osrm`) | aucune | Estimation des trajets, France seulement (`core/services/geo/routing.py`, `inspections/services/travel.py`) |
| Géoplateforme IGN — tuiles WMTS | aucune | Fond de carte Leaflet |

La forme juridique est un code INSEE, traduit par une table en dur (`crm/services/legal_forms.py`). `GEOCODING_ENABLED=0` coupe tout appel à la Géoplateforme (hors ligne ; valeur des settings de test). Aucun appel réseau dans les tests : les réponses viennent de fixtures réelles (`crm/tests/fixtures/`, `core/tests/fixtures/geopf_*.json`).

## Structure du projet

```
RiskFlow/
├── .github/workflows/ci.yml   # CI GitHub Actions
├── apps/
│   ├── accounts/        # authentification, CustomUser, profil Inspector
│   ├── crm/             # clients et contacts, client API Sirene
│   │   └── services/    # company.py, contact.py, naf.py, legal_forms.py
│   ├── core/            # code commun, layouts, dashboard, recherche, thème
│   │   ├── services/    # helpers génériques, dashboard.py, directory.py, geo/ (geocoding.py, routing.py)
│   │   └── static/core/ # address_autocomplete.js, address_map.js
│   ├── medias/          # fichiers joints, tags, quota, stockage
│   │   └── services/    # validation.py, images.py, media.py, tags.py
│   ├── inspections/     # dossiers d'inspection, visites, templates, recommandations
│   │   ├── services/    # inspectionfolder.py, visit.py, visit_pdf.py, template.py, recommandation.py, travel.py
│   │   ├── static/inspections/  # visit_form.js
│   │   ├── templates/inspections/  # pages, partials/<entité>/, pdf/
│   │   ├── validators.py           # schémas Pydantic
│   │   └── tests/       # un paquet tests/ par app : factories.py, test_<sujet>.py
│   └── theme/           # django-tailwind : static_src/src/styles.css (tokens), static/css (CSS compilé)
├── config/
│   ├── settings/        # base.py, dev.py, local.py (Docker), test.py
│   └── urls.py
├── scripts/             # backup.ps1, update.ps1 (PC Windows)
├── compose.yaml         # services web et db
├── Dockerfile
├── .dockerignore
├── .env.example
├── manage.py
├── Procfile.tailwind
├── pyproject.toml       # dépendances, configuration Ruff et coverage
├── uv.lock
├── .python-version
└── README.md
```

Principes :
- respecter les approches conceptuelles de Django ;
- toutes les applications dans `apps/` ;
- la logique métier dans `services/`, pas dans les vues ;
- les fragments HTMX dans `templates/<app>/partials/`.

L'app `medias` regroupe les fichiers joints (modèle, validation, compression, quota, vues et onglet). Une app `reports` est prévue pour la consolidation et la génération du rapport (sprint 4).

## Modèle de données

`InspectionFolder` est l'entité mère : elle contient toutes les étapes et pièces du processus de l'inspecteur.

### InspectionFolder
- `reference` (générée automatiquement, création contrainte)
- `company` [FK vers Company, « Client » dans l'interface]
- `contact` lié au dossier (doit appartenir au client)
- `current_phase` : Création, Préparation, Visite, Rapport, Suivi, Clôturé, Archivé (un nouveau dossier démarre en Préparation)
- `notes`
- adresse du site de l'inspection

Properties : `count_all_recommandations`, `count_all_visits`, `get_latest_visit`.

### VisitTemplate
- `name`
- `description`
- `schema` (JSONField : définition du formulaire)
- `shared`

### VisitInstance
- `folder` [FK]
- `template`
- `instance_schema` (copie ajustable du schéma du modèle)
- `data` (JSONField : réponses de l'inspecteur)
- `current_status`
- `date`
- `notes`
- `start_time`
- `end_time`

Le schéma d'un modèle de visite (`VisitTemplate.schema`) est validé par Pydantic (`inspections/validators.py`). Les réponses de l'inspecteur (`VisitInstance.data = {"answers": {...}}`) sont validées contre la copie du schéma de la visite (`validate_answers`, `inspections/validators.py`), champ par champ à l'enregistrement et avec les champs obligatoires à « Terminer la visite ».

### Recommandation
- `folder` [FK]
- `description`
- `topic`
- `priority`
- `notes`
- `current_status`
- `due_date`

### Company (« Client » dans l'interface)
- `reference` (générée, en lecture seule), `name`, `address`, `business_line` (code NAF rév. 2)
- `siret`, `siren`, `vat_number`
- `company_size_category`, `legal_structure` (code INSEE, affiché avec son libellé)
- `nb_employees` (facultatif), `creation_date`
- `labels`, `executive_board`, `website`
- Données Sirene, jamais saisies à la main : `administrative_state` (`A` actif, `F` établissement fermé, `C` entreprise cessée), `closure_date`, `headquarters_siret`, `headquarters_address`, `headquarters_state`, `activity_naf25`, `activity_naf25_label`

Cycle Sirene : à la création, le serveur relit le SIRET et stocke ces champs ; ensuite le bouton « Actualiser (Sirene) » propose les différences, champ par champ. `siret`, `website`, `labels`, `executive_board`, `nb_employees` et les contacts ne sont jamais modifiés par Sirene.

### Contact
- `company` [FK]
- `first_name`, `last_name`, `position`, `email`
- `phone_number_fix`, `phone_number_mobile`

### TrackingModel
Base abstraite (`core/models.py`) de presque tous les modèles métier ; `created_by` est obligatoire :
- `created_at`, `updated_at`, `archived_at`
- `is_active`
- `created_by`, `updated_by`, `archived_by`

Méthodes `archive(user)` / `unarchive(user)` avec hooks `cascade_archive` / `cascade_unarchive`. Le désarchivage efface `archived_at` et `archived_by` : la trace de l'archivage n'est conservée que tant que l'objet est archivé.

Cascades implémentées :
- `InspectionFolder` : visites, recommandations et médias archivés avec la même `archived_at` que le dossier ; au désarchivage, seules celles-ci sont réactivées.
- `Company` : contacts actifs archivés avec la même date, sauf ceux référencés par un dossier actif ; aucune réactivation au désarchivage.

Suppression définitive : `delete_archived_instance` (`core/services/__init__.py`) refuse un objet actif. Contraintes de base : `InspectionFolder.company` est en `PROTECT` (un client avec dossiers ne peut pas être supprimé), `Contact.company` en `CASCADE`, `InspectionFolder.contact` en `SET_NULL` (la suppression d'un contact référencé est bloquée par l'application).

### Media (`medias`)
Hérite de `TrackingModel`.
- `folder` [FK, `CASCADE`, obligatoire] : porte le cloisonnement (`folder__created_by`)
- `visit` [FK `VisitInstance`, `SET_NULL`, facultatif] et `recommandation` [FK `Recommandation`, `SET_NULL`, facultatif] : au plus une des deux (contrainte en base), du même dossier ; supprimer la visite ou la recommandation conserve le média sur le dossier
- `file`, `thumbnail` (images), `original_name`, `content_type` (déduit de l'extension), `media_type` (`image`, `pdf`, `excel`, `word`, `powerpoint`, `video`), `size` (octets, après compression)
- `metadata` (JSON) : EXIF utile d'une photo (`taken_at`, `latitude`, `longitude`, `camera`)
- `title` (légende), `notes`, `tags` [M2M `MediaTag`]

`MediaTag` (hérite de `TrackingModel`) : `name`, unique par utilisateur sans tenir compte de la casse, créé à la volée.

Règles : types acceptés `jpg/jpeg/png/webp`, `pdf`, `xls/xlsx`, `doc/docx`, `ppt/pptx`, `mp4/mov/webm` (HEIC non géré) ; extension et signature des premiers octets contrôlées ; taille maximale par type (`MEDIA_MAX_SIZE_BY_TYPE`, vidéo 100 Mo, autres 25 Mo) ; images limitées à 50 Mpx puis ramenées à 2000 px, JPEG à 80 %, miniature 400 px, EXIF conservé ; quota approximatif de 1 Go (1024 Mo, `MEDIA_FOLDER_QUOTA_MB`) par dossier (médias archivés compris). Aucun `MEDIA_URL` : le fichier n'est joignable que par les vues `media_file` / `media_thumbnail`, après contrôle du propriétaire.

## Environnements et déploiement

Application mono-utilisateur sur un PC Windows, accessible uniquement depuis ce PC. Aucun hébergement en ligne.

**Développement** : WSL2, `runserver`, PostgreSQL local (base `riskflow_dev`), fichiers dans `media/` (ignoré par Git, streamés par Django avec gestion des requêtes `Range`), `.env` exclu de Git.

**Usage réel (Docker Compose, `config.settings.local`)** :
- `Dockerfile` (Python 3.12, `uv sync --frozen`, build Tailwind, `collectstatic`, gunicorn) et `compose.yaml` : services `web` et `db` (PostgreSQL 16, comme la CI), port publié sur `127.0.0.1:8000` seulement ;
- volumes `pgdata`, `media`, `logs` ; HTTP simple sur localhost (pas de HTTPS, HSTS ni cookies sécurisés) ; WhiteNoise pour les statiques ;
- releases par tags Git `vX.Y.Z` ; `scripts/update.ps1` (sauvegarde, build, migrations, test de santé, retour arrière) et `scripts/backup.ps1` (dump PostgreSQL + médias) ;
- sauvegardes planifiées via le Planificateur de tâches Windows, vers un autre disque ou un dossier synchronisé.

**CI (GitHub Actions)** : lint et formatage (Ruff), docstrings des tests, contrôle des migrations, tests et couverture, construction de l'image Docker. Pas d'environnements GitHub ni de déploiement automatique.

## IA et RAG (prévu, non développé)

- LLM et embeddings chez le fournisseur (Gemini) via clé API.
- Orchestration asynchrone côté serveur pour ne pas bloquer l'utilisateur lors de l'ingestion de gros documents.
- Vecteurs dans PostgreSQL avec `pgvector` : métadonnées métier et données sémantiques dans le même moteur, jointures simples, pas de base vectorielle externe.
- Pipeline sans framework lourd :
  1. Ingestion : extraction du texte (PDF, Word, Excel, PowerPoint ; périmètre par dossier ; point d'entrée `create_media` ; tâche lancée dans le conteneur `web` ou file adossée à PostgreSQL, sans Redis) en tâche de fond → découpage en blocs → vectorisation → stockage.
  2. Interrogation : vectorisation de la question → recherche sémantique → envoi des meilleurs extraits au LLM → réponse ou recommandation.

Outils de recherche web notés comme pistes : Firecrawl, Brave API, Staan API, LightOn, Linkup.

## Décisions ouvertes

- **Tâches asynchrones** : pas de Celery ni Redis (services en trop pour un PC) ; commande de gestion ou Django-Q2 adossé à PostgreSQL.
- **Ressources CDN** : HTMX et Leaflet viennent d'unpkg ; les servir en statique supprimerait la dépendance à Internet pour l'interface.
