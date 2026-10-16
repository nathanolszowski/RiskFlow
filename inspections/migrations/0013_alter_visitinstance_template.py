import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inspections', '0012_visitinstance_snapshot_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='visitinstance',
            name='template',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='instances',
                to='inspections.visittemplate',
                verbose_name="Template d'origine",
            ),
        ),
    ]
