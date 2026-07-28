#!/usr/bin/env python
import os
import sys


def main() -> None:
    """Django 관리 명령 진입점."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
