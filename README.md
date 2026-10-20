# RISKFLOW

Je souhaitais réaliser une application fullstack pour mon portfolio mais je ne voulais pas que ce soit une coquille vide, une application sans intention, ni objectifs réels. Je voulais qu’elle puisse répondre à un véritable cas d’usage que l’on retrouverait dans une entreprise réelle. Il se trouve qu’un membre de ma famille travaille dans le domaine des assurances en tant qu’inspecteur de risque et que dans son entreprise, ils n’ont pas encore de solution logicielle pour les aider à structurer et rassembler toutes leurs données et flux de travail à un seul endroit. Je me suis donc appuyé sur ses besoins métier pour créer l’application.

> "Des nains sur des épaules de géants"
*Bertrand de Chartres*

## État du projet

Projet personnel en cours de développement, réalisé par sprints : fondations, cœur métier et CRM sont en place ; la gestion des médias est en place ; le rapport de visite, la sécurité et le déploiement sont les prochaines étapes. La configuration actuelle est une configuration de **développement** et n'est pas destinée à la production.

## Le métier en bref

L'inspecteur de risques intervient **en amont de la souscription** d'un contrat d'assurance (ce n'est pas de l'expertise sinistre). Il évalue un site industriel ou commercial, identifie les risques (incendie, intrusion, process…) et formule des recommandations de prévention. Une mission suit cinq étapes :

1. **Préparation** : collecte des informations sur le client et le site.
2. **Entretien** avec les interlocuteurs du client.
3. **Visite terrain** guidée par un questionnaire structuré.
4. **Rapport** consolidant les observations.
5. **Suivi des recommandations** émises.

RiskFlow vise à rassembler ce flux de travail, aujourd'hui éclaté entre tableurs, documents et e-mails, dans une seule application pensée pour le terrain (tablette, gros boutons).

## Fonctionnalités

### Disponibles

