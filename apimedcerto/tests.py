import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.authtoken.models import Token
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APIClient

from apimedcerto.models import Medication, VerificationChallenge


class ApiDocumentationTests(TestCase):
    def test_schema_and_swagger_ui_are_available(self):
        schema_response = APIClient().get("/api/schema/?format=json")
        docs_response = APIClient().get("/api/docs/")

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_response.status_code, status.HTTP_200_OK)
        self.assertIn("/api/medications/", schema_response.data["paths"])
        self.assertIn(
            "/api/users/password/change/code/",
            schema_response.data["paths"],
        )
        medication_parameters = schema_response.data["paths"]["/api/medications/"]["get"]["parameters"]
        self.assertIn(
            "name",
            [parameter["name"] for parameter in medication_parameters],
        )

    def test_configured_frontend_origin_can_access_api(self):
        response = APIClient().get(
            "/api/schema/?format=json",
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Access-Control-Allow-Origin"],
            "http://localhost:5173",
        )


class BootstrapAdminCommandTests(TestCase):
    def test_bootstrap_is_disabled_without_environment_variables(self):
        with patch.dict(os.environ, {}, clear=True):
            call_command("bootstrap_admin")

        self.assertFalse(get_user_model().objects.exists())

    def test_creates_superuser_from_environment_variables(self):
        bootstrap_environment = {
            "BOOTSTRAP_ADMIN_USERNAME": "initial-admin",
            "BOOTSTRAP_ADMIN_EMAIL": "initial-admin@example.com",
            "BOOTSTRAP_ADMIN_PASSWORD": "SecureAdmin-726!Tiger",
        }
        with patch.dict(os.environ, bootstrap_environment, clear=True):
            call_command("bootstrap_admin")

        user = get_user_model().objects.get(username="initial-admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("SecureAdmin-726!Tiger"))

    def test_does_not_replace_existing_superuser_password(self):
        user = get_user_model().objects.create_superuser(
            username="initial-admin",
            email="initial-admin@example.com",
            password="ExistingAdmin-936!Tiger",
        )
        bootstrap_environment = {
            "BOOTSTRAP_ADMIN_USERNAME": "initial-admin",
            "BOOTSTRAP_ADMIN_EMAIL": "initial-admin@example.com",
        }

        with patch.dict(os.environ, bootstrap_environment, clear=True):
            call_command("bootstrap_admin")

        user.refresh_from_db()
        self.assertTrue(user.check_password("ExistingAdmin-936!Tiger"))
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_promotes_existing_user_when_email_matches(self):
        user = get_user_model().objects.create_user(
            username="initial-admin",
            email="initial-admin@example.com",
            password="ExistingUser-936!Tiger",
        )
        bootstrap_environment = {
            "BOOTSTRAP_ADMIN_USERNAME": "initial-admin",
            "BOOTSTRAP_ADMIN_EMAIL": "initial-admin@example.com",
        }

        with patch.dict(os.environ, bootstrap_environment, clear=True):
            call_command("bootstrap_admin")

        user.refresh_from_db()
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("ExistingUser-936!Tiger"))

    def test_rejects_incomplete_environment_variables(self):
        with patch.dict(
            os.environ,
            {"BOOTSTRAP_ADMIN_USERNAME": "initial-admin"},
            clear=True,
        ):
            with self.assertRaises(CommandError):
                call_command("bootstrap_admin")


