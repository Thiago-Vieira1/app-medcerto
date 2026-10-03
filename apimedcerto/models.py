from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class MedCertoModel(models.Model):
    timestamp_create=models.DateTimeField(auto_now_add=True)
    timestamp_update=models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class User(AbstractUser, MedCertoModel):

    @property
    def token(self):
        from rest_framework.authtoken.models import Token

        return Token.objects.get_or_create(user=self).key

class Medication(MedCertoModel):
    user=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name=models.CharField(max_length=100, blank=True, null=True)
    dosage=models.CharField(max_length=50)
    description=models.TextField(blank=True, null=True)
    # intervalo_horas=models.IntegerField()


