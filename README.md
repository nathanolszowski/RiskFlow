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
- **CRM** : clients et contacts, avec pré-remplissage d'un client à partir de son SIRET via l'**API Sirene de l'INSEE** (forme juridique, activité NAF 2025, siège social). Une alerte signale un établissement fermé ou une entreprise cessée, et un bouton « Actualiser (Sirene) » compare la fiche aux données de l'API et applique, champ par champ, ce que l'utilisateur accepte.
- **Adresses certifiées** : autocomplétion et géocodage par la **Géoplateforme IGN** (sans clé), position sur une carte, et temps de trajet en voiture depuis le domicile de l'inspecteur (ou un autre point de départ) jusqu'au site, mémorisé et recalculé seulement à la demande.
- **Dossiers d'inspection** : création, suivi de l'avancement par phase, référence générée automatiquement (`DOS-<année>-<hex>`), filtres, tri et pagination.
- **Visites dynamiques** : les modèles de visite sont décrits en JSON (sections et champs `boolean`, `text`, `select`, `number`), leur structure est validée avec **Pydantic**, et chaque visite d'un dossier travaille sur sa propre copie du modèle. Les réponses sont validées et enregistrées à la volée, champ par champ, y compris après une coupure réseau.
- **Recommandations de prévention** rattachées à un dossier.
- **Médias** : photos, PDF, Excel, Word, PowerPoint et vidéos rattachés à un dossier, une visite ou une recommandation, à toutes les étapes de la mission. Images compressées avec Pillow (miniature, EXIF conservé : date, GPS, appareil), tags libres par utilisateur, limites de taille par type, quota approximatif par dossier avec barre de remplissage, fichiers privés servis uniquement à leur propriétaire. Voir [Gestion des médias](#gestion-des-médias-développement-et-production).
- **Archivage (soft delete) et suppression définitive** de tous les objets métier, avec cascades (dossier → visites, recommandations et médias, client → contacts), popups de confirmation et règles de protection (on n'efface qu'un objet préalablement archivé).
- **Traçabilité** : date et auteur de la création, de la dernière modification et de l'archivage.
- **Tests automatisés et CI** : suite de tests Django (factory_boy, API Sirene simulée) et workflow GitHub Actions. Voir [Tests](#tests).
- **Tableau de bord**, **recherche globale** et **thème clair / sombre**.

### Prévues

- Rapport de visite : interface en écran partagé, export PDF.
- Déploiement.
- À plus long terme : notifications, tableau de bord analytique, portail client, base de connaissances avec recherche sémantique (RAG avec `pgvector`), dont une interrogation des documents d'un dossier (Gemini, Celery + Redis).

## Stack technique

| Couche | Technologies |
| --- | --- |
| Back-end | Python 3.12, Django 6 |
| Base de données | PostgreSQL (via `psycopg` 3), `JSONField` pour les formulaires dynamiques |
| Front-end | Templates Django, HTMX (`django-htmx`), Tailwind CSS v4 (`django-tailwind`, binaire standalone, sans npm) |
| Validation | Pydantic 2 |
| Fichiers | Système de fichiers en dev, stockage S3 (Cloudflare R2) via `django-storages` en prod, Pillow pour les images |
| Intégrations | API Sirene (INSEE), référentiel de nomenclatures `id.insee.fr` (libellés NAF 2025), Géoplateforme IGN (géocodage, itinéraires, fond de carte), sans clé |
| Outillage | `uv` |

Le choix d'HTMX permet de limiter le JavaScript au strict minimum : les listes, formulaires en modale, onglets et confirmations sont des fragments HTML renvoyés par le serveur.

## Architecture

```
apps/
  accounts/    Utilisateur personnalisé et profil inspecteur
  core/        Code commun : modèle de traçabilité, layout, dashboard, recherche, thème
  crm/         Clients, contacts, client de l'API Sirene (siège, état administratif, NAF 2025)
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
uv run python manage.py test --settings=config.settings.test   # lancer les tests
```

### Tests

Les tests utilisent PostgreSQL (verrous `select_for_update`, contraintes `CHECK`) : le rôle de la base doit pouvoir créer une base de test.

```bash
sudo -u postgres psql -c "ALTER ROLE <utilisateur> CREATEDB;"   # une seule fois
uv run python manage.py test --settings=config.settings.test    # toute la suite
uv run python manage.py test inspections --settings=config.settings.test -v 2   # une app, avec la description de chaque test
uv run coverage run manage.py test --settings=config.settings.test && uv run coverage report
```

- Un paquet `tests/` par app, avec ses fabriques (`factories.py`) ; aucun appel réseau (API Sirene et service NAF simulés avec les fichiers de `apps/crm/tests/fixtures/`) ; fichiers écrits dans un dossier temporaire.
- Chaque module, classe et méthode de test a une docstring en anglais ; `uv run ruff check --select D1 apps/*/tests` le vérifie.
- La CI (`.github/workflows/ci.yml`) lance, sur chaque push et pull request vers `develop` et `main` : lint, format, docstrings des tests, contrôle des migrations, tests et couverture (seuil de 70 %).
- Le cloisonnement par utilisateur (dossiers, visites, recommandations, médias, templates privés, recherche globale des dossiers) est verrouillé par les tests d'isolation (`test_isolation.py`). Les clients et leurs contacts sont partagés entre utilisateurs, ce que vérifie `CrmSharingTests`.
- Ce que les tests ne couvrent pas (navigateur, réseau, tablette) se vérifie avec la [recette manuelle](#recette-manuelle).

### Contrôle des réglages de production

`DJANGO_SETTINGS_MODULE=config.settings.prod uv run python manage.py check --deploy` (avec `SECRET_KEY`, `ALLOWED_HOSTS`, `DB_*` et `AWS_*` renseignés) ne laisse que deux avertissements, volontaires :

- `security.W005` (`SECURE_HSTS_INCLUDE_SUBDOMAINS`) et `security.W021` (`SECURE_HSTS_PRELOAD`) : ces réglages engagent tous les sous-domaines (et, pour le preload, la liste des navigateurs, difficile à annuler). Ils ne sont à activer qu'une fois le nom de domaine définitif connu et entièrement servi en HTTPS.


## Recette manuelle

Les tests automatisés ne couvrent pas ce qui dépend du navigateur, du réseau et de l'appareil. Cette liste se déroule à la main, de préférence sur une tablette (iPad/Safari) et sur un poste avec les outils de développement (DevTools) ouverts. Cocher chaque ligne avant une livraison.

Préparation : un compte inspecteur, un dossier avec une visite préparée à partir d'un modèle contenant au moins un champ de chaque type (oui/non, texte, choix, nombre).

### Enregistrement à la volée hors ligne

- [ ] Ouvrir le formulaire de la visite, répondre à un champ : l'indicateur passe par « Enregistrement… » puis « Enregistré ».
- [ ] DevTools > Réseau > « Hors connexion » (ou mode avion sur la tablette), répondre à deux champs : les réponses restent affichées, l'indicateur affiche « Non enregistré · nouvelle tentative » et un bandeau « Connexion perdue » apparaît (les réponses sont gardées dans `localStorage`, DevTools > Application).
- [ ] Rétablir le réseau sans recharger la page : les réponses sont renvoyées d'elles-mêmes dans l'ordre (nouvelle tentative automatique ou événement « online »), le bandeau disparaît et l'indicateur repasse à « Enregistré ». Recharger la page : les réponses sont toujours là.
- [ ] Refaire l'étape hors ligne, puis tenter de **fermer l'onglet** sans rétablir le réseau : le navigateur demande confirmation (réponses non enregistrées). Fermer quand même, puis rouvrir le formulaire avec le réseau : les réponses gardées dans `localStorage` (clé `visit-<id>-pending`) sont renvoyées, puis la clé est vidée.
- [ ] Hors ligne, saisir une valeur que le serveur refusera (nombre hors des bornes) puis revenir en ligne : au renvoi, le message d'erreur s'affiche sous le champ, la valeur n'est pas enregistrée et elle ne reste pas en attente.
- [ ] Terminer ou archiver la visite depuis un autre onglet, puis répondre dans le premier : bandeau « Cette visite est terminée ou archivée » et réponse abandonnée.

### File d'attente des enregistrements

- [ ] Saisir rapidement dans plusieurs champs à la suite (tabulation entre champs, sans attendre) : aucune réponse n'est perdue ni enregistrée dans le désordre (la dernière valeur d'un champ est celle qui reste).
- [ ] Avec la limitation du réseau sur « 3G lent » (DevTools), répéter : la file ne bloque pas la saisie.
- [ ] Le compteur de la révision augmente à chaque enregistrement (vérifiable dans l'administration, champ « Révision des réponses »).

### Expiration de session

- [ ] Ouvrir le formulaire de visite et rester inactif plus de 5 minutes : la page continue de signaler sa présence (appels `session/ping/` toutes les 5 minutes dans l'onglet Réseau) et la session reste ouverte.
- [ ] Dans l'administration Django, supprimer la session de l'utilisateur (ou vider le cookie `sessionid`), puis répondre à un champ : l'application répond 401 sans rediriger, l'indicateur affiche « Non enregistré · session expirée », la réponse reste dans `localStorage` et un bandeau invite à se reconnecter dans un autre onglet.
- [ ] Se reconnecter dans un autre onglet, revenir au formulaire : la réponse en attente est renvoyée à la nouvelle tentative suivante.
- [ ] Sur une autre page (liste des dossiers), laisser la session expirer puis cliquer : la page de connexion s'affiche, et après connexion on revient à la page demandée.

### Fichiers refusés

- [ ] Envoyer un fichier d'un format non accepté (`.exe`, `.heic`) : un pop-up explicatif s'affiche avant l'envoi, rien n'est enregistré.
- [ ] Envoyer un PDF au-delà de la limite (`MEDIA_MAX_PDF_MB` réduite dans `.env` pour le test) : le pop-up donne la limite.
- [ ] Envoyer un lot mêlant un fichier valide et un fichier refusé : le fichier valide apparaît dans l'onglet Médias, le refus est expliqué.
- [ ] Renommer un fichier texte en `.pdf` et l'envoyer : refus (contenu différent de l'extension).
- [ ] Remplir le quota du dossier (`MEDIA_FOLDER_QUOTA_MB` réduit) : la barre passe à l'orange puis au rouge, et un nouvel envoi est refusé avec le message de quota.
- [ ] Envoyer une photo prise avec l'appareil de la tablette : orientation correcte, miniature présente, date et position affichées.

### Lecture vidéo sur Safari / iPad

- [ ] Envoyer une vidéo `.mp4` et une `.mov` filmées avec l'iPad, puis les ouvrir depuis l'onglet Médias : la lecture démarre.
- [ ] Se déplacer dans la vidéo (barre de progression) : la lecture reprend à l'endroit choisi (le serveur répond en `206 Partial Content`, onglet Réseau).
- [ ] Même vérification avec le stockage S3/R2 en préproduction (redirection vers l'URL signée).

### Autres contrôles sur tablette

- [ ] Les boutons restent utilisables au doigt (formulaire de visite, modales, onglets).
- [ ] Le thème clair / sombre persiste après un rechargement et une navigation.
