# RISKFLOW

Je souhaitais réaliser une application fullstack pour mon portfolio mais je ne voulais pas que ce soit une coquille vide, une application sans intention, ni objectifs réels. Je voulais qu’elle puisse répondre à un véritable cas d’usage que l’on retrouverait dans une entreprise réelle. Il se trouve qu’un membre de ma famille travaille dans le domaine des assurances en tant qu’inspecteur de risque et que dans son entreprise, ils n’ont pas encore de solution logicielle pour les aider à structurer et rassembler toutes leurs données et flux de travail à un seul endroit. Je me suis donc appuyé sur ses besoins métier pour créer l’application.

> "Des nains sur des épaules de géants"
*Bertrand de Chartres*

## État du projet

Projet personnel en cours de développement, réalisé par sprints : fondations, cœur métier et CRM sont en place ; le rapport de visite, la sécurité et le déploiement sont les prochaines étapes. La configuration actuelle est une configuration de **développement** et n'est pas destinée à la production.

## Le métier en bref

L'inspecteur de risques intervient **en amont de la souscription** d'un contrat d'assurance (ce n'est pas de l'expertise sinistre). Il évalue un site industriel ou commercial, identifie les risques (incendie, intrusion, process…) et formule des recommandations de prévention. Une mission suit cinq étapes :

1. **Préparation** : collecte des informations sur l'entreprise et le site.
2. **Entretien** avec les interlocuteurs du client.
3. **Visite terrain** guidée par un questionnaire structuré.
4. **Rapport** consolidant les observations.
5. **Suivi des recommandations** émises.

RiskFlow vise à rassembler ce flux de travail, aujourd'hui éclaté entre tableurs, documents et e-mails, dans une seule application pensée pour le terrain (tablette, gros boutons).

## Fonctionnalités

### Disponibles

- **Authentification** : utilisateur personnalisé et profil inspecteur, sessions expirant après 10 minutes d'inactivité.
- **CRM** : sociétés et contacts, avec pré-remplissage d'une société à partir de son SIRET via l'**API Sirene de l'INSEE**.
- **Dossiers d'inspection** : création, suivi de l'avancement par phase, référence générée automatiquement (`DOS-<année>-<hex>`), filtres, tri et pagination.
- **Visites dynamiques** : les modèles de visite sont décrits en JSON (sections et champs `boolean`, `text`, `select`, `number`), leur structure est validée avec **Pydantic**, et chaque visite d'un dossier est instanciée à partir d'un modèle.
- **Recommandations de prévention** rattachées à un dossier.
- **Archivage (soft delete) et suppression définitive** de tous les objets métier, avec cascades (dossier → visites et recommandations, société → contacts), popups de confirmation et règles de protection (on n'efface qu'un objet préalablement archivé).
- **Traçabilité** : date et auteur de la création, de la dernière modification et de l'archivage.
- **Tableau de bord**, **recherche globale** et **thème clair / sombre**.

### Prévues

- Rapport de visite : interface en écran partagé, gestion des photos et documents, export PDF.
- Cloisonnement complet des données par inspecteur.
- Validation des réponses d'une visite contre son modèle.
- Tests automatisés, séparation des environnements dev / prod, CI GitHub Actions et déploiement.
- À plus long terme : notifications, tableau de bord analytique, portail client, base de connaissances avec recherche sémantique (RAG avec `pgvector`).

## Stack technique

| Couche | Technologies |
| --- | --- |
| Back-end | Python 3.12, Django 6 |
| Base de données | PostgreSQL (via `psycopg` 3), `JSONField` pour les formulaires dynamiques |
| Front-end | Templates Django, HTMX (`django-htmx`), Tailwind CSS v4 (`django-tailwind`, binaire standalone, sans npm) |
| Validation | Pydantic 2 |
| Intégrations | API Sirene (INSEE) |
| Outillage | `uv` |

Le choix d'HTMX permet de limiter le JavaScript au strict minimum : les listes, formulaires en modale, onglets et confirmations sont des fragments HTML renvoyés par le serveur.

## Architecture

```
accounts/      Utilisateur personnalisé et profil inspecteur
config/        Settings et routage du projet
core/          Code commun : modèle de traçabilité, layout, dashboard, recherche, thème
crm/           Sociétés, contacts, client de l'API INSEE
inspections/   Dossiers, modèles et instances de visite, recommandations
theme/         Configuration Tailwind et tokens de thème
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

### Commandes utiles

```bash
uv run python manage.py runserver        # serveur seul
uv run python manage.py tailwind build   # compiler le CSS
uv run python manage.py test             # lancer les tests
```

