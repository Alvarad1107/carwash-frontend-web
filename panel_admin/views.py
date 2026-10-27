from django.shortcuts import render, redirect
import requests

API_URL = "http://127.0.0.1:8000"


def obtener_json(endpoint):
    """Función auxiliar segura para consultar la API sin que un error detenga el resto."""
    try:
        res = requests.get(f"{API_URL}{endpoint}", timeout=4)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error consultando {endpoint}: {e}")
    return []


def dashboard_prueba(request):
    return render(request, "base.html")


def login_prueba(request):
    if request.method == "POST":
        return redirect("monitor")
    return render(request, "login.html")


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
            "servicio_total": f"Orden de Lavado (${float(o.get('total_pagar', 0)):.2f})",
            "tiempo": tiempo_texto,
            "estado": estado,
        })

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
                requests.patch(
                    f"{API_URL}/ordenes/{orden_id}/estado",
                    json={"estado": nuevo_estado},
                    timeout=10,
                )
            except Exception as e:
                print(
                    f"Error actualizando el estado de la orden {orden_id}: {e}")
    return redirect("monitor")


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
                placa = request.POST.get("placa", "").strip().upper()
                marca = request.POST.get("marca", "").strip()
                modelo = request.POST.get("modelo", "").strip()
                subtotal = float(request.POST.get("subtotal", 0))
                impuestos = float(request.POST.get("impuestos", 0))
                total_pagar = float(request.POST.get("total_pagar", 0))

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

                # Crear la orden en estado Pendiente y asignarle los montos calculados
                if vehiculo_id:
                    res_ord = requests.post(
                        f"{API_URL}/ordenes/",
                        json={
                            "vehiculo_id": vehiculo_id,
                            "bahia_id": 1,
                            "estado": "Pendiente",
                        },
                        timeout=5,
                    )
                    if res_ord.status_code == 200:
                        orden_creada = res_ord.json()
                        orden_id = orden_creada.get("id")
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

    # Peticiones GET para alimentar la pantalla de Punto de Venta

    clientes = obtener_json("/clientes/")
    categorias = obtener_json("/categorias-vehiculos/")
    adicionales = obtener_json("/servicios/adicionales")
    matriz = obtener_json("/servicios/matriz-precios")

    if not categorias:
        categorias = [
            {"id": 1, "nombre": "Sedán", "comision_base": 2.50},
            {"id": 2, "nombre": "Pick Up", "comision_base": 3.00},
            {"id": 3, "nombre": "Carros Medianos", "comision_base": 2.50},
            {"id": 4, "nombre": "Carros Grandes", "comision_base": 3.00},
        ]
    if not adicionales:
        adicionales = [
            {"id": 1, "nombre": "Lavado de Motor",
                "precio_fijo": 15.00, "comision_extra": 2.00},
        ]

    # Mapear el precio base real según el ID de cada categoría desde la matriz
    precios_respaldo = {1: 4.00, 2: 8.00, 3: 6.00, 4: 8.00, 5: 10.00}
    precios_por_categoria = {
        m.get("categoria_vehiculo_id"): float(m.get("precio_base", 0))
        for m in matriz
    }

    for cat in categorias:
        cid = cat.get("id")
        cat["precio_base"] = precios_por_categoria.get(
            cid, precios_respaldo.get(cid, 5.00))

    contexto = {
        "clientes": clientes,
        "categorias": categorias[:4],  # Mostramos las 4 tarjetas principales
        "adicionales": adicionales,
    }
    return render(request, "registro_orden.html", contexto)


def modulo_finanzas(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "registrar_pago":
                requests.post(
                    f"{API_URL}/finanzas/pagos",
                    json={
                        "orden_id": int(request.POST.get("orden_id")),
                        "cajero_id": int(request.POST.get("cajero_id")),
                        "metodo_pago": request.POST.get("metodo_pago"),
                        "monto": float(request.POST.get("monto", 0)),
                    },
                    timeout=5,
                )
            elif accion == "asignar_operarios":
                operarios_raw = request.POST.getlist("operarios_ids")
                operarios_ids = [int(x) for x in operarios_raw]
                if operarios_ids:
                    requests.post(
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
        except Exception as e:
            print(f"Error en módulo de finanzas: {e}")
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
    ord_dict = {o["id"]: o for o in ordenes}

    ordenes_info = []
    for o in ordenes:
        v = veh_dict.get(o.get("vehiculo_id"), {})
        c = cli_dict.get(v.get("cliente_id"), {})
        cat = cat_dict.get(v.get("categoria_vehiculo_id"), {})
        ordenes_info.append({
            "id": o.get("id"),
            "id_formateado": f"{o.get('id', 0):08d}",
            "vehiculo_info": f"{v.get('placa', 'S/P')} ({v.get('marca', '')} {v.get('modelo', '')})".strip(),
            "cliente_nombre": c.get("nombre_completo", "Cliente General"),
            "categoria_nombre": cat.get("nombre", "Sedán"),
            "comision_base": float(cat.get("comision_base", 2.50)),
            "total_pagar": float(o.get("total_pagar", 0)),
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
        pagos_lista.append({
            "orden_formateada": f"{p.get('orden_id', 0):08d}",
            "vehiculo_info": oi.get("vehiculo_info", "Vehículo"),
            "cliente_nombre": oi.get("cliente_nombre", "Cliente"),
            "metodo_pago": metodo,
            "cajero_nombre": usr_dict.get(p.get("cajero_id"), "Cajero"),
            "monto": monto,
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
    }
    return render(request, "finanzas.html", contexto)


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
