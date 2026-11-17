"""Shared test tools of the project (base factory, HTMX client helpers).

Importing this package makes the generated data reproducible: the random generator
is reseeded and Faker produces French data, like the application.
"""

from factory import random
from factory.faker import Faker

random.reseed_random("riskflow")
Faker._DEFAULT_LOCALE = "fr_FR"
