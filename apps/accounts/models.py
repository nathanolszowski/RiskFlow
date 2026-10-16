from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    # Add any additional fields you want for ALL USERS
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username

class Inspector(models.Model):
    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='inspector_profile'
    )
    
    registration_number = models.CharField(max_length=50, unique=True, verbose_name="Card number")
    zone = models.CharField(max_length=100, blank=True, null=True, verbose_name="Inspection Zone")
    is_active = models.BooleanField(default=True, verbose_name="Activated")

    def __str__(self):
        return f"Inspecteur : {self.user.get_full_name() or self.user.username}"