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
from panel_admin.views import (
    cambiar_estado_orden,
    catalogos,
    dashboard_prueba,
    login_prueba,
    modulo_finanzas,
    modulo_usuarios,
    monitor_operaciones,
    registro_orden,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard_prueba, name="dashboard"),
    path("login/", login_prueba, name="login"),
    path("monitor/", monitor_operaciones, name="monitor"),
    path(
        "monitor/estado/<int:orden_id>/",
        cambiar_estado_orden,
        name="cambiar_estado_orden",
    ),
    path("caja/", registro_orden, name="caja"),
    path("finanzas/", modulo_finanzas, name="finanzas"),
    path("catalogos/", catalogos, name="catalogos"),
    path("usuarios/", modulo_usuarios, name="usuarios"),
]
