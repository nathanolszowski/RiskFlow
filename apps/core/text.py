"""French wording helpers shared by the messages of the apps."""

from typing import Optional


def agree(n: int, singular: str, plural: Optional[str] = None) -> str:
    """Return the word agreeing with the quantity: singular for 0 or 1, plural above.

    Args:
        n: Quantity.
        singular: Singular form (``"sera supprimé"``).
        plural: Plural form, ``singular`` followed by ``s`` by default.

    Returns:
        The form matching ``n``.
    """
    return singular if n < 2 else plural or f"{singular}s"


def plural(n: int, singular: str, plural_form: Optional[str] = None) -> str:
    """Return ``'<n> <word>'`` with the word agreeing with ``n`` (``"3 visites"``).

    Args:
        n: Quantity.
        singular: Singular form of the word.
        plural_form: Plural form, ``singular`` followed by ``s`` by default.

    Returns:
        The quantity and the word.
    """
    return f"{n} {agree(n, singular, plural_form)}"
