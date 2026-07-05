from django.db import models
from django.conf import settings
from config.models import TrackingModel

class Clients(TrackingModel):
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence Client")
    name = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    address = models.TextField(verbose_name="Adresse")
    siret = models.CharField(max_length=14, unique=True, verbose_name="Numéro SIRET")
    business_line = models.CharField(max_length=100, verbose_name="Secteur d'activité")

    class Meta(TrackingModel.Meta):
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ['name']

    def __str__(self):
        return f"{self.name}"
