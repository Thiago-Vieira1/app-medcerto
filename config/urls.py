"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from apimedcerto.views import *

router = DefaultRouter()

router.register(r'medications', MedicationViewSet, basename='medication')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/medications/import/', MedicationImportView.as_view(), name='medication-import'),
    path('api/users/', UserCreateView.as_view(), name='user-create'),
    path('api/users/password/change/code/', PasswordChangeCodeView.as_view(), name='password-change-code'),
    path('api/users/password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('api/', include(router.urls)),
    path('api/login/', LoginView.as_view()),
]