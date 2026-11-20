# RiskFlow — Produit : fonctionnalités et écrans

Dernière modification : 17/11/2026 à 11:04 par Nathan

## Fonctionnalités

### Priorité 1 — Essentielles (MVP)

1. **Utilisateurs et authentification** : comptes inspecteurs et administrateurs, login/logout sécurisé.
2. **Dossiers d'inspection** : ajouter des dossiers et suivre leur traitement.
3. **Visites**
   - Créer des modèles de visite pour préparer les visites d'un dossier.
   - Initier une « instance de visite » à partir d'un modèle.
   - Temps de transport jusque chez le client. [Avancé en P1]
4. **Tableau de bord** : visites en cours et terminées, avec un statut simple (planifié, en cours, terminé, à revoir).
5. **CRM** : gestion et suivi des clients assurés et des contacts.
6. **Recommandations de prévention** : recommandations structurées (obligatoires ou suggérées) avec description, priorité et date de mise en œuvre.
7. **Suivi des recommandations** : état de chaque recommandation (en attente de mise en œuvre, validée, rejetée).
8. **Documents** : attacher des images, PDF, Excel, Word, PowerPoint et vidéos, avec tags libres, filtres, limites de taille par type et quota par dossier; les photos gardent leur date et leur position GPS (lien vers la carte). [Avancé en P1]

### Priorité 2 — Avancées

