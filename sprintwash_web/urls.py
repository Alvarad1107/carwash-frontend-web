"""
URL configuration for sprintwash_web project.

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
from django.urls import path
# Importa tu vista
from panel_admin.views import dashboard_prueba, login_prueba, monitor_operaciones, registro_orden, catalogos, modulo_usuarios

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_prueba, name='dashboard'),  # Ruta principal
    path('login/', login_prueba, name='login'),  # Ruta para la página de login
    # Ruta para la página de monitorización
    path('monitor/', monitor_operaciones, name='monitor'),
    # Ruta para la página de registro de órdenes
    path('caja/', registro_orden, name='caja'),
    # Ruta para la página de catálogos
    path('catalogos/', catalogos, name='catalogos'),
    path('usuarios/', modulo_usuarios, name='usuarios'),
]
