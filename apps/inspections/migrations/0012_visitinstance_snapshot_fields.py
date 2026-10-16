from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inspections', '0011_migrate_inspectionfolder_phases'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitinstance',
            name='template_name',
            field=models.CharField(blank=True, max_length=255, verbose_name="Nom du template d'origine"),
        ),
        migrations.AddField(
            model_name='visitinstance',
            name='revision',
            field=models.PositiveIntegerField(default=0, verbose_name='Révision des réponses'),
        ),
        migrations.AddField(
            model_name='visitinstance',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Date de fin de la visite'),
        ),
    ]
