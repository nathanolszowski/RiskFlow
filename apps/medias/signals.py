"""Remove the stored files when a media row is deleted.

``Model.delete()`` and database cascades (folder, visit or recommendation deleted)
only remove the row, so the files would stay in the storage.
"""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Media


@receiver(post_delete, sender=Media)
def delete_media_files(sender: type[Media], instance: Media, **kwargs: object) -> None:
    """Delete the file and the thumbnail once the deletion is committed.

    Args:
        sender: Model class that sent the signal.
        instance: Media that was deleted.
        **kwargs: Other signal arguments, unused.
    """
    files = [f for f in (instance.file, instance.thumbnail) if f]

    def _delete() -> None:
        """Remove the files from the storage."""
        for f in files:
            f.storage.delete(f.name)

    transaction.on_commit(_delete)
