from django.contrib import admin
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from .models import VisitTemplate, InspectionFolder, VisitInstance

@admin.register(VisitTemplate)
class VisitTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'created_by')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }

    # Optionally, you can override the save_model method to automatically set the created_by and updated_by fields based on the current user.
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class VisitInstanceInline(admin.TabularInline):
    """
    Can be used to display VisitInstance objects inline within the InspectionFolder admin view.
    """
    model = VisitInstance
    extra = 0
    readonly_fields = ('created_by', 'created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')
    # Exclude the 'data' field from the inline form to prevent it from being displayed or edited in the admin interface.
    exclude = ('data',) 


@admin.register(InspectionFolder)
class InspectionFolderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'client', 'current_phase', 'is_active', 'created_by', 'updated_at')
    list_filter = ('current_phase', 'is_active', 'created_at')
    search_fields = ('reference', 'client__name') # 'client__name' authorizes searching by the name of the related client
    readonly_fields = ('created_by', 'created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')
    
    inlines = [VisitInstanceInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """
        This method is called when saving the inline formsets (like VisitInstanceInline) associated with the InspectionFolder.
        It ensures that the created_by and updated_by fields of VisitInstance are set correctly based on the current user.
        """
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, VisitInstance):
                if not instance.pk: # new visit
                    instance.created_by = request.user
                else: # if it's an existing visit being updated
                    instance.updated_by = request.user
                instance.save()
        formset.save_m2m()


@admin.register(VisitInstance)
class VisitInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'folder', 'template', 'current_status', 'is_active')
    list_filter = ('current_status', 'is_active')
    search_fields = ('folder__reference', 'template__name')
    readonly_fields = ('created_by', 'created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)