1. **Rapport de visite** : générer un rapport pré-formaté qui consolide les données saisies (description de l'activité et du site, observations clés). [Reporté en P2]
2. **RAG Documents** : interrogation des documents (RAG).
3. **Modèles de rapport personnalisables** : gabarits avec champs calculés, sections conditionnelles, intégration dynamique des données.
4. **Notifications** (WebSockets ou email) : pour les inspecteurs (visites assignées, rappels) et les administrateurs (rapports finalisés, problèmes critiques).
5. **Capture structurée pendant la visite** : observations et résultats de vérification saisis dans les champs prévus et stockés de manière structurée.

### Priorité 3 — Bonus

1. **Workflows adaptatifs** : règles simples qui font varier le parcours selon les réponses.
2. **Tableau de bord analytique** : taux de conformité des recommandations, répartition des types de risques, temps moyen par étape, goulots d'étranglement, filtrage et drill-down.
3. **Estimation SMM/SMP** : formulaires ou calculs pour évaluer l'impact financier des scénarios de sinistre.
4. **Portail client sécurisé** : consultation des rapports, suivi des recommandations, dépôt de justificatifs, suivi des consultations.
5. **Intégrations externes** (API REST, webhooks) vers un CRM ou un système de gestion de contrats.
6. Google Analytics.
7. **Base de connaissances** : articles (réglementations, normes incendie, guides intrusion) en CRUD, liés aux étapes d'un modèle de visite, avec recherche textuelle.
8. **Notifications** : notifications de workflow intégrés dans l'application

## Écrans

### Layout de l'application
- Barre de recherche globale dans le menu horizontal.
- Footer.

### Dashboard
Contenu : nombre de dossiers en cours, vue graphique des statuts de dossier (par mois et par année), dernier dossier modifié, prochaines visites de la semaine.

Disposition retenue dans les notes :
- B1 : bandeau de bienvenue
- B2 : dernier dossier modifié (1/3) et prochaines visites (2/3)
- B3 : filtre mois/année
- B4 : nombre de dossiers en cours (1/4) et vue d'ensemble graphique (3/4)

### Liste des dossiers
Actions par dossier : modifier, archiver puis supprimer, dupliquer. Présentation en cartes, avec tri. L'archivage et la suppression se font depuis la fiche du dossier (voir « Archivage et suppression »).

### Détail d'un dossier
Actions : modifier, archiver puis supprimer, dupliquer. Barre de progression selon ce qui est rempli.

Contenu :
- résumé des informations client
- contact du dossier
- adresse du lieu
- phase du dossier
- score actuel
- secteur d'activité et activités exercées
- carte du lieu et risques en données ouvertes
- historique des sinistres
- étude des documents (plans, rapports de conformité : électricité, sprinkler, etc.)
- notes

Onglets : vue d'ensemble, visites, recommandations, médias (grille de miniatures, filtres type / rattachement / tag, barre de quota, ajout multiple, pop-up en cas de fichier refusé), génération du rapport (prévu).

### Visites

**Modèles de visite**
- créer un modèle, dupliquer un modèle, lister les modèles
- archiver ou supprimer un modèle, seulement si l'on en est le créateur et qu'aucune instance de visite n'y est liée

**Visites**
- préparer une nouvelle visite
- lister les visites existantes : date, statut, actif, début et fin, client, adresse, contact, modèle utilisé
- ouvrir le formulaire de visite : remplir les champs, ajouter des questions et des remarques (l'instance de visite importe donc le schéma du modèle et peut l'ajuster)
- archiver puis supprimer
- parcours de création en fil d'Ariane : informations de visite (contact, etc.) > choix du modèle > ajustements

### Recommandations
Liste : date de création, échéance, priorité, statut, sujet, description dépliable.

Tris : priorité, statut, échéance, sujet, actif/archivé, date de création.

## Clients (CRM)

- Liste des clients : recherche, filtre actif / archivé, tri (nom, date, nombre de dossiers), pagination. Chaque carte affiche le nom, la référence, et sous la référence l'état de l'établissement selon Sirene : « Établissement en activité » (vert), « Établissement fermé » ou « Entreprise cessée » (rouge), « Établissement non vérifié ».
- Création (`clients/nouveau-client/`) : saisie d'un SIRET (14 chiffres) qui pré-remplit le formulaire depuis l'API Sirene, avec forme juridique en clair, activité principale NAF 2025 (libellé), siège social (adresse et état) et une alerte rouge si l'établissement est fermé ou l'entreprise cessée. La création reste possible. La référence est générée, jamais saisie.
- Fiche client : informations, bandeau d'alerte (établissement fermé depuis le … / entreprise cessée, avec l'état du siège), forme juridique, activité NAF 2025, siège social (avec lien vers sa fiche si c'est un autre client), contacts liés et dossiers d'inspection liés (ceux de l'utilisateur, archivés compris).
- « Actualiser (Sirene) » : une modale compare la fiche aux données actuelles de l'API et propose, ligne par ligne et cochée par défaut, les champs différents (nom, adresse, forme juridique, taille, activité, NAF 2025, siège, état administratif). L'utilisateur applique ce qu'il accepte ; rien d'autre n'est modifié (site web, labels, conseil d'administration, effectifs, contacts). Si Sirene signale une fermeture, la modale l'indique. Un client archivé ne peut pas être actualisé.

## Archivage et suppression

Règles communes aux dossiers, clients, contacts, visites et recommandations :
- Archiver est réversible (désarchiver) ; supprimer est définitif et n'est possible que sur un objet déjà archivé.
- Une popup précède l'archivage d'un dossier, d'un client et d'un contact, et la suppression de chaque objet. Archiver ou désarchiver une visite ou une recommandation demande une simple confirmation du navigateur.
- Permissions : dossiers, visites et recommandations sont réservés au propriétaire du dossier. Clients et contacts sont **partagés** entre tous les utilisateurs connectés, qui peuvent tous les modifier, les archiver ou les supprimer (liste, fiche, recherche, utilisation dans un dossier) ; les pages client n'affichent que les dossiers de l'utilisateur.

Cascades et blocages :
- Archiver un dossier archive ses visites et recommandations, pas le client ni le contact. Le désarchiver ne réactive que ce qui a été archivé avec lui.
- Archiver un client archive ses contacts actifs, sauf ceux référencés par un dossier actif. Le désarchiver laisse les contacts archivés.
- Archiver un contact est refusé tant qu'un dossier actif le référence : il faut d'abord changer le contact référent.
- Supprimer un dossier supprime ses visites et recommandations.
- Supprimer un client supprime ses contacts, mais est refusé tant qu'il a des dossiers (même archivés).
- Supprimer un contact est refusé tant qu'un dossier (même archivé) le référence.

Les fiches dossier, client et contact affichent « Archivé le … par … » dans le bandeau de traçabilité tant que l'objet est archivé.

## Design

Palette complète attendue : couleurs primaire, secondaire, d'accent, de fond, de surface et sémantiques. Thème géré par les variables CSS de Tailwind. Gros boutons adaptés à l'usage terrain.
