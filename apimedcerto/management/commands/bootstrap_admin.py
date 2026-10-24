import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create the configured initial superuser, if needed."

    def handle(self, *args, **options):
        username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip()
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")

        if not username and not email and not password:
            self.stdout.write("Admin bootstrap is not configured.")
            return

        if not username or not email:
            raise CommandError(
                "Set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_EMAIL."
            )

        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD
        user_manager = user_model._default_manager
        existing_user = user_manager.filter(**{username_field: username}).first()

        if existing_user:
            if existing_user.email.casefold() != email.casefold():
                raise CommandError(
                    "The configured username belongs to a different email address."
                )
            if not existing_user.is_superuser:
                existing_user.is_staff = True
                existing_user.is_superuser = True
                existing_user.save(update_fields=["is_staff", "is_superuser"])
                self.stdout.write("Configured user promoted to superuser.")
                return
            self.stdout.write("Configured superuser already exists.")
            return

        if not password:
            raise CommandError(
                "Set BOOTSTRAP_ADMIN_PASSWORD to create a new superuser."
            )

        user = user_model(**{username_field: username, "email": email})
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error

        with transaction.atomic():
            user_manager.create_superuser(
                **{
                    username_field: username,
                    "email": email,
                    "password": password,
                }
            )

        self.stdout.write("Configured superuser created.")
