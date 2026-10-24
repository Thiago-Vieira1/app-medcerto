from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.functions import Lower


class MedCertoModel(models.Model):
    timestamp_create=models.DateTimeField(auto_now_add=True)
    timestamp_update=models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class User(AbstractUser, MedCertoModel):

    @property
    def token(self):
        from rest_framework.authtoken.models import Token

        return Token.objects.get_or_create(user=self)[0].key

class Medication(MedCertoModel):
    name = models.CharField(max_length=255)
    stripe = models.CharField(max_length=50, blank=True)
    therapeutic_class = models.TextField(blank=True)
    anvisa_registration = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), name="medication_name_ci_unique"),
        ]


class VerificationChallenge(MedCertoModel):
    class Purpose(models.TextChoices):
        PASSWORD_CHANGE = "password_change", "Password change"
        TWO_FACTOR_AUTHENTICATION = "two_factor_authentication", "Two-factor authentication"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        AUTHENTICATOR = "authenticator", "Authenticator"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="verification_challenges",
    )
    purpose = models.CharField(max_length=40, choices=Purpose.choices)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(blank=True, null=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "purpose", "channel", "consumed_at"],
                name="verification_challenge_lookup",
            ),
        ]
