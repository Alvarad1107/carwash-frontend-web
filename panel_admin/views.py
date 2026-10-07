from django.shortcuts import render

# Create your views here.

from django.shortcuts import render


def dashboard_prueba(request):
    return render(request, 'base.html')


def login_prueba(request):
    return render(request, 'login.html')


def monitor_operaciones(request):
    return render(request, 'monitor.html')