class SeedMedicationsCommandTests(TestCase):
    def test_imports_catalog_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base_directory = Path(temporary_directory)
            catalog_directory = base_directory / "data"
            catalog_directory.mkdir()
            catalog_path = catalog_directory / "medications.xlsx"

            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Lista PMC"
            worksheet.append(
                ["PRODUTO", "TARJA", "CLASSE TERAPÊUTICA", "REGISTRO"]
            )
            worksheet.append(
                ["DIPIRONA", "Tarja sem tarja", "Analgésicos", "123"]
            )
            worksheet.append(
                ["Dipirona", "Tarja sem tarja", "Analgésicos", "456"]
            )
            workbook.save(catalog_path)

            with override_settings(BASE_DIR=base_directory):
                call_command("seed_medications")
                call_command("seed_medications")

        self.assertEqual(Medication.objects.count(), 1)
        medication = Medication.objects.get()
        self.assertEqual(medication.name, "DIPIRONA")
        self.assertEqual(medication.anvisa_registration, "123")

    def test_reports_missing_bundled_catalog(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with override_settings(BASE_DIR=Path(temporary_directory)):
                with self.assertRaisesMessage(
                    CommandError,
                    "Medication catalog not found",
                ):
                    call_command("seed_medications")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordChangeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="password-user",
            email="password-user@example.com",
            password="Current-password-842!",
        )
        self.client.force_authenticate(user=self.user)

    def request_code(self):
        response = self.client.post("/api/users/password/change/code/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("code", response.data)
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group()
        return code

    def test_changes_password_and_consumes_code(self):
        token = self.user.token
        code = self.request_code()
        challenge = VerificationChallenge.objects.get(user=self.user)
        self.assertNotEqual(challenge.code_hash, code)

        response = self.client.post(
            "/api/users/password/change/",
            {"code": code, "new_password": "Updated-password-763!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            self.user.__class__.objects.get(pk=self.user.pk).check_password(
                "Updated-password-763!"
            )
        )
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertNotIn(token, response.data.values())

        response = self.client.post(
            "/api/users/password/change/",
            {"code": code, "new_password": "Another-password-937!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_validation_is_in_portuguese(self):
        response = self.client.post(
            "/api/users/password/change/",
            {"code": "123456", "new_password": "123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("senha", " ".join(response.data["new_password"]).lower())

    def test_rejects_invalid_code_and_limits_attempts(self):
        valid_code = self.request_code()
        invalid_code = "000000" if valid_code != "000000" else "000001"

        for _ in range(5):
            response = self.client.post(
                "/api/users/password/change/",
                {"code": invalid_code, "new_password": "Updated-password-763!"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        challenge = VerificationChallenge.objects.get(user=self.user)
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.consumed_at)

    def test_code_request_requires_user_email(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])

        response = self.client.post("/api/users/password/change/code/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(VerificationChallenge.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_code_request_has_resend_cooldown(self):
        first_response = self.client.post("/api/users/password/change/code/")
        second_response = self.client.post("/api/users/password/change/code/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(VerificationChallenge.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_can_be_reset_without_authentication(self):
        self.client.force_authenticate(user=None)

        code_response = self.client.post(
            "/api/users/password/change/code/",
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(code_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            code_response.data["detail"],
            "Se houver uma conta com esse e-mail, o código será enviado.",
        )
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group()
        token = self.user.token

        response = self.client.post(
            "/api/users/password/change/",
            {
                "email": self.user.email,
                "code": code,
                "new_password": "Xylophone-cactus-594!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            get_user_model().objects.get(pk=self.user.pk).check_password(
                "Xylophone-cactus-594!"
            )
        )
        self.assertFalse(Token.objects.filter(key=token).exists())

    def test_anonymous_code_request_does_not_reveal_account_existence(self):
        self.client.force_authenticate(user=None)

        existing_response = self.client.post(
            "/api/users/password/change/code/",
            {"email": self.user.email},
            format="json",
        )
        existing_response_detail = existing_response.data["detail"]

        self.client.force_authenticate(user=None)
        unknown_response = APIClient().post(
            "/api/users/password/change/code/",
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(existing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown_response.data["detail"], existing_response_detail)
        self.assertEqual(len(mail.outbox), 1)

    def test_anonymous_password_reset_requires_email(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/users/password/change/",
            {"code": "123456", "new_password": "Reset-password-594!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserCreateViewTests(TestCase):
    def test_creates_user_with_hashed_password_and_safe_response(self):
        response = APIClient().post(
            "/api/users/",
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "first_name": "New",
                "last_name": "User",
                "password": "A-strong-password-928!",
                "is_staff": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        self.assertNotIn("is_staff", response.data)

        user = get_user_model().objects.get(username="new-user")
        self.assertTrue(user.check_password("A-strong-password-928!"))
        self.assertNotEqual(user.password, "A-strong-password-928!")
        self.assertFalse(user.is_staff)

    def test_rejects_weak_password(self):
        response = APIClient().post(
            "/api/users/",
            {"username": "new-user", "password": "123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertFalse(get_user_model().objects.filter(username="new-user").exists())

    def test_rejects_duplicate_username(self):
        get_user_model().objects.create_user(
            username="existing-user",
            password="A-strong-password-928!",
        )

        response = APIClient().post(
            "/api/users/",
            {"username": "existing-user", "password": "Another-strong-password-834!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MedicationImportViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )

    def test_medication_list_can_filter_by_partial_name_case_insensitively(self):
        self.client.force_authenticate(user=self.admin)
        Medication.objects.create(name="DIPIRONA")
        Medication.objects.create(name="VIAGRA")

        response = self.client.get("/api/medications/?name=dipi")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["name"] for item in response.data["results"]],
            ["DIPIRONA"],
        )

    def test_medication_list_is_paginated_with_20_items_per_page(self):
        self.client.force_authenticate(user=self.admin)
        Medication.objects.bulk_create(
            [Medication(name=f"MEDICAMENTO {number}") for number in range(25)]
        )

        response = self.client.get("/api/medications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

        response = self.client.get("/api/medications/?page=2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])

    def create_workbook_upload(self, rows, sheet_name="Lista PMC"):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name
        worksheet.append(["PRODUTO", "TARJA", "CLASSE TERAPÊUTICA", "REGISTRO"])
        for row in rows:
            worksheet.append(row)

        content = BytesIO()
        workbook.save(content)
        return SimpleUploadedFile(
            "medicamentos.xlsx",
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_imports_unique_products_and_is_idempotent(self):
        self.client.force_authenticate(user=self.admin)
        rows = [
            ["VIAGRA", "Tarja Vermelha", "Classe terapêutica", "1021602620013"],
            ["VIAGRA", "Tarja Vermelha", "Classe terapêutica", "1021602620021"],
            ["Dipirona", "Tarja Sem Tarja", "Analgésicos", "1018600360022"],
        ]

        response = self.client.post(
            "/api/medications/import/",
            {"file": self.create_workbook_upload(rows)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["duplicate_rows"], 1)
        self.assertEqual(Medication.objects.count(), 2)
        viagra = Medication.objects.get(name="VIAGRA")
        self.assertEqual(viagra.anvisa_registration, "1021602620013")
        self.assertEqual(viagra.stripe, "Tarja Vermelha")

        response = self.client.post(
            "/api/medications/import/",
            {"file": self.create_workbook_upload(rows)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["already_existing"], 2)
        self.assertEqual(Medication.objects.count(), 2)

    def test_medication_api_rejects_duplicate_name_case_insensitively(self):
        self.client.force_authenticate(user=self.admin)
        Medication.objects.create(name="DIPIRONA")

        response = self.client.post(
            "/api/medications/",
            {"name": "  dipirona  "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Medication.objects.count(), 1)

    def test_import_requires_admin_user(self):
        user = get_user_model().objects.create_user(
            username="user",
            password="test-password",
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/medications/import/",
            {"file": self.create_workbook_upload([])},
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)

    def test_import_rejects_missing_file_and_wrong_sheet(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post("/api/medications/import/", {}, format="multipart")
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/medications/import/",
            {"file": self.create_workbook_upload([], sheet_name="Dados")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Medication.objects.count(), 0)
