from django.db import models


class CatalogoVehiculos(models.Model):
    tipo = models.CharField(max_length=100)
    cargo_extra = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name_plural = "Catálogo de Vehículos"

    def __str__(self):
        return self.tipo


class CatalogoServicios(models.Model):
    nombre = models.CharField(max_length=100)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_estimada_minutos = models.IntegerField()

    class Meta:
        verbose_name_plural = "Catálogo de Servicios"

    def __str__(self):
        return self.nombre


class Roles(models.Model):
    nombre = models.CharField(max_length=50)

    class Meta:
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre
