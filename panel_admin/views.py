from django.shortcuts import redirect
from functools import wraps
from django.contrib import messages
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from datetime import datetime, timedelta, timezone
import requests

API_URL = "http://127.0.0.1:8000"


def login_requerido(view_func):
    """Evita que entren a cualquier módulo si no han iniciado sesión."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            messages.error(request, "Por favor inicie sesión para continuar.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return wrapper


def solo_administrador(view_func):
    """Restringe el acceso exclusivamente al rol Administrador (Encargado General)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        if request.session.get("rol_id") != 1:
            messages.error(
                request, "Acceso denegado. Se requieren privilegios de Administrador."
            )
            return redirect("monitor")
        return view_func(request, *args, **kwargs)

    return wrapper


def cajero_o_admin(view_func):
    """Permite acceso a Administradores y Cajeros (bloquea a Operarios/Supervisores en áreas financieras)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        if request.session.get("rol_id") == 3:  # Operario / Supervisor
            messages.error(
                request,
                "Acceso restringido. Esta área es exclusiva para Caja y Administración.",
            )
            return redirect("monitor")
        return view_func(request, *args, **kwargs)

    return wrapper


def es_fecha_de_hoy(fecha_str):
    """Verifica si una fecha ISO pertenece al día de hoy (considerando hora local y UTC)."""
    hoy_local = datetime.now().date()
    hoy_utc = datetime.now(timezone.utc).date()
    if not fecha_str:
        return True
    try:
        fecha_orden = datetime.fromisoformat(
            str(fecha_str).replace("Z", "")).date()
        return fecha_orden in (hoy_local, hoy_utc)
    except Exception:
        return True


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
    hoy = datetime.now().date()
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

        fecha_orden = hoy
        if fecha_str:
            try:
                fecha_orden = datetime.fromisoformat(
                    str(fecha_str).replace("Z", "")
                ).date()
            except Exception:
                pass

        de_hoy = es_fecha_de_hoy(fecha_str)

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
            # Consumimos directamente el endpoint oficial de autenticación en la API
            res_auth = requests.post(
                f"{API_URL}/auth/login",
                json={"correo": correo, "password": password},
                timeout=5,
            )

            if res_auth.status_code == 200:
                datos = res_auth.json()
                rol_nombre = datos.get("rol", "SIN ROL")
                rol_upper = rol_nombre.upper()

                # Asignar el nivel de acceso según el rol devuelto por MySQL
                if "ENCARGADO" in rol_upper or "ADMIN" in rol_upper:
                    rol_id = 1
                elif "CAJERO" in rol_upper:
                    rol_id = 2
                else:
                    rol_id = 3

                # Guardar los datos provenientes de la BD y el token JWT en la sesión
                request.session["access_token"] = datos.get("access_token")
                request.session["usuario_id"] = datos.get("usuario_id")
                request.session["usuario_nombre"] = datos.get("nombre")
                request.session["rol_id"] = rol_id
                request.session["rol_nombre"] = rol_nombre

                return redirect("dashboard" if rol_id in [1, 2] else "monitor")
            else:
                # Muestra el mensaje exacto de la API (401 credenciales inválidas o 403 inactivo)
                detalle = res_auth.json().get("detail", "Correo o contraseña incorrectos.")
                messages.error(request, detalle)

        except Exception:
            messages.error(
                request, "Error al conectar con el servidor de autenticación.")

    return render(request, "login.html")


@login_requerido
def monitor_operaciones(request):
    ordenes_lista = []
    conteo_pendientes = 0
    conteo_en_proceso = 0
    conteo_terminados = 0

    ordenes = obtener_json("/ordenes/")
    vehiculos = obtener_json("/vehiculos/")
    clientes = obtener_json("/clientes/")

    vehiculos_dict = {v["id"]: v for v in vehiculos}
    clientes_dict = {c["id"]: c for c in clientes}

    for o in ordenes:
        # Filtrar para mostrar únicamente las órdenes del día actual
        if not es_fecha_de_hoy(o.get("created_at", "")):
            continue

        estado = o.get("estado", "Pendiente")
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
            "vehiculo_info": f"{placa} / {detalle_auto}" if detalle_auto else placa,
            "servicio_total": (
                f"Orden de Lavado (${float(o.get('total_pagar', 0)):.2f})"
            ),
            "tiempo": tiempo_texto,
            "estado": estado,
        })

    contexto = {
        "ordenes": sorted(
            ordenes_lista, key=lambda x: x.get("id", 0), reverse=True
        ),
        "pendientes": conteo_pendientes,
        "en_proceso": conteo_en_proceso,
        "terminados": conteo_terminados,
    }
    return render(request, "monitor.html", contexto)


@login_requerido
def cambiar_estado_orden(request, orden_id):
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        if nuevo_estado:
            try:
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
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            # 1. Acción para crear un cliente nuevo desde Caja
            if accion == "crear_cliente":
                requests.post(
                    f"{API_URL}/clientes/",
                    json={
                        "nombre_completo": request.POST.get("nombre_completo"),
                        "telefono": request.POST.get("telefono") or None,
                        "correo": request.POST.get("correo") or None,
                    },
                    timeout=5,
                )
                return redirect("caja")

            # 2. Acción para generar la orden completa y mandarla al Monitor
            elif accion == "generar_orden":
                cliente_id = int(request.POST.get("cliente_id", 1))
                categoria_id = int(request.POST.get(
                    "categoria_vehiculo_id", 1))
                bahia_id = int(request.POST.get("bahia_id", 1))
                placa = request.POST.get("placa", "").strip().upper()
                marca = request.POST.get("marca", "").strip()
                modelo = request.POST.get("modelo", "").strip()

                subtotal = float(request.POST.get("subtotal", 0))
                impuestos = float(request.POST.get("impuestos", 0))
                total_pagar = float(request.POST.get("total_pagar", 0))
                extras_ids = request.POST.getlist("extras_ids")

                # Verificar si la placa ya existe en MySQL o crear el vehículo
                vehiculos_existentes = obtener_json("/vehiculos/")
                vehiculo_id = None
                for v in vehiculos_existentes:
                    if v.get("placa", "").upper() == placa:
                        vehiculo_id = v.get("id")
                        break

                if not vehiculo_id:
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
                return redirect("monitor")
        except Exception as e:
            print(f"Error procesando orden en caja: {e}")
            return redirect("caja")

    # Inicializar catálogos base si la BD recién se creó
    obtener_json("/finanzas/usuarios")

    # Peticiones GET para alimentar la pantalla de Punto de Venta
    clientes = obtener_json("/clientes/")
    categorias = obtener_json("/categorias-vehiculos/")
    adicionales = obtener_json("/servicios/adicionales")
    matriz = obtener_json("/servicios/matriz-precios")
    bahias = obtener_json("/bahias/")

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
        "categorias": categorias[:5],
        "adicionales": adicionales,
        "bahias": bahias,
    }
    return render(request, "registro_orden.html", contexto)


@cajero_o_admin
def modulo_finanzas(request):
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
                operarios_raw = request.POST.getlist("operarios_ids")
                operarios_ids = [int(x) for x in operarios_raw]
                if operarios_ids:
                    res_asig = requests.post(
                        f"{API_URL}/finanzas/asignar-operarios",
                        json={
                            "orden_id": int(request.POST.get("orden_id")),
                            "operarios_ids": operarios_ids,
                            "comision_extra_manual": float(
                                request.POST.get("comision_extra_manual") or 0
                            ),
                        },
                        timeout=5,
                    )
                    if res_asig.status_code == 200:
                        messages.success(
                            request, "Comisión calculada y guardada en planilla.")
        except Exception as e:
            print(f"Error en módulo de finanzas: {e}")
            messages.error(request, "Error de conexión con la API.")
        return redirect("finanzas")

    ordenes = obtener_json("/ordenes/")
    vehiculos = obtener_json("/vehiculos/")
    clientes = obtener_json("/clientes/")
    categorias = obtener_json("/categorias-vehiculos/")
    usuarios = obtener_json("/finanzas/usuarios")
    pagos = obtener_json("/finanzas/pagos")
    comisiones = obtener_json("/finanzas/comisiones")

    veh_dict = {v["id"]: v for v in vehiculos}
    cli_dict = {c["id"]: c for c in clientes}
    cat_dict = {c["id"]: c for c in categorias}
    usr_dict = {u["id"]: u["nombre_completo"] for u in usuarios}
    ordenes_pagadas_ids = {p.get("orden_id") for p in pagos}

    ordenes_info = []
    for o in ordenes:
        v = veh_dict.get(o.get("vehiculo_id"), {})
        c = cli_dict.get(v.get("cliente_id"), {})
        cat = cat_dict.get(v.get("categoria_vehiculo_id"), {})
        estado_actual = o.get("estado", "Pendiente")

        ordenes_info.append({
            "id": o.get("id"),
            "id_formateado": f"{o.get('id', 0):08d}",
            "vehiculo_info": f"{v.get('placa', 'S/P')} ({v.get('marca', '')} {v.get('modelo', '')})".strip(),
            "cliente_nombre": c.get("nombre_completo", "Cliente General"),
            "categoria_nombre": cat.get("nombre", "Sedán"),
            "comision_base": float(cat.get("comision_base", 2.50)),
            "total_pagar": float(o.get("total_pagar", 0)),
            "estado": estado_actual,
            "cobrable": estado_actual not in ["Pendiente", "En proceso"],
            "ya_pagada": o.get("id") in ordenes_pagadas_ids,
        })

    ord_info_dict = {oi["id"]: oi for oi in ordenes_info}

    pagos_lista = []
    total_ingresos = 0.0
    total_efectivo = 0.0
    total_digital = 0.0

    for p in pagos:
        monto = float(p.get("monto", 0))
        metodo = p.get("metodo_pago", "Efectivo")
        total_ingresos += monto
        if metodo == "Efectivo":
            total_efectivo += monto
        else:
            total_digital += monto

        oi = ord_info_dict.get(p.get("orden_id"), {})
        fecha_raw = str(p.get("fecha_pago", ""))[:16].replace("T", " ")

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

    for com in comisiones:
        uid = com.get("usuario_id")
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

    resumen_planilla = []
    for u in usuarios:
        uid = u["id"]
        if uid in acumulado_por_op or u.get("rol_id") == 3:
            resumen_planilla.append({
                "nombre": u["nombre_completo"],
                "cantidad_lavados": conteo_por_op.get(uid, 0),
                "total_comision": acumulado_por_op.get(uid, 0.0),
            })

# Conteo de vehículos lavados segmentados por categoría (Sección 4.7)
    conteo_por_categoria = {}
    for oi in ordenes_info:
        if oi["estado"] not in ["Pendiente"]:
            cat_nom = oi["categoria_nombre"]
            conteo_por_categoria[cat_nom] = conteo_por_categoria.get(
                cat_nom, 0) + 1

    resumen_categorias = [
        {"categoria": k, "cantidad": v} for k, v in conteo_por_categoria.items()
    ]

    contexto = {
        "ordenes": ordenes_info,
        "usuarios": usuarios,
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
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear_usuario":
                requests.post(
                    f"{API_URL}/finanzas/usuarios",
                    json={
                        "rol_id": int(request.POST.get("rol_id", 3)),
                        "nombre_completo": request.POST.get("nombre_completo"),
                        "correo": request.POST.get("correo"),
                        "password": request.POST.get("password", "sprintwash123"),
                    },
                    timeout=5,
                )
            elif accion == "alternar_estado":
                uid = request.POST.get("usuario_id")
                requests.patch(
                    f"{API_URL}/finanzas/usuarios/{uid}/estado", timeout=5)
        except Exception as e:
            print(f"Error en módulo de usuarios: {e}")
        return redirect("usuarios")

    usuarios = obtener_json("/finanzas/usuarios")
    roles = obtener_json("/finanzas/roles")
    roles_dict = {r["id"]: r["nombre"] for r in roles}

    for u in usuarios:
        u["rol_nombre"] = roles_dict.get(
            u.get("rol_id"), "OPERARIO / SUPERVISOR")

    return render(request, "usuarios.html", {"usuarios": usuarios})


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
            str(m.get("fecha_movimiento", ""))[:16].replace("T", " ")
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
