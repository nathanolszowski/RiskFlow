"""Template filters of the medias app."""

from django import template

register = template.Library()


@register.filter
def filesize_fr(value: int) -> str:
    """Format a size in bytes with French units (o, Ko, Mo, Go).

    Args:
        value: Size in bytes.

    Returns:
        The formatted size, e.g. ``"1,5 Mo"``, or an empty string if ``value`` is not a number.
    """
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("o", "Ko", "Mo"):
        if size < 1024:
            if unit == "o":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size:.1f} Go".replace(".", ",")
