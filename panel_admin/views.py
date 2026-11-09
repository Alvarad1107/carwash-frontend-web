from django.shortcuts import render, redirect
from functools import wraps
from django.contrib import messages
from datetime import datetime, timedelta, timezone
import requests

API_URL = "http://127.0.0.1:8000"


def verificar_acceso_y_estado(request):
    """Verifica que exista sesión y que el usuario no haya sido desactivado en tiempo real."""
    uid = request.session.get("usuario_id")
    if not uid:
        messages.error(
            request, "Necesitas iniciar sesión para acceder al sistema.")
        return False

    usuarios = obtener_json("/finanzas/usuarios")
    if usuarios:
        usuario_actual = next(
            (u for u in usuarios if u.get("id") == uid), None)
        if usuario_actual and usuario_actual.get("estado") == 0:
            request.session.flush()
            messages.error(
                request,
                "Tu sesión ha sido cerrada porque tu cuenta fue desactivada por un Administrador.",
            )
            return False
    return True


def login_requerido(view_func):
    """Evita que entren a cualquier módulo por URL si no han iniciado sesión o si fueron desactivados."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not verificar_acceso_y_estado(request):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


def solo_administrador(view_func):
    """Restringe el acceso exclusivamente al rol Administrador (Encargado General)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not verificar_acceso_y_estado(request):
            return redirect("login")
        if request.session.get("rol_id") != 1:
            messages.error(
                request, "Acceso denegado: Se requieren privilegios de Administrador."
            )
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)
    return wrapper


