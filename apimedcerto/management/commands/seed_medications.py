from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apimedcerto.medication_import import MedicationImportError, import_medications


class Command(BaseCommand):
    help = "Import the public medication catalog bundled with the project."

    def handle(self, *args, **options):
        catalog_path = settings.BASE_DIR / "data" / "medications.xlsx"
        if not catalog_path.is_file():
            raise CommandError(f"Medication catalog not found: {catalog_path}")

        try:
            with catalog_path.open("rb") as catalog_file:
                result = import_medications(catalog_file)
        except OSError as error:
            raise CommandError(
                f"Unable to read medication catalog: {catalog_path}"
            ) from error
        except MedicationImportError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Medication catalog ready: {result['created']} added, "
                f"{result['already_existing']} already present, "
                f"{result['unique_products']} unique products."
            )
        )
