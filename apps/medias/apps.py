from django.apps import AppConfig


class MediasConfig(AppConfig):
    """Configuration of the medias app; registers the signal removing deleted files."""

    name = "medias"

    def ready(self) -> None:
        """Register the signal that removes the files of a deleted media."""
        from . import signals  # noqa: F401
