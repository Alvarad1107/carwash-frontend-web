from django.contrib import admin
from .models import CatalogoVehiculos, CatalogoServicios, Roles

# Cambiar el título del panel
admin.site.site_header = "Administración Sprint Wash"
admin.site.site_title = "Sprint Wash Panel"
admin.site.index_title = "Bienvenido al Panel de Control de Sprint Wash"

# Registrar las tablas
admin.site.register(CatalogoVehiculos)
admin.site.register(CatalogoServicios)
admin.site.register(Roles)
