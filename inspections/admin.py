from django.contrib import admin
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from .models import VisitTemplate, InspectionFolder, VisitInstance, Recommandation

@admin.register(InspectionFolder)
class InspectionFolderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'client', 'current_phase', 'is_active', 'created_by', 'updated_at')
    list_filter = ('current_phase', 'is_active', 'created_at')
    search_fields = ('reference', 'client__name')
    readonly_fields = ('created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')
    
    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by:
            obj.created_by = request.user
        
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(VisitTemplate)
class VisitTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'created_by')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }

    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(VisitInstance)
class VisitInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'folder', 'template', 'current_status', 'is_active', 'created_by')
    list_filter = ('current_status', 'is_active', 'due_date')
    search_fields = ('folder__reference', 'template__name')
    readonly_fields = ('created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')

    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }

    def save_model(self, request, obj, form, change):
        # 🎯 Correction de l'indentation et vérification de la présence de created_by
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Recommandation)
class RecommandationAdmin(admin.ModelAdmin):
    list_display = ('id', 'folder', 'current_status', 'is_active', 'created_by')
    list_filter = ('is_active', 'priority', 'current_status', 'created_at', 'folder')
    search_fields = ('description', 'folder__name', 'folder__reference')
    readonly_fields = ('created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')

    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)