- **Authentification** : utilisateur personnalisé et profil inspecteur, sessions expirant après 60 minutes d'inactivité.
- **CRM** : clients et contacts, avec pré-remplissage d'un client à partir de son SIRET via l'**API Sirene de l'INSEE**.
- **Dossiers d'inspection** : création, suivi de l'avancement par phase, référence générée automatiquement (`DOS-<année>-<hex>`), filtres, tri et pagination.
- **Visites dynamiques** : les modèles de visite sont décrits en JSON (sections et champs `boolean`, `text`, `select`, `number`), leur structure est validée avec **Pydantic**, et chaque visite d'un dossier est instanciée à partir d'un modèle.
- **Recommandations de prévention** rattachées à un dossier.
- **Médias** : photos, PDF, Excel, Word, PowerPoint et vidéos rattachés à un dossier, une visite ou une recommandation, à toutes les étapes de la mission. Images compressées avec Pillow (miniature, EXIF conservé : date, GPS, appareil), tags libres par utilisateur, limites de taille par type, quota approximatif par dossier avec barre de remplissage, fichiers privés servis uniquement à leur propriétaire. Voir [Gestion des médias](#gestion-des-médias-développement-et-production).
- **Archivage (soft delete) et suppression définitive** de tous les objets métier, avec cascades (dossier → visites, recommandations et médias, client → contacts), popups de confirmation et règles de protection (on n'efface qu'un objet préalablement archivé).
- **Traçabilité** : date et auteur de la création, de la dernière modification et de l'archivage.
- **Tableau de bord**, **recherche globale** et **thème clair / sombre**.

### Prévues

- Rapport de visite : interface en écran partagé, export PDF.
- Cloisonnement complet des données par inspecteur.
- Validation des réponses d'une visite contre son modèle.
- Tests automatisés, séparation des environnements dev / prod, CI GitHub Actions et déploiement.
- À plus long terme : notifications, tableau de bord analytique, portail client, base de connaissances avec recherche sémantique (RAG avec `pgvector`), dont une interrogation des documents d'un dossier (Gemini, Celery + Redis).

## Stack technique

| Couche | Technologies |
| --- | --- |
| Back-end | Python 3.12, Django 6 |
| Base de données | PostgreSQL (via `psycopg` 3), `JSONField` pour les formulaires dynamiques |
| Front-end | Templates Django, HTMX (`django-htmx`), Tailwind CSS v4 (`django-tailwind`, binaire standalone, sans npm) |
| Validation | Pydantic 2 |
| Fichiers | Système de fichiers en dev, stockage S3 (Cloudflare R2) via `django-storages` en prod, Pillow pour les images |
| Intégrations | API Sirene (INSEE) |
| Outillage | `uv` |

Le choix d'HTMX permet de limiter le JavaScript au strict minimum : les listes, formulaires en modale, onglets et confirmations sont des fragments HTML renvoyés par le serveur.

## Architecture

```
apps/
  accounts/    Utilisateur personnalisé et profil inspecteur
  core/        Code commun : modèle de traçabilité, layout, dashboard, recherche, thème
  crm/         Clients, contacts, client de l'API INSEE
  inspections/ Dossiers, modèles et instances de visite, recommandations
  medias/      Fichiers joints (images, documents, vidéos), tags, quota, stockage
  theme/       Configuration Tailwind et tokens de thème
config/        Settings et routage du projet
```

Quelques principes :

- **Couche services** : la logique métier et les requêtes vivent dans `<app>/services/`, pas dans les vues. Les vues restent fines (authentification, méthode HTTP, appel du service, rendu), ce qui prépare l'exposition future d'une API.
- **`TrackingModel`** : modèle abstrait commun à la plupart des entités métier, qui gère horodatage, auteurs et archivage, avec des hooks de cascade surchargeables.
- **Archiver avant de supprimer** : la suppression définitive n'est possible que sur un objet déjà archivé.

## Installation locale

### Prérequis

- Python 3.12 et [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Une clé d'API Sirene, à obtenir sur le [portail des API de l'INSEE](https://portail-api.insee.fr/) (facultative, seulement pour le pré-remplissage par SIRET)

### Mise en route

```bash
git clone https://github.com/nathanolszowski/RiskFlow.git
cd RiskFlow
uv sync
```

Créer un fichier `.env` à la racine (il est ignoré par Git) :

```env
DB_NAME=riskflow
DB_USER=<utilisateur>
DB_PASSWORD=<mot_de_passe>
DB_HOST=localhost
DB_PORT=5432
INSEE_API_KEY=<votre_cle>
```

Puis appliquer les migrations, créer un administrateur et lancer le serveur :

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py tailwind dev
```

`tailwind dev` lance à la fois le serveur Django et le watcher Tailwind. L'application est alors accessible sur <http://127.0.0.1:8000/auth/login/>. Les modèles de visite se créent depuis l'administration Django (`/admin/`).

### Gestion des médias (développement et production)

Les fichiers ne sont **jamais** servis par une URL publique : les vues `medias:media_file` et `medias:media_thumbnail` vérifient que l'utilisateur est le propriétaire du dossier avant d'envoyer le fichier.

| | Développement | Production |
| --- | --- | --- |
| Settings | `config.settings.dev` (défaut de `manage.py`) | `DJANGO_SETTINGS_MODULE=config.settings.prod` |
| Stockage | Dossier local `media/` à la racine (`MEDIA_ROOT`, ignoré par Git) | Bucket S3 privé, Cloudflare R2 par défaut |
| Envoi du fichier | Streamé par Django (requêtes `Range` gérées, nécessaire pour lire les vidéos sur iPad/Safari) | Redirection vers une URL pré-signée valable 5 minutes |
| Configuration | Aucune | Variables `AWS_*` obligatoires (voir ci-dessous) |

**Développement** : rien à configurer. Les fichiers sont écrits dans `media/folders/<id du dossier>/` sous un nom aléatoire. Supprimer un média (ou son dossier) supprime aussi le fichier. Pour repartir de zéro, supprimer le dossier `media/` en même temps que la base.

**Production (Cloudflare R2, via le protocole S3 standard)** :

1. Dans Cloudflare, créer un bucket **privé** : ne pas activer l'accès public `r2.dev` ni de domaine personnalisé public.
2. Créer un jeton d'API R2 limité à ce bucket, avec les droits « Object Read & Write ».
3. Renseigner les variables d'environnement (voir `.env.example`) :

   ```env
   DJANGO_SETTINGS_MODULE=config.settings.prod
   AWS_STORAGE_BUCKET_NAME=<bucket>
   AWS_S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
   AWS_ACCESS_KEY_ID=<cle>
   AWS_SECRET_ACCESS_KEY=<secret>
   AWS_S3_REGION_NAME=auto
   ```

4. Appliquer les migrations (`uv run python manage.py migrate`).
5. Sur le reverse proxy, autoriser les gros envois : `client_max_body_size 100m;` pour nginx (au moins la plus grosse limite, celle des vidéos). Django ne limite pas la taille totale d'une requête.

Aucun code n'est propre à R2 : pour utiliser **AWS S3**, laisser `AWS_S3_ENDPOINT_URL` vide et renseigner la région. Pour migrer des fichiers déjà envoyés en développement vers le bucket, copier `media/` à la racine du bucket (les chemins `folders/...` sont ceux enregistrés en base), par exemple :

```bash
aws s3 sync media/ s3://<bucket>/ --endpoint-url https://<account_id>.r2.cloudflarestorage.com
```

**Limites** (variables optionnelles, en Mo) :

| Variable | Défaut | Portée |
| --- | --- | --- |
| `MEDIA_MAX_IMAGE_MB` | 25 | Image reçue (avant compression) |
| `MEDIA_MAX_PDF_MB` | 25 | PDF |
| `MEDIA_MAX_OFFICE_MB` | 25 | Excel, Word, PowerPoint |
| `MEDIA_MAX_VIDEO_MB` | 100 | Vidéo (mp4, mov, webm), stockée telle quelle |
| `MEDIA_FOLDER_QUOTA_MB` | 500 | Quota approximatif par dossier, médias archivés compris |

Un fichier refusé (format, taille, quota) ouvre un pop-up explicatif ; les images de plus de 50 mégapixels sont refusées. Les formats HEIC ne sont pas acceptés.

### Commandes utiles

```bash
uv run python manage.py runserver        # serveur seul
uv run python manage.py tailwind build   # compiler le CSS
uv run python manage.py test             # lancer les tests
```

