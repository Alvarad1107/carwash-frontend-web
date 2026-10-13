from django.shortcuts import render

# Create your views here.

from django.shortcuts import render


def dashboard_prueba(request):
    return render(request, 'base.html')


def login_prueba(request):
    return render(request, 'login.html')


def monitor_operaciones(request):
    return render(request, 'monitor.html')


def registro_orden(request):
    return render(request, 'registro_orden.html')


def catalogos(request):
    return render(request, 'catalogos.html')


def modulo_usuarios(request):
    return render(request, 'usuarios.html')
