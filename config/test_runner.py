"""Test runner that discovers the tests of ``apps/`` when no label is given."""

from pathlib import Path

from django.test.runner import DiscoverRunner

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"


class AppsDiscoverRunner(DiscoverRunner):
    """``DiscoverRunner`` whose default target is ``apps/``.

    ``apps/`` is not a package (the apps keep their top-level import names), so the
    standard discovery from the project root would find nothing.
    """

    def build_suite(self, test_labels=None, **kwargs):
        """Build the suite, testing the whole ``apps/`` folder without labels.

        Args:
            test_labels: Labels given on the command line, if any.
            **kwargs: Other arguments passed to ``DiscoverRunner.build_suite``.

        Returns:
            The test suite.
        """
        if not test_labels:
            test_labels = [str(APPS_DIR)]
        return super().build_suite(test_labels, **kwargs)
