from django.db import models
from django.conf import settings

class TrackingModel(models.Model):
    """
    Abstract base model that provides audit fields for tracking creation and modification of records.
    """
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière mise à jour")
    archived_at = models.DateTimeField(blank=True, null=True, verbose_name="Date d'archivage")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    # '%(class)s' will be replaced by the lowercased name of the child model that inherits from this abstract model.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_%(class)s_set',
        verbose_name="Créé par"
    )
    
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_%(class)s_set',
        verbose_name="Modifié en dernier par",
        blank=True,
        null=True
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='archived_%(class)s_set',
        verbose_name="Archivé par",
        blank=True,
        null=True
    )

    class Meta:
        abstract = True  # <--- Django will not create a database table for this model, but other models can inherit from it to get these fields.