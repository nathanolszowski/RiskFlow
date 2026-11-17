"""Admin of the inspections app: folders, templates, visits and recommendations."""

from django.contrib import admin
from django.db import models
from django.forms import ModelForm
from django.http import HttpRequest
from django_json_widget.widgets import JSONEditorWidget

from .models import InspectionFolder, Recommandation, VisitInstance, VisitTemplate


@admin.register(InspectionFolder)
class InspectionFolderAdmin(admin.ModelAdmin):
    """Admin of ``InspectionFolder``."""

    list_display = (
        "reference",
        "company",
        "current_phase",
        "is_active",
        "created_by",
        "updated_at",
    )
    list_filter = ("current_phase", "is_active", "created_at")
    search_fields = ("reference", "company__name")
    readonly_fields = (
        "created_at",
        "updated_by",
        "updated_at",
        "archived_at",
        "archived_by",
    )

    def save_model(
        self, request: HttpRequest, obj: InspectionFolder, form: ModelForm, change: bool
    ) -> None:
        """Set ``created_by`` when empty and ``updated_by`` to the current user.

        Args:
            request: Current request.
            obj: Object being saved.
            form: Admin form used to edit the object.
            change: True when an existing object is modified, False on creation.
        """
        if not change or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(VisitTemplate)
class VisitTemplateAdmin(admin.ModelAdmin):
    """Admin of ``VisitTemplate``, with a JSON editor for the schema."""

    list_display = ("name", "is_active", "created_at", "created_by")
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)

    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget},
    }

    def save_model(
        self, request: HttpRequest, obj: VisitTemplate, form: ModelForm, change: bool
    ) -> None:
        """Set ``created_by`` when empty and ``updated_by`` to the current user.

        Args:
            request: Current request.
            obj: Object being saved.
            form: Admin form used to edit the object.
            change: True when an existing object is modified, False on creation.
        """
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(VisitInstance)
class VisitInstanceAdmin(admin.ModelAdmin):
    """Admin of ``VisitInstance``.

    The template snapshot and the revision are read-only: only the services write them.
    """

    list_display = (
        "id",
        "folder",
        "template",
        "current_status",
        "is_active",
        "created_by",
    )
    list_filter = ("current_status", "is_active", "due_date")
    search_fields = ("folder__reference", "template__name", "template_name")
    # The snapshot of the template and the revision are only written by the services
    readonly_fields = (
        "created_at",
        "updated_by",
        "updated_at",
        "archived_at",
        "archived_by",
        "template_name",
        "instance_schema",
        "revision",
    )

    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget},
    }

    def save_model(
        self, request: HttpRequest, obj: VisitInstance, form: ModelForm, change: bool
    ) -> None:
        """Set ``created_by`` when empty and ``updated_by`` to the current user.

        Args:
            request: Current request.
            obj: Object being saved.
            form: Admin form used to edit the object.
            change: True when an existing object is modified, False on creation.
        """
        # Correctly set the created_by and updated_by fields based on whether the object is being created or updated
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Recommandation)
class RecommandationAdmin(admin.ModelAdmin):
    """Admin of ``Recommandation``."""

    list_display = ("id", "folder", "current_status", "is_active", "created_by")
    list_filter = ("is_active", "priority", "current_status", "created_at", "folder")
    search_fields = ("description", "folder__name", "folder__reference")
    readonly_fields = (
        "created_at",
        "updated_by",
        "updated_at",
        "archived_at",
        "archived_by",
    )

    def save_model(
        self, request: HttpRequest, obj: Recommandation, form: ModelForm, change: bool
    ) -> None:
        """Set ``created_by`` when empty and ``updated_by`` to the current user.

        Args:
            request: Current request.
            obj: Object being saved.
            form: Admin form used to edit the object.
            change: True when an existing object is modified, False on creation.
        """
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
