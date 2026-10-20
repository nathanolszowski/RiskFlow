"""Shared test tools of the project (base factory, HTMX client helpers).

Importing this package makes the generated data reproducible: the random generator
is reseeded and Faker produces French data, like the application.
"""

import factory
from factory import random

random.reseed_random("riskflow")
factory.Faker._DEFAULT_LOCALE = "fr_FR"
