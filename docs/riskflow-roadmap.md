# RiskFlow — Roadmap et état d'avancement

Dernière modification : 20/11/2026 par Nathan

## Sprints

### Sprint 1 — Fondations et modélisation : terminé
- Projet Django initialisé, PostgreSQL, Tailwind CSS et HTMX dans les templates de base.
- `accounts` : modèle utilisateur personnalisé, rôle « Inspector ».
- `inspections` : modèles `InspectionFolder`, `VisitTemplate` (schéma en `JSONField`), `VisitInstance` (réponses en `JSONField`), `Recommandation`.
- CRM : modèle client.
- Django Admin configuré pour qu'un administrateur crée les `VisitTemplate` directement.

### Sprint 2 — Cœur métier et couche services : terminé
- Logique modèle de visite / instance de visite dans les services.
- Validation des réponses de l'inspecteur contre le schéma du `VisitTemplate`.
- **Reste** : tests unitaires sur les services + logique modèle de visite (validation complète par pydantic)

### Sprint 3 — CRM : terminé
- Accès à l'API Sirene.
- Modèle contact.
- Formulaires contacts et clients, pré-remplissage par SIRET.
- Templates clients.
- Actualisation d'un client depuis Sirene (diff champ par champ), alerte de fermeture / cessation, siège social, forme juridique et activité NAF 2025 en clair (voir « Déjà fait »).

### Sprint 4 — Le rapport : en cours (médias faits, rapport et PDF du rapport à faire)
- App `reports` : interface desktop en écran partagé, avec à gauche le résumé des données et photos de la visite, à droite le formulaire de synthèse et de recommandations.
- ~~Gestion des médias~~ : fait (app `medias`) : images, PDF, Office et vidéos rattachés à un dossier, une visite ou une recommandation ; compression Pillow, miniatures, EXIF, tags, limites de taille par type, quota par dossier et stockage local.
- PDF : template HTML de rapport (logo, infos client), conversion du HTML et des données JSON en PDF téléchargeable.

### Sprint 5 — Finitions, sécurité et déploiement : à faire
- ~~Refonte des interfaces dashboard, dossiers, visites et recommandations.~~
- ~~Permissions : un inspecteur ne voit ni ne modifie les visites d'un autre.~~
- ~~Stockage externe des photos et PDF~~ : abandonné, les fichiers restent sur le disque du PC (volume Docker).
- RAG sur les documents d'un dossier (Gemini, pgvector, sans Celery ni Redis) : prévu après les médias.
- Déploiement local avec Docker sur un PC Windows (`Dockerfile`, `compose.yaml`, `scripts/`) : fait ; reste à le valider sur la machine cible (démarrage avec Windows, sauvegardes planifiées, test de restauration).
- Checklist de release de maintenance (`docs/riskflow-checklist-release.md`) : faite, liée depuis le README.
- ~~Export PDF du questionnaire de visite à emporter sur le terrain, puis re-saisie au retour.~~

## Reste à faire (to-do)

**Interface**
- [ ] Refonte du template dossier d'inspection
  - [ ] Onglet génération du rapport

**Déploiement** (à dérouler avec `docs/riskflow-checklist-release.md`, sections 1 à 4 et 5.8 pour la première installation)
- [ ] Vérification pre-release (section 1)
- [ ] Déploiement docker sur le PC cible, première release (sections 3 et 5.8)
- [ ] Test end-to-end complet (recette, sections 1.5 et 4.2)
- [ ] Test récupération BDD : sauvegarde puis restauration de bout en bout (sections 4.4 et 5.4)

## Leçons

- Le modèle client a changé en cours de route.
- Renommer une app et un modèle en même temps est une mauvaise idée : faire un changement à la fois, avec sa migration.
- Ne pas installer daisyUI sur ce projet ; exploiter pleinement les variables CSS de Tailwind.
- Intégrer le moins de JavaScript possible et utiliser au plus la librairie HTMX
- Créer une app `core` pour le code commun.
- Configurer les modes développement et production plus tôt.
- Mettre en place la CI/CD GitHub dès le début d'un projet.
