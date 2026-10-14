from django.shortcuts import redirect, render
import requests

API_URL = "http://127.0.0.1:8000"


def dashboard_prueba(request):
    return render(request, "base.html")


def login_prueba(request):
    return render(request, "login.html")


def monitor_operaciones(request):
    ordenes_lista = []
    conteo_pendientes = 0
    conteo_en_proceso = 0
    conteo_terminados = 0

    try:
        # Consumimos los endpoints de la API
        res_ordenes = requests.get(f"{API_URL}/ordenes/", timeout=5)
        res_vehiculos = requests.get(f"{API_URL}/vehiculos/", timeout=5)
        res_clientes = requests.get(f"{API_URL}/clientes/", timeout=5)

        ordenes = res_ordenes.json() if res_ordenes.status_code == 200 else []
        vehiculos = res_vehiculos.json() if res_vehiculos.status_code == 200 else []
        clientes = res_clientes.json() if res_clientes.status_code == 200 else []

        # Diccionarios por ID para cruzar los datos
        vehiculos_dict = {v["id"]: v for v in vehiculos}
        clientes_dict = {c["id"]: c for c in clientes}

        for o in ordenes:
            estado = o.get("estado", "Pendiente")

            # Sumar a las tarjetas superiores y definir texto de seguimiento
            if estado == "Pendiente":
                conteo_pendientes += 1
                tiempo_texto = "En espera"
            elif estado == "En proceso":
                conteo_en_proceso += 1
                tiempo_texto = "En bahía de lavado"
            elif estado in ["Listo para entrega", "Terminado"]:
                conteo_terminados += 1
                tiempo_texto = "Listo para retiro"
            else:
                tiempo_texto = "En patio"

            vehiculo = vehiculos_dict.get(o.get("vehiculo_id"), {})
            cliente = clientes_dict.get(vehiculo.get("cliente_id"), {})

            placa = vehiculo.get("placa", "Sin Placa")
            marca = vehiculo.get("marca", "")
            modelo = vehiculo.get("modelo", "")
            detalle_auto = f"{marca} {modelo}".strip()

            ordenes_lista.append({
                "id_formateado": f"{o.get('id', 0):08d}",
                "id": o.get("id"),
                "cliente_nombre": cliente.get("nombre_completo", "Cliente General"),
                "vehiculo_info": (
                    f"{placa} / {detalle_auto}" if detalle_auto else placa
                ),
                "servicio_total": (
                    f"Orden de Lavado (${float(o.get('total_pagar', 0)):.2f})"
                ),
                "tiempo": tiempo_texto,
                "estado": estado,
            })

    except Exception as e:
        print(f"Error conectando con la API de SprintWash: {e}")

    contexto = {
        "ordenes": ordenes_lista,
        "pendientes": conteo_pendientes,
        "en_proceso": conteo_en_proceso,
        "terminados": conteo_terminados,
    }

    return render(request, "monitor.html", contexto)


def cambiar_estado_orden(request, orden_id):
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        if nuevo_estado:
            try:
                # Llamamos al endpoint PATCH de FastAPI (timeout=10 por el envío de correo SMTP)
                requests.patch(
                    f"{API_URL}/ordenes/{orden_id}/estado",
                    json={"estado": nuevo_estado},
                    timeout=10,
                )
            except Exception as e:
                print(
                    f"Error actualizando el estado de la orden {orden_id}: {e}")
    return redirect("monitor")


def registro_orden(request):
    return render(request, "registro_orden.html")


def catalogos(request):
    return render(request, "catalogos.html")


def modulo_usuarios(request):
    return render(request, "usuarios.html")
