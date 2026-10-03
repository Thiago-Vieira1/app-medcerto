from rest_framework import serializers
from apimedcerto.models import *


class MedicationSerializer(serializers.ModelSerializer):


    class Meta:
        model = Medication
        fields = '__all__'
        read_only_fields = ['user']

class LoginSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['token', 'username', 'email', 'first_name', 'last_name']