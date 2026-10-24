import logging
import secrets
import smtplib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import render
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.viewsets import ModelViewSet
from apimedcerto.models import *
from apimedcerto.serializers import *
from django.contrib.auth import authenticate
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiRequest,
    extend_schema,
    extend_schema_view,
)
from apimedcerto.medication_import import MedicationImportError, import_medications

logger = logging.getLogger(__name__)
VERIFICATION_CODE_LIFETIME = timedelta(minutes=10)
VERIFICATION_CODE_MAX_ATTEMPTS = 5
VERIFICATION_CODE_RESEND_DELAY = timedelta(minutes=1)


class ApiMedCertoViewSet(ModelViewSet):
    pass

@extend_schema_view(
    list=extend_schema(
        tags=['Medicamentos'],
        summary='Listar medicamentos',
        description=(
            'Retorna o catálogo paginado com 20 itens por página. Use `name` para '
            'filtrar por trecho do nome, sem diferenciar maiúsculas de minúsculas.'
        ),
        parameters=[
            OpenApiParameter(
                name='name',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Trecho do nome do medicamento usado para filtrar resultados.',
                examples=[OpenApiExample('Buscar dipirona', value='dipi')],
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=['Medicamentos'],
        summary='Consultar medicamento',
        description='Retorna os dados de um medicamento pelo identificador.',
    ),
    create=extend_schema(
        tags=['Medicamentos'],
        summary='Cadastrar medicamento',
        description='Cadastra um medicamento. O nome não pode duplicar outro medicamento.',
    ),
    update=extend_schema(
        tags=['Medicamentos'],
        summary='Atualizar medicamento',
        description='Substitui os dados de um medicamento existente.',
    ),
    partial_update=extend_schema(
        tags=['Medicamentos'],
        summary='Atualizar parcialmente medicamento',
        description='Atualiza somente os campos enviados de um medicamento existente.',
    ),
    destroy=extend_schema(
        tags=['Medicamentos'],
        summary='Remover medicamento',
        description='Remove um medicamento do catálogo.',
    ),
)
class MedicationViewSet(ApiMedCertoViewSet):
    queryset = Medication.objects.all()
    serializer_class = MedicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Medication.objects.order_by("name", "pk")
        name = self.request.query_params.get("name", "").strip()
        if name:
            queryset = queryset.filter(name__icontains=name)
        return queryset

class MedicationImportView(APIView):
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['Medicamentos'],
        summary='Importar medicamentos de uma planilha',
        description=(
            "Importa a aba 'Lista PMC' de um arquivo .xlsx usando as colunas "
            '`PRODUTO`, `TARJA`, `CLASSE TERAPÊUTICA` e `REGISTRO`. Nomes repetidos '
            'são ignorados; a operação pode ser executada novamente sem duplicar '
            'medicamentos. Requer autenticação de administrador.'
        ),
        request=OpenApiRequest(
            request=MedicationImportRequestSerializer,
            encoding={
                'file': {
                    'contentType': (
                        'application/vnd.openxmlformats-officedocument.'
                        'spreadsheetml.sheet'
                    ),
                },
            },
        ),
        responses={
            200: MedicationImportResponseSerializer,
            400: MessageResponseSerializer,
            401: MessageResponseSerializer,
            403: MessageResponseSerializer,
        },
        examples=[
            OpenApiExample(
                'Importação concluída',
                value={
                    'rows_read': 26635,
                    'unique_products': 6012,
                    'created': 6012,
                    'already_existing': 0,
                    'duplicate_rows': 20623,
                    'rows_without_name': 0,
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "Envie a planilha no campo 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = import_medications(uploaded_file)
        except MedicationImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)

class UserCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Usuários'],
        summary='Criar conta de usuário',
        description=(
            'Cria uma conta. A senha é validada pelas regras configuradas no Django '
            'e nunca é retornada na resposta. Permissões administrativas não podem '
            'ser definidas por esta rota.'
        ),
        request=UserCreateSerializer,
        responses={
            201: UserPublicSerializer,
            400: MessageResponseSerializer,
        },
        examples=[
            OpenApiExample(
                'Dados para cadastro',
                value={
                    'username': 'maria',
                    'email': 'maria@example.com',
                    'first_name': 'Maria',
                    'last_name': 'Silva',
                    'password': 'UmaSenhaForte123!',
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserCreateSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class PasswordChangeCodeView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_code_anon"

    @extend_schema(
        tags=['Recuperação de senha'],
        summary='Solicitar código de verificação',
        description=(
            'Envia por e-mail um código de seis dígitos válido por 10 minutos. '
            'Autenticado: o código vai para o e-mail da própria conta e há intervalo '
            'de um minuto entre solicitações. Sem autenticação: informe `email`; '
            'a resposta não revela se existe uma conta com esse endereço. Limite '
            'anônimo: 5 solicitações por hora.'
        ),
        request=VerificationCodeRequestSerializer,
        responses={
            200: MessageResponseSerializer,
            400: MessageResponseSerializer,
            429: MessageResponseSerializer,
            503: MessageResponseSerializer,
        },
        examples=[
            OpenApiExample(
                'Solicitação sem autenticação',
                value={'email': 'maria@example.com'},
                request_only=True,
            ),
            OpenApiExample(
                'Resposta genérica',
                value={
                    'detail': (
                        'Se houver uma conta com esse e-mail, o código será enviado.'
                    )
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        is_authenticated = request.user.is_authenticated
        if is_authenticated:
            user = request.user
            response_detail = "Código de verificação enviado para o e-mail cadastrado."
        else:
            email = request.data.get("email", "")
            if not isinstance(email, str) or not email.strip():
                return Response(
                    {"detail": "Informe o e-mail cadastrado na sua conta."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users = list(
                User.objects.filter(
                    email__iexact=email.strip(),
                    is_active=True,
                ).order_by("pk")[:2]
            )
            if len(users) != 1:
                return Response(
                    {
                        "detail": (
                            "Se houver uma conta com esse e-mail, "
                            "o código será enviado."
                        )
                    },
                    status=status.HTTP_200_OK,
                )
            user = users[0]
            response_detail = (
                "Se houver uma conta com esse e-mail, o código será enviado."
            )

        if not user.email:
            return Response(
                {"detail": "Cadastre um e-mail para receber o código de verificação."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = f"{secrets.randbelow(1_000_000):06d}"
        now = timezone.now()
        latest_challenge = (
            VerificationChallenge.objects.filter(
                user=user,
                purpose=VerificationChallenge.Purpose.PASSWORD_CHANGE,
                channel=VerificationChallenge.Channel.EMAIL,
            )
            .order_by("-timestamp_create")
            .first()
        )
        if (
            latest_challenge is not None
            and latest_challenge.timestamp_create > now - VERIFICATION_CODE_RESEND_DELAY
        ):
            if not is_authenticated:
                return Response(
                    {"detail": response_detail},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"detail": "Aguarde um minuto antes de solicitar outro código."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            with transaction.atomic():
                VerificationChallenge.objects.filter(
                    user=user,
                    purpose=VerificationChallenge.Purpose.PASSWORD_CHANGE,
                    channel=VerificationChallenge.Channel.EMAIL,
                    consumed_at__isnull=True,
                ).update(consumed_at=now)
                VerificationChallenge.objects.create(
                    user=user,
                    purpose=VerificationChallenge.Purpose.PASSWORD_CHANGE,
                    channel=VerificationChallenge.Channel.EMAIL,
                    code_hash=make_password(code),
                    expires_at=now + VERIFICATION_CODE_LIFETIME,
                )
                sent_count = send_mail(
                    subject="Código para alterar sua senha",
                    message=(
                        f"Seu código para alterar a senha é {code}. "
                        "Ele expira em 10 minutos."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                if sent_count != 1:
                    raise smtplib.SMTPException("The verification email was not sent.")
        except (ImproperlyConfigured, OSError, smtplib.SMTPException):
            logger.exception("Could not send password change verification code.")
            return Response(
                {"detail": "Não foi possível enviar o código. Tente novamente mais tarde."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": response_detail}, status=status.HTTP_200_OK)


class PasswordChangeView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Recuperação de senha'],
        summary='Alterar ou recuperar senha',
        description=(
            'Altera a senha usando o código enviado por e-mail. Autenticado: envie '
            '`code` e `new_password`. Sem autenticação: envie também o `email` da '
            'conta. O código é de uso único, expira em 10 minutos e permite no máximo '
            '5 tentativas. A senha deve cumprir as regras configuradas no Django. '
            'Os tokens de autenticação existentes são revogados após a troca.'
        ),
        request=PasswordChangeSerializer,
        responses={
            200: MessageResponseSerializer,
            400: MessageResponseSerializer,
        },
        examples=[
            OpenApiExample(
                'Recuperação sem autenticação',
                value={
                    'email': 'maria@example.com',
                    'code': '123456',
                    'new_password': 'UmaSenhaForte123!',
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        if request.user.is_authenticated:
            user = request.user
        else:
            email = request.data.get("email", "")
            if not isinstance(email, str) or not email.strip():
                return Response(
                    {"detail": "Informe o e-mail cadastrado na sua conta."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users = list(
                User.objects.filter(
                    email__iexact=email.strip(),
                    is_active=True,
                ).order_by("pk")[:2]
            )
            if len(users) != 1:
                return Response(
                    {"detail": "Código inválido ou expirado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = users[0]

        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"user": user},
        )
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]
        now = timezone.now()

        with transaction.atomic():
            challenge = (
                VerificationChallenge.objects.select_for_update()
                .filter(
                    user=user,
                    purpose=VerificationChallenge.Purpose.PASSWORD_CHANGE,
                    channel=VerificationChallenge.Channel.EMAIL,
                    consumed_at__isnull=True,
                    expires_at__gt=now,
                    attempts__lt=VERIFICATION_CODE_MAX_ATTEMPTS,
                )
                .order_by("-timestamp_create")
                .first()
            )
            if challenge is None:
                return Response(
                    {"detail": "Código inválido ou expirado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not check_password(code, challenge.code_hash):
                challenge.attempts += 1
                if challenge.attempts >= VERIFICATION_CODE_MAX_ATTEMPTS:
                    challenge.consumed_at = now
                    challenge.save(update_fields=["attempts", "consumed_at"])
                else:
                    challenge.save(update_fields=["attempts"])
                return Response(
                    {"detail": "Código inválido ou expirado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            user.set_password(new_password)
            user.save(update_fields=["password"])
            Token.objects.filter(user=user).delete()

        return Response(
            {"detail": "Senha alterada com sucesso. Faça login novamente."},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):

    @extend_schema(
        tags=['Usuários'],
        summary='Autenticar usuário',
        description='Autentica com nome de usuário e senha e retorna um token de acesso.',
        request=LoginRequestSerializer,
        responses={
            200: LoginSerializer,
            401: MessageResponseSerializer,
        },
        examples=[
            OpenApiExample(
                'Credenciais',
                value={'username': 'maria', 'password': 'UmaSenhaForte123!'},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)

        if user is None:
            return Response({"detail": "Usuário ou senha inválidos."}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(LoginSerializer(user, many=False).data)