def cajero_o_admin(view_func):
    """Permite acceso a Administradores y Cajeros."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not verificar_acceso_y_estado(request):
            return redirect("login")
        if request.session.get("rol_id") == 3:
            messages.error(
                request,
                "Acceso restringido: Esta área es exclusiva para Caja y Administración.",
            )
            return redirect("monitor")
        return view_func(request, *args, **kwargs)
    return wrapper


# Zona horaria oficial de El Salvador (UTC-6 fijo todo el año)
TZ_SV = timezone(timedelta(hours=-6))


def ahora_sv():
    """Devuelve la fecha y hora actual exacta en El Salvador (UTC-6)."""
    return datetime.now(TZ_SV)


def fecha_iso_a_sv(fecha_str):
    """Convierte cualquier fecha UTC proveniente de la API a hora local de El Salvador (UTC-6)."""
    if not fecha_str:
        return ahora_sv()
    try:
        limpia = str(fecha_str).replace("Z", "")
        dt = datetime.fromisoformat(limpia)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_SV)
    except Exception:
        return ahora_sv()


def es_fecha_de_hoy(fecha_str):
    """Verifica si una fecha ISO pertenece al día de hoy en hora de El Salvador."""
    if not fecha_str:
        return True
    return fecha_iso_a_sv(fecha_str).date() == ahora_sv().date()


def obtener_json(endpoint):
    """Función auxiliar segura para consultar la API sin que un error detenga el resto."""
    try:
        res = requests.get(f"{API_URL}{endpoint}", timeout=4)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error consultando {endpoint}: {e}")
    return []


@cajero_o_admin
def dashboard_prueba(request):
    obtener_json("/finanzas/usuarios")
    hoy = ahora_sv().date()
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    ordenes = obtener_json("/ordenes/")
    insumos = obtener_json("/inventario/")

    ingreso_dia = 0.0
    ingreso_semana = 0.0
    ingreso_mes = 0.0
    en_proceso = 0
    terminados_hoy = 0
    bahias_ocupadas_ids = set()
    ordenes_hoy = []

    for o in ordenes:
        estado = str(o.get("estado", "")).lower()
        total = float(o.get("total_pagar", 0) or 0)
        fecha_str = o.get("created_at", "")
        fecha_orden = fecha_iso_a_sv(fecha_str).date()
        de_hoy = (fecha_orden == hoy)

        # Solo procesamos en el panel operativo las órdenes del día de hoy
        if de_hoy:
            ordenes_hoy.append(o)

            if estado in ["pendiente", "en proceso", "en lavado", "lavando"]:
                en_proceso += 1
                if o.get("bahia_id"):
                    bahias_ocupadas_ids.add(int(o.get("bahia_id")))

            if estado in ["terminado", "listo para entrega", "pagado", "entregado"]:
                terminados_hoy += 1
                ingreso_dia += total

        # Acumulados históricos de semana y mes
        if estado in ["pagado", "terminado", "listo para entrega", "entregado"]:
            if fecha_orden >= inicio_semana:
                ingreso_semana += total
            if fecha_orden.year == hoy.year and fecha_orden.month == hoy.month:
                ingreso_mes += total

    bahias = [
        {
            "id": i,
            "nombre": f"Bahía {i}",
            "estado": "Ocupada" if i in bahias_ocupadas_ids else "Disponible",
        }
        for i in range(1, 7)
    ]

    alertas_stock = [
        item
        for item in insumos
        if int(item.get("cantidad_actual", 0)) <= int(item.get("stock_minimo", 0))
    ]

    context = {
        "ingreso_dia": f"{ingreso_dia:.2f}",
        "ingreso_semana": f"{ingreso_semana:.2f}",
        "ingreso_mes": f"{ingreso_mes:.2f}",
        "en_proceso": en_proceso,
        "terminados_hoy": terminados_hoy,
        "bahias": bahias,
        "bahias_libres": 6 - len(bahias_ocupadas_ids),
        "alertas_stock": alertas_stock,
        # Mostramos únicamente las órdenes del día de hoy ordenadas de la más reciente a la más antigua
        "ultimas_ordenes": sorted(
            ordenes_hoy, key=lambda x: x.get("id", 0), reverse=True
        ),
    }
    return render(request, "dashboard.html", context)


def login_prueba(request):
    if request.GET.get("logout"):
        request.session.flush()
        messages.success(request, "Sesión cerrada correctamente. Buen turno.")
        return redirect("login")

    if request.method == "POST":
        correo = request.POST.get("correo", "").strip().lower()
        password = request.POST.get("password", "").strip()

        try:
            res_auth = requests.post(
                f"{API_URL}/auth/login",
                json={"correo": correo, "password": password},
                timeout=5,
            )

            if res_auth.status_code == 200:
                datos = res_auth.json()
                rol_nombre = datos.get("rol", "SIN ROL")
                rol_upper = rol_nombre.upper()

                if "ENCARGADO" in rol_upper or "ADMIN" in rol_upper:
                    rol_id = 1
                    rol_mostrar = "ADMINISTRADOR"
                elif "CAJERO" in rol_upper:
                    rol_id = 2
                    rol_mostrar = "CAJERO"
                else:
                    rol_id = 3
                    rol_mostrar = "OPERARIO / SUPERVISOR"

                # Bloquear acceso al Sistema Web para Operarios (Exclusivos de App Móvil)
                if rol_id == 3:
                    messages.error(
                        request,
                        "Acceso denegado: El personal operativo debe ingresar desde la Aplicación Móvil.",
                    )
                    return render(request, "login.html")

                request.session["access_token"] = datos.get("access_token")
                request.session["usuario_id"] = datos.get("usuario_id")
                request.session["usuario_nombre"] = datos.get("nombre")
                request.session["rol_id"] = rol_id
                request.session["rol_nombre"] = rol_mostrar

                return redirect("dashboard")
            else:
                try:
                    detalle = res_auth.json().get("detail", "Correo o contraseña incorrectos.")
                except Exception:
                    detalle = "Error al validar credenciales con la API."
                messages.error(request, detalle)

        except Exception:
            messages.error(
                request, "Error al conectar con el servidor de autenticación.")

    return render(request, "login.html")


@login_requerido
def monitor_operaciones(request):
    hoy = ahora_sv().date()
    ayer = hoy - timedelta(days=1)

    # Leer la fecha seleccionada en el filtro o usar HOY por defecto
    fecha_filtro_str = request.GET.get("fecha", "")
    try:
        fecha_seleccionada = (
            datetime.strptime(fecha_filtro_str, "%Y-%m-%d").date()
            if fecha_filtro_str
            else hoy
        )
    except Exception:
        fecha_seleccionada = hoy

    ordenes_lista = []
    conteo_pendientes = 0
    conteo_en_proceso = 0
    conteo_terminados = 0

    ordenes = obtener_json("/ordenes/")
    vehiculos = obtener_json("/vehiculos/")
    clientes = obtener_json("/clientes/")
    pagos = obtener_json("/finanzas/pagos")

    vehiculos_dict = {v["id"]: v for v in vehiculos}
    clientes_dict = {c["id"]: c for c in clientes}
    ordenes_pagadas_ids = {p.get("orden_id") for p in pagos}

    for o in ordenes:
        fecha_orden = fecha_iso_a_sv(o.get("created_at", "")).date()
        if fecha_orden != fecha_seleccionada:
            continue

        oid = o.get("id")
        ya_pagada = oid in ordenes_pagadas_ids
        estado = o.get("estado", "Pendiente")
        if estado == "Pendiente":
            conteo_pendientes += 1
            tiempo_texto = "En espera"
        elif estado == "En proceso":
            conteo_en_proceso += 1
            tiempo_texto = "En bahía de lavado"
        elif estado in ["Listo para entrega", "Terminado", "Pagado", "Entregado"]:
            conteo_terminados += 1
            tiempo_texto = "Cobrado / Entregado" if ya_pagada else "Listo para retiro"
        else:
            tiempo_texto = "En patio"

        vehiculo = vehiculos_dict.get(o.get("vehiculo_id"), {})
        cliente = clientes_dict.get(vehiculo.get("cliente_id"), {})
        placa = vehiculo.get("placa", "Sin Placa")
        marca = vehiculo.get("marca", "")
        modelo = vehiculo.get("modelo", "")
        detalle_auto = f"{marca} {modelo}".strip()

        ordenes_lista.append({
            "id_formateado": f"{oid or 0:08d}",
            "id": oid,
            "cliente_nombre": cliente.get("nombre_completo", "Cliente General"),
            "vehiculo_info": f"{placa} / {detalle_auto}" if detalle_auto else placa,
            "servicio_total": f"Orden de Lavado (${float(o.get('total_pagar', 0)):.2f})",
            "tiempo": tiempo_texto,
            "estado": estado,
            "ya_pagada": ya_pagada,
        })

    contexto = {
        "ordenes": sorted(ordenes_lista, key=lambda x: x.get("id", 0), reverse=True),
        "pendientes": conteo_pendientes,
        "en_proceso": conteo_en_proceso,
        "terminados": conteo_terminados,
        "fecha_seleccionada": fecha_seleccionada.strftime("%Y-%m-%d"),
        "fecha_hoy": hoy.strftime("%Y-%m-%d"),
        "fecha_ayer": ayer.strftime("%Y-%m-%d"),
        "es_hoy": fecha_seleccionada == hoy,
    }
    return render(request, "monitor.html", contexto)


@login_requerido
def cambiar_estado_orden(request, orden_id):
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        if nuevo_estado:
            try:
                ordenes = obtener_json("/ordenes/")
                orden_actual = next(
                    (o for o in ordenes if o.get("id") == int(orden_id)), None
                )
                estado_actual = (orden_actual or {}).get("estado", "Pendiente")

                # Regla de flujo unidireccional: Pendiente -> En proceso -> Listo para entrega
                if estado_actual in ["Listo para entrega", "Terminado", "Pagado", "Entregado"]:
                    messages.error(
                        request,
                        f"Operación bloqueada: La orden #{int(orden_id):08d} ya fue marcada como Terminada y no puede regresar a un estado anterior.",
                    )
                    return redirect("monitor")

                if estado_actual == "En proceso" and nuevo_estado == "Pendiente":
                    messages.error(
                        request,
                        f"Operación bloqueada: La orden #{int(orden_id):08d} ya está En Proceso y no puede regresar a Pendiente.",
                    )
                    return redirect("monitor")

                requests.patch(
                    f"{API_URL}/ordenes/{orden_id}/estado",
                    json={"estado": nuevo_estado},
                    timeout=10,
                )
            except Exception as e:
                print(
                    f"Error actualizando el estado de la orden {orden_id}: {e}")
    return redirect("monitor")


@solo_administrador
def catalogos(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear_categoria":
                requests.post(
                    f"{API_URL}/categorias-vehiculos/",
                    json={
                        "nombre": request.POST.get("nombre"),
                        "comision_base": float(request.POST.get("comision_base", 0)),
                    },
                    timeout=5,
                )
            elif accion == "eliminar_categoria":
                cat_id = request.POST.get("id")
                requests.delete(
                    f"{API_URL}/categorias-vehiculos/{cat_id}", timeout=5)

            elif accion == "crear_servicio_base":
                nombre_srv = request.POST.get("nombre", "").strip()
                cat_id = int(request.POST.get("categoria_vehiculo_id"))
                precio = float(request.POST.get("precio_base", 0))

                servicios_existentes = obtener_json("/servicios/base")
                srv_id = None
                for s in servicios_existentes:
                    if s["nombre"].lower() == nombre_srv.lower():
                        srv_id = s["id"]
                        break

                if not srv_id:
                    res_nuevo = requests.post(
                        f"{API_URL}/servicios/base",
                        json={"nombre": nombre_srv},
                        timeout=5,
                    )
                    if res_nuevo.status_code == 200:
                        srv_id = res_nuevo.json().get("id")

                if srv_id:
                    requests.post(
                        f"{API_URL}/servicios/matriz-precios",
                        json={
                            "categoria_vehiculo_id": cat_id,
                            "servicio_base_id": srv_id,
                            "precio_base": precio,
                        },
                        timeout=5,
                    )
            elif accion == "eliminar_precio_matriz":
                matriz_id = request.POST.get("id")
                requests.delete(
                    f"{API_URL}/servicios/matriz-precios/{matriz_id}", timeout=5)

            elif accion == "crear_adicional":
                requests.post(
                    f"{API_URL}/servicios/adicionales",
                    json={
                        "nombre": request.POST.get("nombre"),
                        "precio_fijo": float(request.POST.get("precio_fijo", 0)),
                        "comision_extra": float(request.POST.get("comision_extra", 0)),
                    },
                    timeout=5,
                )
            elif accion == "eliminar_adicional":
                adicional_id = request.POST.get("id")
                requests.delete(
                    f"{API_URL}/servicios/adicionales/{adicional_id}", timeout=5)

        except Exception as e:
            print(f"Error procesando acción en catálogos: {e}")

        return redirect("catalogos")

    # Consultamos cada endpoint de forma independiente
    categorias = obtener_json("/categorias-vehiculos/")
    servicios_base = obtener_json("/servicios/base")
    matriz = obtener_json("/servicios/matriz-precios")
    adicionales = obtener_json("/servicios/adicionales")

    cat_dict = {c["id"]: c["nombre"] for c in categorias}
    sb_dict = {s["id"]: s["nombre"] for s in servicios_base}

    matriz_lista = []
    if matriz:
        for m in matriz:
            matriz_lista.append({
                "id": m.get("id"),
                "servicio_nombre": sb_dict.get(m.get("servicio_base_id"), "Lavado Básico"),
                "categoria_nombre": cat_dict.get(m.get("categoria_vehiculo_id"), "General"),
                "precio_base": float(m.get("precio_base", 0)),
            })
    elif servicios_base:
        # Respaldo automático por si la tabla precios_servicio_base tiene bloqueo en XAMPP local
        matriz_lista = [
            {"id": 1, "servicio_nombre": servicios_base[0]["nombre"],
                "categoria_nombre": "Sedán", "precio_base": 4.00},
            {"id": 2, "servicio_nombre": servicios_base[0]["nombre"],
                "categoria_nombre": "Pick Up", "precio_base": 8.00},
        ]

    contexto = {
        "categorias": categorias,
        "servicios_matriz": matriz_lista,
        "adicionales": adicionales,
    }
    return render(request, "catalogos.html", contexto)


@cajero_o_admin
def registro_orden(request):
    ordenes_todas = obtener_json("/ordenes/")
    bahias_raw = obtener_json("/bahias/")

    ordenes_activas = [
        o for o in ordenes_todas if o.get("estado") in ["Pendiente", "En proceso"]
    ]
    bahias_ocupadas_ids = {
        int(o.get("bahia_id")) for o in ordenes_activas if o.get("bahia_id")
    }
    vehiculos_en_lavado_map = {
        int(o.get("vehiculo_id")): {
            "orden_id": o.get("id"),
            "bahia_id": o.get("bahia_id"),
            "estado": o.get("estado"),
        }
        for o in ordenes_activas
        if o.get("vehiculo_id")
    }

    bahias_api_dict = {
        int(b.get("id", 0)): b for b in bahias_raw if b.get("id")
    }
    bahias = []
    for i in range(1, 7):
        b_info = bahias_api_dict.get(i, {})
        estado_api = b_info.get("estado", "Disponible")
        if i in bahias_ocupadas_ids:
            estado_real = "Ocupada"
        elif estado_api == "Mantenimiento":
            estado_real = "Mantenimiento"
        else:
            estado_real = "Disponible"
        bahias.append({
            "id": i,
            "nombre": b_info.get("nombre") or f"Bahía {i}",
            "estado": estado_real,
        })

    proxima_bahia = next(
        (
            b
            for b in bahias
            if b["id"] not in bahias_ocupadas_ids
            and b["estado"] != "Mantenimiento"
        ),
        None,
    )
    bahias_libres_count = sum(
        1 for b in bahias if b["estado"] == "Disponible"
    )
    patio_lleno = len(bahias_ocupadas_ids) >= 6 or (proxima_bahia is None)

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            # 1. Acción para crear un cliente nuevo desde Caja
            if accion == "crear_cliente":
                res = requests.post(
                    f"{API_URL}/clientes/",
                    json={
                        "nombre_completo": (request.POST.get("nombre_completo") or "").strip(),
                        "telefono": (request.POST.get("telefono") or "").strip() or None,
                        "correo": (request.POST.get("correo") or "").strip().lower() or None,
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Cliente registrado correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo registrar el cliente.")
                    except Exception:
                        detalle = "No se pudo registrar el cliente."
                    messages.error(request, detalle)
                return redirect("caja")

            # 1.B Acción para editar un cliente existente desde Caja
            elif accion == "editar_cliente":
                cliente_id = int(request.POST.get("cliente_id", 0))
                res = requests.patch(
                    f"{API_URL}/clientes/{cliente_id}",
                    json={
                        "nombre_completo": (request.POST.get("nombre_completo") or "").strip(),
                        "telefono": (request.POST.get("telefono") or "").strip() or None,
                        "correo": (request.POST.get("correo") or "").strip().lower() or None,
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Datos del cliente actualizados correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo actualizar el cliente.")
                    except Exception:
                        detalle = "No se pudo actualizar el cliente."
                    messages.error(request, detalle)
                return redirect("caja")

            elif accion == "editar_vehiculo":
                vehiculo_id = int(request.POST.get("vehiculo_id", 0))
                res = requests.patch(
                    f"{API_URL}/vehiculos/{vehiculo_id}",
                    json={
                        "cliente_id": int(request.POST.get("cliente_id")),
                        "categoria_vehiculo_id": int(request.POST.get("categoria_vehiculo_id")),
                        "placa": (request.POST.get("placa") or "").strip().upper(),
                        "marca": (request.POST.get("marca") or "").strip(),
                        "modelo": (request.POST.get("modelo") or "").strip(),
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Propietario y datos del vehículo actualizados correctamente."
                    )
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo actualizar el vehículo.")
                    except Exception:
                        detalle = "No se pudo actualizar el vehículo."
                    messages.error(request, detalle)

            # 2. Acción para generar la orden completa y mandarla al Monitor
            elif accion == "generar_orden":
                if len(bahias_ocupadas_ids) >= 6 or proxima_bahia is None:
                    messages.error(
                        request,
                        "Capacidad máxima alcanzada: Las 6 bahías están ocupadas en este momento. Debes finalizar un lavado en el Monitor antes de registrar otro vehículo.",
                    )
                    return redirect("caja")

                cliente_id = int(request.POST.get("cliente_id", 1))
                categoria_id = int(request.POST.get(
                    "categoria_vehiculo_id", 1))
                bahia_id = proxima_bahia["id"]
                placa = request.POST.get("placa", "").strip().upper()
                marca = request.POST.get("marca", "").strip()
                modelo = request.POST.get("modelo", "").strip()

                subtotal = float(request.POST.get("subtotal", 0))
                impuestos = float(request.POST.get("impuestos", 0))
                total_pagar = float(request.POST.get("total_pagar", 0))
                extras_ids = request.POST.getlist("extras_ids")

                # Verificar si la placa ya existe en MySQL o crear el vehículo
                vehiculos_existentes = obtener_json("/vehiculos/")
                vehiculo_existente = None
                for v in vehiculos_existentes:
                    if v.get("placa", "").strip().upper() == placa:
                        vehiculo_existente = v
                        break

                vehiculo_id = None
                if vehiculo_existente:
                    vehiculo_id = vehiculo_existente.get("id")
                    if int(vehiculo_id) in vehiculos_en_lavado_map:
                        info = vehiculos_en_lavado_map[int(vehiculo_id)]
                        messages.error(
                            request,
                            f"Operación bloqueada: El vehículo con placa {placa} ya tiene una orden activa en Bahía {info['bahia_id']} ({info['estado']}). Debe finalizarse antes de registrar otra orden.",
                        )
                        return redirect("caja")

                    # Si el vehículo ya existe y se modificaron marca, modelo, categoría o cliente, sincronizar vía PATCH
                    if (
                        (vehiculo_existente.get("marca") or "") != marca
                        or (vehiculo_existente.get("modelo") or "") != modelo
                        or int(vehiculo_existente.get("categoria_vehiculo_id") or 0) != categoria_id
                        or int(vehiculo_existente.get("cliente_id") or 0) != cliente_id
                    ):
                        requests.patch(
                            f"{API_URL}/vehiculos/{vehiculo_id}",
                            json={
                                "cliente_id": cliente_id,
                                "categoria_vehiculo_id": categoria_id,
                                "placa": placa,
                                "marca": marca,
                                "modelo": modelo,
                            },
                            timeout=5,
                        )
                else:
                    res_veh = requests.post(
                        f"{API_URL}/vehiculos/",
                        json={
                            "cliente_id": cliente_id,
                            "categoria_vehiculo_id": categoria_id,
                            "placa": placa,
                            "marca": marca,
                            "modelo": modelo,
                            "color": "N/A",
                        },
                        timeout=5,
                    )
                    if res_veh.status_code == 200:
                        vehiculo_id = res_veh.json().get("id")
                    else:
                        try:
                            detalle = res_veh.json().get("detail", "No se pudo registrar el vehículo.")
                        except Exception:
                            detalle = "No se pudo registrar el vehículo."
                        messages.error(request, detalle)
                        return redirect("caja")

                # Crear la orden en estado Pendiente, registrar detalles y actualizar montos
                if vehiculo_id:
                    res_ord = requests.post(
                        f"{API_URL}/ordenes/",
                        json={
                            "vehiculo_id": vehiculo_id,
                            "bahia_id": bahia_id,
                            "estado": "Pendiente",
                        },
                        timeout=5,
                    )
                    if res_ord.status_code == 200:
                        orden_creada = res_ord.json()
                        orden_id = orden_creada.get("id")

                        # Registrar servicios adicionales para el cálculo de comisiones
                        for extra_id in extras_ids:
                            requests.post(
                                f"{API_URL}/detalles-orden/",
                                json={
                                    "orden_id": orden_id,
                                    "servicio_adicional_id": int(extra_id),
                                },
                                timeout=5,
                            )

                        # Ajustar el subtotal, impuestos (13%) y total exacto calculado en caja
                        requests.patch(
                            f"{API_URL}/ordenes/{orden_id}",
                            json={
                                "subtotal": subtotal,
                                "impuestos": impuestos,
                                "total_pagar": total_pagar,
                            },
                            timeout=5,
                        )
                    else:
                        try:
                            detalle = res_ord.json().get("detail", "No se pudo generar la orden.")
                        except Exception:
                            detalle = "No se pudo generar la orden."
                        messages.error(request, detalle)
                        return redirect("caja")
                return redirect("monitor")
        except Exception as e:
            print(f"Error procesando orden en caja: {e}")
            messages.error(
                request, "Error de conexión al procesar la solicitud.")
            return redirect("caja")

    # Inicializar catálogos base si la BD recién se creó
    obtener_json("/finanzas/usuarios")

    # Peticiones GET para alimentar la pantalla de Punto de Venta
    clientes = obtener_json("/clientes/")
    vehiculos = obtener_json("/vehiculos/")
    categorias = obtener_json("/categorias-vehiculos/")
    adicionales = obtener_json("/servicios/adicionales")
    matriz = obtener_json("/servicios/matriz-precios")

    for v in vehiculos:
        info_act = vehiculos_en_lavado_map.get(v.get("id"))
        v["en_lavado"] = bool(info_act)
        v["bahia_activa"] = info_act["bahia_id"] if info_act else ""
        v["estado_activo"] = info_act["estado"] if info_act else ""

    if not categorias:
        categorias = [
            {"id": 1, "nombre": "Sedán", "comision_base": 2.50},
            {"id": 2, "nombre": "Pick Up", "comision_base": 3.00},
            {"id": 3, "nombre": "Carros Medianos", "comision_base": 2.50},
            {"id": 4, "nombre": "Carros Grandes", "comision_base": 3.00},
        ]

    precios_respaldo = {1: 4.00, 2: 5.00, 3: 6.00, 4: 8.00, 5: 10.00}
    precios_por_categoria = {}
    for m in matriz:
        # Tomamos el precio del Lavado Básico (servicio_base_id == 1) por categoría
        if (
            m.get("servicio_base_id") == 1
            or m.get("categoria_vehiculo_id") not in precios_por_categoria
        ):
            precios_por_categoria[m.get("categoria_vehiculo_id")] = float(
                m.get("precio_base", 0)
            )

    for cat in categorias:
        cid = cat.get("id")
        cat["precio_base"] = precios_por_categoria.get(
            cid, precios_respaldo.get(cid, 5.00)
        )

    contexto = {
        "clientes": clientes,
        "vehiculos": vehiculos,
        "categorias": categorias[:5],
        "adicionales": adicionales,
        "bahias": bahias,
        "proxima_bahia": proxima_bahia,
        "bahias_libres_count": bahias_libres_count,
        "patio_lleno": patio_lleno,
    }
    return render(request, "registro_orden.html", contexto)


@cajero_o_admin
def modulo_clientes(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear_cliente":
                res = requests.post(
                    f"{API_URL}/clientes/",
                    json={
                        "nombre_completo": (request.POST.get("nombre_completo") or "").strip(),
                        "telefono": (request.POST.get("telefono") or "").strip() or None,
                        "correo": (request.POST.get("correo") or "").strip().lower() or None,
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Cliente registrado correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo registrar el cliente.")
                    except Exception:
                        detalle = "No se pudo registrar el cliente."
                    messages.error(request, detalle)

            elif accion == "editar_cliente":
                cliente_id = int(request.POST.get("cliente_id", 0))
                res = requests.patch(
                    f"{API_URL}/clientes/{cliente_id}",
                    json={
                        "nombre_completo": (request.POST.get("nombre_completo") or "").strip(),
                        "telefono": (request.POST.get("telefono") or "").strip() or None,
                        "correo": (request.POST.get("correo") or "").strip().lower() or None,
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Datos del cliente actualizados correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo actualizar el cliente.")
                    except Exception:
                        detalle = "No se pudo actualizar el cliente."
                    messages.error(request, detalle)

            elif accion == "editar_vehiculo":
                vehiculo_id = int(request.POST.get("vehiculo_id", 0))
                res = requests.patch(
                    f"{API_URL}/vehiculos/{vehiculo_id}",
                    json={
                        "cliente_id": int(request.POST.get("cliente_id")),
                        "categoria_vehiculo_id": int(request.POST.get("categoria_vehiculo_id")),
                        "placa": (request.POST.get("placa") or "").strip().upper(),
                        "marca": (request.POST.get("marca") or "").strip(),
                        "modelo": (request.POST.get("modelo") or "").strip(),
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Propietario y datos del vehículo actualizados correctamente."
                    )
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo actualizar el vehículo.")
                    except Exception:
                        detalle = "No se pudo actualizar el vehículo."
                    messages.error(request, detalle)
        except Exception as e:
            print(f"Error en módulo de clientes: {e}")
            messages.error(request, "Error de conexión con la API.")
        return redirect("clientes")

    clientes = obtener_json("/clientes/")
    vehiculos = obtener_json("/vehiculos/")
    categorias = obtener_json("/categorias-vehiculos/")
    cat_dict = {c.get("id"): c.get("nombre") for c in categorias}

    vehiculos_por_cliente = {}
    for v in vehiculos:
        cid = v.get("cliente_id")
        v["categoria_nombre"] = cat_dict.get(
            v.get("categoria_vehiculo_id"), "Vehículo")
        vehiculos_por_cliente.setdefault(cid, []).append(v)

    for c in clientes:
        c["vehiculos_registrados"] = vehiculos_por_cliente.get(c.get("id"), [])

    return render(
        request,
        "clientes.html",
        {
            "clientes": clientes,
            "vehiculos": vehiculos,
            "categorias": categorias,
        },
    )


@cajero_o_admin
def modulo_finanzas(request):
    ordenes_todas = obtener_json("/ordenes/")
    pagos_todos = obtener_json("/finanzas/pagos")
    comisiones_todas = obtener_json("/finanzas/comisiones")

    # Identificar qué órdenes ya tienen comisión distribuida para volverlas INMUTABLES
    ordenes_comisionadas_ids = {c.get("orden_id") for c in comisiones_todas}

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "registrar_pago":
                res_pago = requests.post(
                    f"{API_URL}/finanzas/pagos",
                    json={
                        "orden_id": int(request.POST.get("orden_id")),
                        "cajero_id": int(request.POST.get("cajero_id")),
                        "metodo_pago": request.POST.get("metodo_pago"),
                        "monto": float(request.POST.get("monto", 0)),
                    },
                    timeout=5,
                )
                if res_pago.status_code == 200:
                    messages.success(
                        request, "Cobro registrado exitosamente en caja.")
                else:
                    detalle = res_pago.json().get("detail", "No se pudo registrar el cobro.")
                    messages.error(request, detalle)

            elif accion == "asignar_operarios":
                orden_id_sel = int(request.POST.get("orden_id", 0))
                orden_sel = next(
                    (o for o in ordenes_todas if o.get("id") == orden_id_sel),
                    None,
                )

                # PROHIBIDO distribuir comisión antes de terminar el lavado
                if not orden_sel or orden_sel.get("estado", "Pendiente") in ["Pendiente", "En proceso"]:
                    messages.error(
                        request,
                        "Operación bloqueada: No se puede distribuir comisión a un vehículo cuyo lavado no ha sido Terminado.",
                    )
                    return redirect("finanzas")

                # CANDADO DE INMUTABILIDAD: Impedir que una comisión ya repartida se vuelva a editar
                if orden_id_sel in ordenes_comisionadas_ids:
                    messages.error(
                        request,
                        "Operación bloqueada: La comisión de esta orden ya fue distribuida y no puede modificarse.",
                    )
                    return redirect("finanzas")

                operarios_raw = request.POST.getlist("operarios_ids")
                operarios_ids = [int(x) for x in operarios_raw]
                if operarios_ids:
                    res_asig = requests.post(
                        f"{API_URL}/finanzas/asignar-operarios",
                        json={
                            "orden_id": orden_id_sel,
                            "operarios_ids": operarios_ids,
                            "comision_extra_manual": float(
                                request.POST.get("comision_extra_manual") or 0
                            ),
                        },
                        timeout=5,
                    )
                    if res_asig.status_code == 200:
                        messages.success(
                            request, "Comisión distribuida y cerrada en planilla."
                        )
        except Exception as e:
            print(f"Error en módulo de finanzas: {e}")
            messages.error(request, "Error de conexión con la API.")
        return redirect("finanzas")

    vehiculos = obtener_json("/vehiculos/")
    clientes = obtener_json("/clientes/")
    categorias = obtener_json("/categorias-vehiculos/")
    usuarios = obtener_json("/finanzas/usuarios")

    veh_dict = {v["id"]: v for v in vehiculos}
    cli_dict = {c["id"]: c for c in clientes}
    cat_dict = {c["id"]: c for c in categorias}
    usr_dict = {u["id"]: u["nombre_completo"] for u in usuarios}
    rol_por_usr = {u["id"]: u.get("rol_id") for u in usuarios}

    ordenes_pagadas_ids = {p.get("orden_id") for p in pagos_todos}
    pagos_hoy_orden_ids = {
        p.get("orden_id")
        for p in pagos_todos
        if es_fecha_de_hoy(p.get("fecha_pago", ""))
    }

    # Incluir todas las órdenes de hoy MÁS cualquier orden de días anteriores que siga abierta
    ordenes_turno = []
    for o in ordenes_todas:
        oid = o.get("id")
        es_de_hoy = es_fecha_de_hoy(o.get("created_at", ""))
        estado_o = o.get("estado", "Pendiente")
        sigue_abierta = (
            estado_o in ["Pendiente", "En proceso"]
            or (oid not in ordenes_pagadas_ids)
            or (oid not in ordenes_comisionadas_ids)
        )
        if es_de_hoy or sigue_abierta or (oid in pagos_hoy_orden_ids):
            ordenes_turno.append(o)

    ordenes_turno_ids = {o.get("id") for o in ordenes_turno}
    ordenes_hoy_ids = {
        o.get("id")
        for o in ordenes_todas
        if es_fecha_de_hoy(o.get("created_at", ""))
    }

    ordenes_info = []
    for o in ordenes_turno:
        oid = o.get("id")
        es_de_hoy = oid in ordenes_hoy_ids
        v = veh_dict.get(o.get("vehiculo_id"), {})
        c = cli_dict.get(v.get("cliente_id"), {})
        cat = cat_dict.get(v.get("categoria_vehiculo_id"), {})
        estado_actual = o.get("estado", "Pendiente")
        cobrable = estado_actual not in ["Pendiente", "En proceso"]
        ya_pagada = oid in ordenes_pagadas_ids
        ya_comisionada = oid in ordenes_comisionadas_ids

        ordenes_info.append({
            "id": oid,
            "id_formateado": f"{oid or 0:08d}",
            "vehiculo_info": f"{v.get('placa', 'S/P')} ({v.get('marca', '')} {v.get('modelo', '')})".strip(),
            "cliente_nombre": c.get("nombre_completo", "Cliente General"),
            "categoria_nombre": cat.get("nombre", "Sedán"),
            "comision_base": float(cat.get("comision_base", 2.50)),
            "total_pagar": float(o.get("total_pagar", 0)),
            "estado": estado_actual,
            "es_rezagada": not es_de_hoy,
            "cobrable": cobrable,
            "comisionable": cobrable and (not ya_comisionada),
            "ya_pagada": ya_pagada,
            "ya_comisionada": ya_comisionada,
        })

    ord_info_dict = {oi["id"]: oi for oi in ordenes_info}

    pagos_lista = []
    total_ingresos = 0.0
    total_efectivo = 0.0
    total_digital = 0.0

    for p in pagos_todos:
        if p.get("orden_id") not in ordenes_hoy_ids and not es_fecha_de_hoy(p.get("fecha_pago", "")):
            continue
        monto = float(p.get("monto", 0))
        metodo = p.get("metodo_pago", "Efectivo")
        total_ingresos += monto
        if metodo == "Efectivo":
            total_efectivo += monto
        else:
            total_digital += monto

        oi = ord_info_dict.get(p.get("orden_id"), {})
        fecha_raw = fecha_iso_a_sv(
            p.get("fecha_pago", "")).strftime("%Y-%m-%d %H:%M")
        pagos_lista.append({
            "id": p.get("id"),
            "orden_formateada": f"{p.get('orden_id', 0):08d}",
            "vehiculo_info": oi.get("vehiculo_info", "Vehículo"),
            "cliente_nombre": oi.get("cliente_nombre", "Cliente General"),
            "categoria_nombre": oi.get("categoria_nombre", "Servicio de Lavado"),
            "metodo_pago": metodo,
            "cajero_nombre": usr_dict.get(p.get("cajero_id"), "Cajero"),
            "monto": monto,
            "fecha_pago": fecha_raw or "Hoy",
        })

    detalle_comisiones = []
    acumulado_por_op = {}
    conteo_por_op = {}
    total_comisiones = 0.0

    for com in comisiones_todas:
        # Mostrar las comisiones de las órdenes del turno actual y de rol Operario (rol_id == 3)
        if com.get("orden_id") not in ordenes_turno_ids:
            continue
        uid = com.get("usuario_id")
        if rol_por_usr.get(uid) != 3:
            continue

        monto_com = float(com.get("comision_calculada", 0))
        total_comisiones += monto_com
        acumulado_por_op[uid] = acumulado_por_op.get(uid, 0.0) + monto_com
        conteo_por_op[uid] = conteo_por_op.get(uid, 0) + 1

        oi = ord_info_dict.get(com.get("orden_id"), {})
        detalle_comisiones.append({
            "orden_formateada": f"{com.get('orden_id', 0):08d}",
            "vehiculo_categoria": f"{oi.get('vehiculo_info', '')} - {oi.get('categoria_nombre', '')}",
            "operario_nombre": usr_dict.get(uid, "Operario"),
            "comision_calculada": monto_com,
        })

    # En la tabla de planilla solo aparecen los Operarios (rol_id == 3)
    resumen_planilla = []
    for u in usuarios:
        uid = u["id"]
        if u.get("rol_id") == 3:
            resumen_planilla.append({
                "nombre": u["nombre_completo"],
                "cantidad_lavados": conteo_por_op.get(uid, 0),
                "total_comision": acumulado_por_op.get(uid, 0.0),
            })

    # Listas separadas por rol para los modales
    operarios_activos = [u for u in usuarios if u.get(
        "rol_id") == 3 and u.get("estado") == 1]
    personal_caja = [u for u in usuarios if u.get(
        "rol_id") in [1, 2] and u.get("estado") == 1]

    conteo_por_categoria = {}
    for oi in ordenes_info:
        if oi["estado"] not in ["Pendiente"]:
            cat_nom = oi["categoria_nombre"]
            conteo_por_categoria[cat_nom] = conteo_por_categoria.get(
                cat_nom, 0) + 1

    resumen_categorias = [
        {"categoria": k, "cantidad": v} for k, v in conteo_por_categoria.items()
    ]

    ordenes_en_patio = sum(
        1 for oi in ordenes_info if oi["estado"] in ["Pendiente", "En proceso"]
    )
    ordenes_listas_para_cobrar = sum(
        1 for oi in ordenes_info if oi["cobrable"] and not oi["ya_pagada"]
    )
    comisiones_sin_distribuir = sum(
        1 for oi in ordenes_info if oi["cobrable"] and not oi["ya_comisionada"]
    )
    comisiones_pendientes_totales = sum(
        1 for oi in ordenes_info if not oi["ya_comisionada"]
    )

    contexto = {
        "ordenes": ordenes_info,
        "ordenes_en_patio": ordenes_en_patio,
        "ordenes_listas_para_cobrar": ordenes_listas_para_cobrar,
        "comisiones_sin_distribuir": comisiones_sin_distribuir,
        "comisiones_pendientes_totales": comisiones_pendientes_totales,
        "usuarios": personal_caja,
        "operarios": operarios_activos,
        "pagos": pagos_lista,
        "cantidad_pagos": len(pagos_lista),
        "total_ingresos": total_ingresos,
        "total_efectivo": total_efectivo,
        "total_digital": total_digital,
        "total_comisiones": total_comisiones,
        "resumen_planilla": resumen_planilla,
        "detalle_comisiones": detalle_comisiones,
        "resumen_categorias": resumen_categorias,
    }
    return render(request, "finanzas.html", contexto)


@solo_administrador
def modulo_usuarios(request):
    usuarios = obtener_json("/finanzas/usuarios")
    roles = obtener_json("/finanzas/roles")
    mi_id = int(request.session.get("usuario_id", 0))
    soy_admin_principal = (mi_id == 1)

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear_usuario":
                rol_nuevo = int(request.POST.get("rol_id", 3))
                if rol_nuevo == 1 and not soy_admin_principal:
                    messages.error(
                        request,
                        "Operación bloqueada: Solo el Administrador Principal puede crear cuentas con rol de Administrador.",
                    )
                    return redirect("usuarios")

                res = requests.post(
                    f"{API_URL}/finanzas/usuarios",
                    json={
                        "rol_id": rol_nuevo,
                        "nombre_completo": (request.POST.get("nombre_completo") or "").strip(),
                        "correo": (request.POST.get("correo") or "").strip().lower(),
                        "password": request.POST.get("password", "sprintwash123"),
                    },
                    timeout=5,
                )
                if res.status_code == 200:
                    messages.success(
                        request, "Empleado registrado correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo crear el usuario.")
                    except Exception:
                        detalle = "No se pudo crear el usuario."
                    messages.error(request, detalle)

            elif accion == "editar_usuario":
                uid = int(request.POST.get("usuario_id", 0))
                rol_id = int(request.POST.get("rol_id", 3))
                nombre_completo = (request.POST.get(
                    "nombre_completo") or "").strip()
                correo = (request.POST.get("correo") or "").strip().lower()
                password_nueva = (request.POST.get("password") or "").strip()

                usuario_objetivo = next(
                    (u for u in usuarios if u["id"] == uid), None
                )

                if not soy_admin_principal:
                    if uid == 1 or (
                        usuario_objetivo
                        and usuario_objetivo.get("rol_id") == 1
                        and uid != mi_id
                    ):
                        messages.error(
                            request,
                            "Operación bloqueada: Solo el Administrador Principal puede modificar datos o contraseñas de otros Administradores.",
                        )
                        return redirect("usuarios")
                    if rol_id == 1 and uid != mi_id:
                        messages.error(
                            request,
                            "Operación bloqueada: Solo el Administrador Principal puede otorgar el rol de Administrador.",
                        )
                        return redirect("usuarios")

                if uid == 1 and rol_id != 1:
                    messages.error(
                        request,
                        "Operación bloqueada: El Administrador Principal debe mantener el rol de Encargado General.",
                    )
                    return redirect("usuarios")

                payload = {
                    "rol_id": rol_id,
                    "nombre_completo": nombre_completo,
                    "correo": correo,
                }
                if password_nueva:
                    payload["password"] = password_nueva

                res = requests.patch(
                    f"{API_URL}/finanzas/usuarios/{uid}",
                    json=payload,
                    timeout=5,
                )
                if res.status_code == 200:
                    if uid == request.session.get("usuario_id"):
                        request.session["usuario_nombre"] = nombre_completo
                    messages.success(
                        request, "Datos del empleado actualizados correctamente.")
                else:
                    try:
                        detalle = res.json().get("detail", "No se pudo actualizar el usuario.")
                    except Exception:
                        detalle = "No se pudo actualizar el usuario."
                    messages.error(request, detalle)

            elif accion == "alternar_estado":
                uid = int(request.POST.get("usuario_id", 0))
                usuario_objetivo = next(
                    (u for u in usuarios if u["id"] == uid), None)

                # 1. Evitar que el usuario en sesión se desactive a sí mismo
                if uid == mi_id:
                    messages.error(
                        request, "Operación bloqueada: No puedes desactivar tu propia cuenta en sesión activa.")
                    return redirect("usuarios")

                # 1.B Proteger la cuenta del Administrador Principal (ID 1)
                if uid == 1:
                    messages.error(
                        request, "Operación bloqueada: La cuenta del Administrador Principal no puede ser desactivada.")
                    return redirect("usuarios")

                # 1.C Solo el Administrador Principal puede activar/desactivar a otros Administradores
                if usuario_objetivo and usuario_objetivo.get("rol_id") == 1 and not soy_admin_principal:
                    messages.error(
                        request,
                        "Operación bloqueada: Solo el Administrador Principal puede activar o desactivar a otros Administradores.",
                    )
                    return redirect("usuarios")

                if usuario_objetivo and usuario_objetivo.get("estado") == 1:
                    # 2. Garantizar que siempre quede al menos 1 Administrador activo
                    if usuario_objetivo.get("rol_id") == 1:
                        admins_activos = sum(1 for u in usuarios if u.get(
                            "rol_id") == 1 and u.get("estado") == 1)
                        if admins_activos <= 1:
                            messages.error(
                                request, "Operación bloqueada: Debe existir al menos un Administrador activo en el sistema.")
                            return redirect("usuarios")

                    # 3. Evitar desactivar operarios asignados a una orden actualmente "En proceso"
                    ordenes_en_proceso = {
                        o["id"] for o in obtener_json("/ordenes/") if o.get("estado") == "En proceso"
                    }
                    comisiones = obtener_json("/finanzas/comisiones")
                    en_uso = any(
                        c.get("usuario_id") == uid and c.get(
                            "orden_id") in ordenes_en_proceso
                        for c in comisiones
                    )
                    if en_uso:
                        messages.error(
                            request, "No se puede desactivar: El usuario tiene una orden en proceso en este momento.")
                        return redirect("usuarios")

                requests.patch(
                    f"{API_URL}/finanzas/usuarios/{uid}/estado", timeout=5)
                messages.success(request, "Estado del usuario actualizado.")
        except Exception as e:
            print(f"Error en módulo de usuarios: {e}")
        return redirect("usuarios")

    roles_dict = {r["id"]: ("ADMINISTRADOR" if r["id"]
                            == 1 else r["nombre"]) for r in roles}
    for u in usuarios:
        uid = u.get("id")
        rol_u = u.get("rol_id")
        u["rol_nombre"] = roles_dict.get(rol_u, "OPERARIO / SUPERVISOR")
        u["puede_editar"] = (
            soy_admin_principal or uid == mi_id or rol_u in [2, 3]
        )
        u["puede_alternar_estado"] = (
            uid != mi_id
            and uid != 1
            and (soy_admin_principal or rol_u in [2, 3])
        )

    return render(
        request,
        "usuarios.html",
        {
            "usuarios": usuarios,
            "soy_admin_principal": soy_admin_principal,
        },
    )


@login_requerido
def modulo_inventario(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear_insumo":
                requests.post(
                    f"{API_URL}/inventario/",
                    json={
                        "codigo_sku": request.POST.get("codigo_sku"),
                        "nombre_producto": request.POST.get("nombre_producto"),
                        "cantidad_actual": int(request.POST.get("cantidad_actual", 0)),
                        "stock_minimo": int(request.POST.get("stock_minimo", 0)),
                        "unidad_medida": request.POST.get("unidad_medida", "Unidad"),
                        "costo_unitario": float(request.POST.get("costo_unitario", 0)),
                        "proveedor": request.POST.get("proveedor", "")
                    },
                    timeout=5,
                )
            elif accion == "eliminar_insumo":
                insumo_id = request.POST.get("insumo_id")
                requests.delete(f"{API_URL}/inventario/{insumo_id}", timeout=5)
            elif accion == "registrar_movimiento":
                requests.post(
                    f"{API_URL}/inventario/movimiento",
                    json={
                        "inventario_id": int(request.POST.get("inventario_id")),
                        "usuario_id": int(request.session.get("usuario_id", 1)),
                        "tipo_movimiento": request.POST.get("tipo_movimiento"),
                        "cantidad": int(request.POST.get("cantidad", 1)),
                        "descripcion": (
                            request.POST.get("descripcion")
                            or "Movimiento desde panel web"
                        ),
                    },
                    timeout=5,
                )
        except Exception as e:
            print(f"Error en inventario: {e}")
        return redirect("inventario")

    insumos = obtener_json("/inventario/")
    movimientos = obtener_json("/inventario/movimientos")

    insumos_dict = {i["id"]: i["nombre_producto"] for i in insumos}
    unidades_dict = {i["id"]: i["unidad_medida"] for i in insumos}

    total_retirados = sum(
        int(m.get("cantidad", 0))
        for m in movimientos
        if m.get("tipo_movimiento") == "Salida"
    )
    for m in movimientos:
        m["producto_nombre"] = insumos_dict.get(
            m.get("inventario_id"), "Insumo")
        m["unidad"] = unidades_dict.get(m.get("inventario_id"), "Unidades")
        m["fecha_corta"] = (
            fecha_iso_a_sv(m.get("fecha_movimiento", "")
                           ).strftime("%Y-%m-%d %H:%M")
        )

    total_insumos = len(insumos)
    valor_inventario = sum(
        float(i.get("costo_unitario", 0)) * int(i.get("cantidad_actual", 0))
        for i in insumos
    )
    alertas_criticas = sum(
        1
        for i in insumos
        if int(i.get("cantidad_actual", 0)) <= int(i.get("stock_minimo", 0))
    )

    contexto = {
        "insumos": insumos,
        "total_insumos": total_insumos,
        "valor_inventario": valor_inventario,
        "alertas_criticas": alertas_criticas,
        "total_retirados": total_retirados,
        "movimientos": sorted(
            movimientos, key=lambda x: x.get("id", 0), reverse=True
        )[:10],
    }
    return render(request, "inventario.html", contexto)
