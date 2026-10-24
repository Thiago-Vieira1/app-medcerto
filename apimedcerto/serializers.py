from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import override
from rest_framework import serializers
from apimedcerto.models import *


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField(help_text='Nome de usuário cadastrado.')
    password = serializers.CharField(
        write_only=True,
        help_text='Senha da conta.',
    )


class VerificationCodeRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=False,
        help_text=(
            'Obrigatório quando não estiver autenticado. Para usuários autenticados, '
            'o código será enviado ao e-mail da própria conta.'
        ),
    )


class MedicationImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="Planilha .xlsx da lista PMC, contendo a aba 'Lista PMC'."
    )


class MedicationImportResponseSerializer(serializers.Serializer):
    rows_read = serializers.IntegerField(help_text='Número de linhas de dados lidas.')
    unique_products = serializers.IntegerField(help_text='Produtos únicos encontrados na planilha.')
    created = serializers.IntegerField(help_text='Medicamentos novos cadastrados.')
    already_existing = serializers.IntegerField(help_text='Medicamentos que já existiam no catálogo.')
    duplicate_rows = serializers.IntegerField(help_text='Linhas repetidas ignoradas.')
    rows_without_name = serializers.IntegerField(help_text='Linhas sem nome de produto ignoradas.')


class MessageResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(help_text='Mensagem da operação em português.')


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']


class PasswordChangeSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=False,
        write_only=True,
        help_text='Obrigatório para redefinição sem autenticação.',
        error_messages={
            'invalid': 'Informe um e-mail válido.',
            'required': 'Informe o e-mail cadastrado na sua conta.',
        },
    )
    code = serializers.RegexField(
        regex=r"^\d{6}$",
        help_text='Código de verificação de seis dígitos enviado por e-mail.',
        error_messages={
            'invalid': 'Informe um código numérico de 6 dígitos.',
            'required': 'Informe o código de verificação.',
        },
    )
    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        help_text='Nova senha, sujeita às regras de segurança configuradas no Django.',
        error_messages={
            'blank': 'Informe a nova senha.',
            'required': 'Informe a nova senha.',
        },
    )

    def validate_new_password(self, value):
        try:
            with override('pt-br'):
                password_validation.validate_password(
                    value,
                    user=self.context["user"],
                )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text='Senha da conta, validada conforme as regras de segurança do Django.',
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def validate(self, attrs):
        user = User(
            username=attrs.get('username', ''),
            email=attrs.get('email', ''),
            first_name=attrs.get('first_name', ''),
            last_name=attrs.get('last_name', ''),
        )
        try:
            password_validation.validate_password(attrs['password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class MedicationSerializer(serializers.ModelSerializer):
    name = serializers.CharField(help_text='Nome do medicamento.')
    stripe = serializers.CharField(
        help_text='Classificação de tarja do medicamento.',
        allow_blank=True,
        required=False,
    )
    therapeutic_class = serializers.CharField(
        help_text='Classe terapêutica do medicamento.',
        allow_blank=True,
        required=False,
    )
    anvisa_registration = serializers.CharField(
        help_text='Número de registro na Anvisa.',
        allow_blank=True,
        required=False,
    )

    def validate_name(self, value):
        normalized_name = " ".join(value.strip().upper().split())
        medications = Medication.objects.filter(name__iexact=normalized_name)
        if self.instance is not None:
            medications = medications.exclude(pk=self.instance.pk)
        if medications.exists():
            raise serializers.ValidationError("Já existe um medicamento com esse nome.")
        return normalized_name

    class Meta:
        model = Medication
        fields = '__all__'

class LoginSerializer(serializers.ModelSerializer):
    token = serializers.CharField(
        read_only=True,
        help_text='Token usado no cabeçalho Authorization: Token <token>.',
    )

    class Meta:
        model = User
        fields = ['token', 'username', 'email', 'first_name', 'last_name']