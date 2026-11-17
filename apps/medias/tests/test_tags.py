"""Tests for the media tags (medias/services/tags.py)."""

from accounts.tests.factories import UserFactory
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from inspections.tests.factories import InspectionFolderFactory

from medias.models import MediaTag
from medias.services.tags import (
    MAX_TAG_LENGTH,
    get_folder_tags,
    get_user_tags,
    normalize_tag_names,
    parse_tag_names,
    set_media_tags,
)
from medias.tests.factories import MediaFactory, MediaTagFactory
from medias.tests.helpers import TempMediaRootMixin


class ParseAndNormalizeTests(SimpleTestCase):
    """``parse_tag_names`` and ``normalize_tag_names`` (no database)."""

    def test_parse_splits_on_commas_and_semicolons(self):
        """Commas and semicolons separate the names, spaces are collapsed."""
        self.assertEqual(
            parse_tag_names(" toiture ,  gros   oeuvre;feu "),
            ["toiture", "gros oeuvre", "feu"],
        )

    def test_parse_drops_empty_names(self):
        """Empty items and blank text give nothing."""
        self.assertEqual(parse_tag_names(",, ; ,"), [])
        self.assertEqual(parse_tag_names(""), [])

    def test_normalize_removes_case_insensitive_duplicates(self):
        """The first spelling of a duplicate is kept, the order is preserved."""
        self.assertEqual(
            normalize_tag_names(["Toiture", "feu", "TOITURE", "Feu"]),
            ["Toiture", "feu"],
        )

    def test_normalize_length_limit(self):
        """A name of 50 characters is accepted, 51 is refused."""
        normalize_tag_names(["a" * MAX_TAG_LENGTH])
        with self.assertRaisesMessage(ValidationError, "50 caractères"):
            normalize_tag_names(["a" * (MAX_TAG_LENGTH + 1)])

    def test_normalize_count_limit(self):
        """Ten distinct tags are accepted, eleven are refused."""
        normalize_tag_names([f"t{i}" for i in range(10)])
        with self.assertRaisesMessage(ValidationError, "plus de 10 tags"):
            normalize_tag_names([f"t{i}" for i in range(11)])

    def test_duplicates_do_not_count_toward_the_limit(self):
        """Eleven spellings of ten tags are fine."""
        names = [f"t{i}" for i in range(10)] + ["T0"]
        self.assertEqual(len(normalize_tag_names(names)), 10)


class SetMediaTagsTests(TempMediaRootMixin, TestCase):
    """``set_media_tags``: creation on the fly, reuse and replacement."""

    def setUp(self):
        """Create a media and its owner."""
        self.media = MediaFactory()
        self.user = self.media.created_by

    def names(self):
        """Return the sorted tag names of the media.

        Returns:
            A list of names.
        """
        return sorted(self.media.tags.values_list("name", flat=True))

    def test_tags_are_created_on_the_fly(self):
        """Unknown names create tags owned by the user."""
        set_media_tags(self.media, self.user, ["Toiture", "Feu"])
        self.assertEqual(self.names(), ["Feu", "Toiture"])
        tag = MediaTag.objects.get(name="Toiture")
        self.assertEqual((tag.created_by, tag.updated_by), (self.user, self.user))

    def test_existing_tag_is_reused_whatever_its_case(self):
        """``toiture`` reuses ``Toiture`` instead of creating a second tag."""
        existing = MediaTagFactory(created_by=self.user, name="Toiture")
        set_media_tags(self.media, self.user, ["toiture"])
        self.assertEqual(list(self.media.tags.all()), [existing])
        self.assertEqual(MediaTag.objects.count(), 1)

    def test_tags_of_another_user_are_never_reused(self):
        """Another user's tag with the same name is left alone, a new one is created."""
        foreign = MediaTagFactory(name="Toiture")
        set_media_tags(self.media, self.user, ["Toiture"])
        mine = self.media.tags.get()
        self.assertNotEqual(mine.pk, foreign.pk)
        self.assertEqual(mine.created_by, self.user)

    def test_set_replaces_the_whole_set(self):
        """The previous tags are replaced, not completed."""
        set_media_tags(self.media, self.user, ["a", "b"])
        set_media_tags(self.media, self.user, ["b", "c"])
        self.assertEqual(self.names(), ["b", "c"])
        set_media_tags(self.media, self.user, [])
        self.assertEqual(self.names(), [])

    def test_more_than_ten_tags_are_refused_and_nothing_changes(self):
        """Eleven tags raise ValidationError and the media keeps its tags."""
        set_media_tags(self.media, self.user, ["keep"])
        with self.assertRaises(ValidationError):
            set_media_tags(self.media, self.user, [f"t{i}" for i in range(11)])
        self.assertEqual(self.names(), ["keep"])

    def test_unique_constraint_is_case_insensitive_per_user(self):
        """The database refuses two tags differing by case for one user."""
        MediaTagFactory(created_by=self.user, name="Feu")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MediaTagFactory(created_by=self.user, name="FEU")
        MediaTagFactory(name="FEU")  # another user: fine


class TagQueriesTests(TempMediaRootMixin, TestCase):
    """``get_user_tags`` and ``get_folder_tags``."""

    def setUp(self):
        """Create two folders of one user with tagged medias, plus an unused tag."""
        self.user = UserFactory()
        self.folder = InspectionFolderFactory(created_by=self.user)
        self.other_folder = InspectionFolderFactory(created_by=self.user)
        self.in_folder = MediaTagFactory(created_by=self.user, name="Dans dossier")
        self.elsewhere = MediaTagFactory(created_by=self.user, name="Ailleurs")
        self.unused = MediaTagFactory(created_by=self.user, name="Inutilisé")
        MediaFactory(folder=self.folder, created_by=self.user).tags.add(self.in_folder)
        MediaFactory(folder=self.other_folder, created_by=self.user).tags.add(
            self.elsewhere, self.in_folder
        )

    def test_user_tags_are_the_used_ones(self):
        """Tags not attached to any media are not offered, each appears once."""
        self.assertEqual(
            list(get_user_tags(self.user)), [self.elsewhere, self.in_folder]
        )

    def test_user_tags_exclude_other_users(self):
        """The tags of other users never appear."""
        MediaFactory().tags.add(MediaTagFactory(name="Étranger"))
        self.assertNotIn("Étranger", [t.name for t in get_user_tags(self.user)])

    def test_folder_tags(self):
        """Only the tags of the medias of this folder are returned."""
        self.assertEqual(
            list(get_folder_tags(self.folder, self.user)), [self.in_folder]
        )
        self.assertEqual(
            list(get_folder_tags(self.other_folder, self.user)),
            [self.elsewhere, self.in_folder],
        )
