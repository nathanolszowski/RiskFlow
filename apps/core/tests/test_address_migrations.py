"""Tests of the data migrations that split the old free-text addresses."""

from importlib import import_module

from django.test import SimpleTestCase

MIGRATIONS = (
    "crm.migrations.0015_migrate_company_address",
    "inspections.migrations.0018_migrate_folder_site_address",
)


class SplitAddressTests(SimpleTestCase):
    """``split_address`` cuts « street, postal code city » and never loses text."""

    def split(self, module, text):
        """Run the splitter of a migration.

        Args:
            module: Dotted path of the migration module.
            text: Old free-text address.

        Returns:
            ``(address_line, postal_code, city)``.
        """
        return import_module(module).split_address(text)

    def test_sirene_format_is_split(self):
        """The format written by the Sirene import is split into its three parts."""
        for module in MIGRATIONS:
            with self.subTest(module=module):
                self.assertEqual(
                    self.split(module, "10 RUE DE LA PAIX, 75002 PARIS"),
                    ("10 RUE DE LA PAIX", "75002", "PARIS"),
                )

    def test_multiline_address_is_split(self):
        """A typed address on several lines still finds the postal code and city."""
        for module in MIGRATIONS:
            with self.subTest(module=module):
                self.assertEqual(
                    self.split(module, "Bâtiment B\n5 av Jean Jaurès\n69007 Lyon"),
                    ("Bâtiment B\n5 av Jean Jaurès", "69007", "Lyon"),
                )

    def test_address_without_postal_code_stays_in_the_street(self):
        """An address that does not match is kept whole in ``address_line``."""
        for module in MIGRATIONS:
            with self.subTest(module=module):
                self.assertEqual(
                    self.split(module, "Zone industrielle Nord"),
                    ("Zone industrielle Nord", "", ""),
                )

    def test_long_text_is_truncated_to_the_column(self):
        """The street never exceeds the 255 characters of the column."""
        for module in MIGRATIONS:
            with self.subTest(module=module):
                line, _, _ = self.split(module, "x" * 400)
                self.assertEqual(len(line), 255)

    def test_empty_address_gives_empty_parts(self):
        """No address gives empty parts."""
        for module in MIGRATIONS:
            with self.subTest(module=module):
                self.assertEqual(self.split(module, ""), ("", "", ""))
