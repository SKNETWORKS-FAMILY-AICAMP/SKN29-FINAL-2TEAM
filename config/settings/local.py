from .base import *  # noqa: F403

DEBUG = True

if env.bool("USE_SQLITE", default=False):  # noqa: F405
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }
else:
    DATABASES = {
        "default": env.db(  # noqa: F405
            "DATABASE_URL",
            default="postgres://project_copilot:project_copilot@127.0.0.1:5432/project_copilot",
        )
    }
