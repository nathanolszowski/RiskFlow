"""Admin of the medias app: metadata of the medias (the files themselves are not editable)."""

from django.contrib import admin

from .models import Media, MediaTag


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    """Admin of ``Media``."""

    list_display = (
        "original_name",
        "media_type",
        "folder",
        "size",
        "is_active",
        "created_at",
    )
    list_filter = ("media_type", "is_active")
    # File and thumbnail are not editable here: their widget links to .url, which is not exposed
    exclude = ("file", "thumbnail")
    search_fields = ("original_name", "title", "folder__reference")


@admin.register(MediaTag)
class MediaTagAdmin(admin.ModelAdmin):
    """Admin of ``MediaTag``."""

    list_display = ("name", "created_by", "created_at")
    search_fields = ("name",)
