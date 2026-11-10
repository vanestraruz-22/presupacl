"""cotizaciones_creacion: crear una cotización para un cliente (RF-07, HU-07).

Une los conceptos elegidos (SYSCOM o manuales, de los ocho tipos de RF-07, que
pueden repetirse), valida (validador_cotizacion), calcula
(calculadora_cotizacion) y pide guardar todo en una transacción. Copia los
datos del cliente y de ACL (snapshots) para que la cotización no cambie después.
"""

from datetime import date, timedelta

from proyecto.cotizaciones import calculadora_cotizacion as calc
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion, validar_partidas
from proyecto.infraestructura import almacenamiento_datos

MONEDA = "MXN"  # SUPUESTO D02 — validar con ACL.

TIPOS = {
    "SYSCOM": "Producto SYSCOM",
    "manual": "Producto o material manual",
    "mano_obra": "Mano de obra",
    "viaticos": "Viáticos",
    "insumos": "Insumos de instalación",
    "programacion": "Programación",
    "equipo_seguridad": "Equipo de seguridad",
    "dia_festivo": "Cargo por domingo o día festivo",
}


def preparar_partidas(conexion, renglones, moneda=MONEDA):
    """Convierte renglones capturados en partidas listas para guardar.

    renglones: [{"id_concepto", "cantidad" (texto o milésimas int), "precio" (texto opcional)}].
    Sin "precio" se usa el precio vigente del catálogo. Lanza ErrorCotizacion con
    todos los errores por renglón; ningún renglón inválido se incorpora (CA-16).
    """
    conceptos = almacenamiento_datos.obtener_conceptos(
        conexion, [r.get("id_concepto") for r in renglones if r.get("id_concepto")]
    )
    partidas, errores = [], []
    for numero, renglon in enumerate(renglones, start=1):
        concepto = conceptos.get(renglon.get("id_concepto"))
        try:
            if concepto is None:
                raise calc.ErrorCalculo("el concepto no existe en el catálogo")
            if concepto["moneda"] != moneda:
                raise calc.ErrorCalculo(f"el concepto está en {concepto['moneda']} y la cotización en {moneda}")
            cantidad = renglon.get("cantidad")
            cantidad = cantidad if isinstance(cantidad, int) and not isinstance(cantidad, bool) \
                else calc.texto_a_milesimas(cantidad)
            if cantidad <= 0:
                raise calc.ErrorCalculo("Cantidad: debe ser mayor que cero.")
            precio = renglon.get("precio")
            if precio is None or (isinstance(precio, str) and not precio.strip()):
                precio = concepto["precio_unitario_centavos"]
            elif not isinstance(precio, int) or isinstance(precio, bool):
                precio = calc.texto_a_centavos(precio)
            partidas.append({
                "id_concepto": concepto["id_concepto"],
                "descripcion_snapshot": concepto["descripcion"],
                "tipo_snapshot": concepto["tipo"],
                "unidad_snapshot": concepto["unidad"],
                "cantidad_milesimas": cantidad,
                "precio_unitario_centavos": precio,
                "importe_centavos": calc.importe_centavos(cantidad, precio),
            })
        except calc.ErrorCalculo as error:
            errores.append(f"Renglón {numero}: {error}")
    if errores:
        raise ErrorCotizacion(" ".join(errores) + " No se guardó.")
    return partidas


def totales(partidas, metodo_utilidad, utilidad_tasa, iva_tasa):
    """Totales de la cotización con la calculadora; ErrorCalculo se informa como ErrorCotizacion."""
    try:
        resultado = calc.calcular(partidas, metodo_utilidad, utilidad_tasa, iva_tasa)
    except calc.ErrorCalculo as error:
        raise ErrorCotizacion(f"{error} No se guardó.") from error
    return {k: v for k, v in resultado.items() if k != "importes"}


def validar_direccion(cliente, id_direccion):
    """Regresa el texto de la dirección elegida o None; error si no es del cliente."""
    if id_direccion in (None, ""):
        return None
    for direccion in cliente["direcciones"]:
        if direccion["id_direccion"] == int(id_direccion):
            return direccion["direccion"]
    raise ErrorCotizacion("La dirección elegida no pertenece al cliente. No se guardó.")


def crear_cotizacion(conexion, id_cliente, renglones, id_direccion=None, id_origen=None):
    """Crea una cotización pendiente y regresa (id_cotizacion, folio) (CA-14, CA-44).

    Errores (ErrorCotizacion, nada se guarda): cliente inexistente, falta la
    configuración de ACL, dirección ajena, sin conceptos (RF-20) o renglón inválido.
    """
    cliente = almacenamiento_datos.obtener_cliente(conexion, id_cliente)
    if cliente is None:
        raise ErrorCotizacion(f"No existe el cliente {id_cliente}. No se guardó.")
    config = almacenamiento_datos.obtener_configuracion(conexion)
    if config is None:
        raise ErrorCotizacion("Primero capture los datos de ACL en Configuración. No se guardó.")
    direccion = validar_direccion(cliente, id_direccion)

    if not renglones:
        validar_partidas([])
    partidas = preparar_partidas(conexion, renglones)
    validar_partidas(partidas)
    resultado = totales(partidas, config["metodo_utilidad"], config["utilidad_tasa_default"],
                        config["iva_tasa_default"])

    cabecera = {
        "id_cliente": cliente["id_cliente"],
        "id_direccion": int(id_direccion) if direccion else None,
        "id_origen": id_origen,
        "estatus": "pendiente",
        "moneda": MONEDA,
        "cliente_nombre_snapshot": cliente["nombre"],
        "cliente_telefono_snapshot": cliente["telefono"],
        "direccion_snapshot": direccion,
        "acl_nombre_snapshot": config["nombre_comercial"],
        "acl_telefono_snapshot": config["telefono"],
        "acl_correo_snapshot": config["correo"],
        "acl_logo_ruta_snapshot": config["logo_ruta"],
        "condiciones": config["condiciones_default"],
        "vigencia_hasta": (date.today() + timedelta(days=config["vigencia_dias_default"])).isoformat(),
        "metodo_utilidad": config["metodo_utilidad"],
        "utilidad_tasa": config["utilidad_tasa_default"],
        "iva_tasa": config["iva_tasa_default"],
        **resultado,
    }
    try:
        return almacenamiento_datos.crear_cotizacion(conexion, cabecera, partidas)
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        raise ErrorCotizacion(str(error)) from error
