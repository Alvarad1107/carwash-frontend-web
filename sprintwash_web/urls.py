"""
URL configuration for sprintwash_web project.
"""
from django.contrib import admin
from django.urls import path
from panel_admin.views import (
    cambiar_estado_orden,
    catalogos,
    dashboard_prueba,
    login_prueba,
    modulo_clientes,
    modulo_finanzas,
    modulo_usuarios,
    monitor_operaciones,
    registro_orden,
    modulo_inventario,
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
    path("clientes/", modulo_clientes, name="clientes"),
    path("finanzas/", modulo_finanzas, name="finanzas"),
    path("catalogos/", catalogos, name="catalogos"),
    path("usuarios/", modulo_usuarios, name="usuarios"),
    path("inventario/", modulo_inventario, name="inventario"),
]
