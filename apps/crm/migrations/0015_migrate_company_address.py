import re

from django.db import migrations

# "10 RUE DE LA PAIX, 75002 PARIS" -> street, postal code, city
ADDRESS_RE = re.compile(
    r"^(?P<line>.*?)[,\s]+(?P<postal_code>\d{5})\s+(?P<city>[^,\n]+)$", re.DOTALL
)


def split_address(text):
    """Split a free-text address into (address_line, postal_code, city)."""
    text = (text or "").strip()
    match = ADDRESS_RE.match(text)
    if match:
        return (
            match["line"].strip(" ,\n")[:255],
            match["postal_code"],
            match["city"].strip()[:100],
        )
    return text.replace("\n", ", ")[:255], "", ""


def copy_address(apps, schema_editor):
    """Copy the free-text ``address`` into the structured fields."""
    Company = apps.get_model("crm", "Company")
    for company in Company.objects.exclude(address=""):
        line, postal_code, city = split_address(company.address)
        company.address_line = line
        company.postal_code = postal_code
        company.city = city
        company.save(update_fields=["address_line", "postal_code", "city"])


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0014_address_mixin"),
    ]

    operations = [
        migrations.RunPython(copy_address, migrations.RunPython.noop),
    ]
