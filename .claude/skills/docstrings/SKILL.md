---
name: docstrings
description: Écrit ou complète les docstrings Python au style de RiskFlow (anglais, Google, ruff pydocstyle). À utiliser quand on demande d'ajouter, corriger ou relire des docstrings, ou en écrivant du code/des tests qui en exigent (modules, classes, fonctions, vues, services, modèles, tests).
---

# Docstrings RiskFlow

Convention : **anglais**, **style Google** (`[tool.ruff.lint.pydocstyle] convention = "google"`), triple guillemets doubles `"""`. Le domaine et l'UI sont en français, mais les docstrings sont en anglais ; les termes métier français restent entre double accent grave (``Recommandation``) ou entre guillemets s'ils sont affichés (« Terminer la visite »).

## Règles générales

- Première ligne : une phrase **impérative ou descriptive au présent**, qui finit par un point, tient sur une ligne (88 colonnes). Pas de saut de ligne après `"""`.
  - Fonctions : verbe à l'impératif (`Return a visit, ensuring...`, `Split the text typed in...`, `Render the full page...`).
  - Tests : comportement attendu au présent (`Each call adds exactly one to the revision.`).
- Ligne vide, puis détails (le pourquoi, les invariants, les statuts HTTP, les pièges) seulement s'ils apportent quelque chose. Ne pas paraphraser le code ni les annotations de type.
- Les noms de code, champs, méthodes, paramètres GET sont entre doubles accents graves : ``instance_schema``, ``created_by``, ``certify_address``.
- Les types sont dans la signature, **pas** dans la docstring (`pk: Primary key of the visit.`, pas `pk (int)`).
- Docstring d'une ligne si tout tient : `"""Create the two users and log the owner in."""`.
- Obligatoire sur chaque module, classe et méthode de test (vérifié par `uv run ruff check --select D1 apps/*/tests`) ; partout ailleurs, sur tout ce qui est public ou non trivial. Pas besoin sur `__str__`, `Meta` ou les `@property` triviales.
- Ne pas commenter les migrations (exclues de ruff).

## Modules

Une phrase qui dit ce que contient le module, éventuellement suivie d'un paragraphe d'invariant :

```python
"""Tags of the medias: parsing, normalization and assignment.

Tags belong to the user (``created_by``) and are unique per user whatever their case.
"""
```

Modules de tests : `"""Tests for the visit services (inspections/services/visit.py)."""`. Services : `"""Services of the visits: creation, ..."""`. Vues : `"""Views of the visit form: filling on the field, ..."""`.

## Fonctions et méthodes

Sections Google, dans cet ordre, séparées par une ligne vide, **uniquement** celles qui s'appliquent :

```python
def get_visit_by_id(pk: int, user: "CustomUser") -> VisitInstance:
    """Return a visit, ensuring that its folder was created by the user.

    Args:
        pk: Primary key of the visit.
        user: Logged-in user, who must own the folder.

    Returns:
        The visit, with its folder, template and tracking users.

    Raises:
        Http404: If the visit does not exist or its folder belongs to another user.
    """
```

- `Args:` un paramètre par ligne `nom: Description.` (majuscule, point final). Continuation indentée de 4 espaces. Omettre `self`/`cls`. Pour une vue, `request:` précise les paramètres GET/POST lus (``section`` GET parameter...) et `pk:` donne la clé primaire.
- `Returns:` décrit la valeur (pas son type). Pour une vue : ce qui est rendu et les en-têtes HTMX (`HX-Trigger`, `HX-Refresh`).
- `Raises:` `Exception: If ...` pour les exceptions levées **par la fonction ou volontairement propagées** (`Http404`, `ValidationError`, `VisitLockedError`, `AnswersValidationError`). Pour les vues, mentionner les statuts renvoyés (200, 204, 401, 404, 409, 422) dans le corps.
- Pas de section pour ce qui est évident (une fonction sans argument, un `Returns` qui répéterait la première ligne).
- `@property` : une seule ligne `Return ...` ; détail en paragraphe si le format n'est pas évident (``label (code)``).

## Classes

Première ligne = ce que la classe représente. Pour les modèles/mixins/helpers avec des champs ou attributs utiles, ajouter une section `Attributes:` (même format que `Args:`) :

```python
class HtmxClientMixin:
    """Add two users, a logged-in client and HTMX request shortcuts to a test case.

    Put it before ``TestCase`` in the bases. ``setUp`` creates ``owner`` (logged in
    with ``force_login``) and ``other`` (not logged in).

    Attributes:
        owner: User who owns the objects the test creates, logged in on ``client``.
        other: Second user, who must never reach the objects of ``owner``.
    """
```

- Exceptions : décrire la situation (`"""The visit cannot be changed any more (done or archived).` + ligne sur la réponse des vues).
- Classes internes `TextChoices` : une ligne (`"""Origin of the address."""`).
- Les constantes de module se documentent par une docstring de chaîne **sous** l'affectation quand le nom ne suffit pas (`Route = namedtuple(...)` puis `"""A URL under test: ..."""`).

## Tests

Chaque module, classe `TestCase` et méthode de test a une docstring.

- Classe : le sujet testé en première ligne, puis `Data:` si les fixtures de `setUpTestData` ne sont pas évidentes :
  ```python
  class CreateVisitTests(TestCase):
      """``create_visit`` with a folder and a template of the same owner.

      Data: ``folder`` and ``template`` share ``user`` as owner.
      """
  ```
- `setUp`/`setUpTestData` : `"""Create the folder and a private template of the same user."""`.
- Méthode `test_*` : **une ligne** qui énonce le comportement attendu au présent, sujet en tête, lisible avec `-v 2` : `"""The user who saved the answers becomes ``updated_by``."""`. Éviter « Test that... » et « Tests ». Ajouter un second paragraphe seulement pour un cas subtil (ordre PostgreSQL, `on_commit`, régression).
- Ne jamais adapter un test pour qu'il passe : un bug révélé = commit `fix/<app>:` séparé.

## Séparateurs de sections (vues)

Les fichiers de vues peuvent grouper avec des bandeaux de commentaires, pas des docstrings :

```python
# ==========================================
# ==== VISIT FORM (FILLING ON THE FIELD) ===
# ==========================================
```

## Méthode de travail

1. Lire le code à documenter (et son appelant si le contrat HTTP/HTMX compte) : documenter ce qu'il fait réellement, pas ce qu'on suppose. Le code fait foi sur la doc `docs/`.
2. Imiter le fichier voisin (densité, vocabulaire) ; réutiliser les termes de `CLAUDE.md` (dossier = ``InspectionFolder``, « Client » = ``Company``, snapshot, cloisonnement...).
3. Ne modifier que les docstrings : aucun changement de logique, d'imports ni de formatage ailleurs.
4. Vérifier :
   ```bash
   uv run ruff check apps config
   uv run ruff format --check apps config
   uv run ruff check --select D1 apps/*/tests
   ```
   Pour contrôler le style Google sur un fichier : `uv run ruff check --select D --ignore D100,D104,D105,D107 <fichier>` (la convention vient de `pyproject.toml`).
