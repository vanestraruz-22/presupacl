"""cotizaciones_duplicado: nueva cotización pendiente a partir de una cerrada (RF-15, HU-13.1).

Copia conceptos y cantidades, pero toma el precio VIGENTE del catálogo (no el
de la original) y deja la original intacta. Permite cambiar cliente y dirección
(CA-57). Señala los conceptos que conviene revisar (CA-67).

SUPUESTO D03 — validar con ACL: un cambio de precio "significativo" es de más
del 10 % (hacia arriba o hacia abajo); un producto SYSCOM con existencia 0 se
señala como agotado.
"""

from decimal import Decimal

from proyecto.cotizaciones import cotizaciones_creacion
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos

UMBRAL_CAMBIO = Decimal("0.10")


def duplicar(conexion, id_origen, id_cliente=None, id_direccion=None):
    """Regresa (id_nueva, folio). Error si el origen no existe (CA-66) o sigue pendiente."""
    origen = almacenamiento_datos.obtener_cotizacion(conexion, id_origen)
    if origen is None:
        raise ErrorCotizacion(f"No existe la cotización {id_origen}; no se creó ninguna copia.")
    if origen["estatus"] == "pendiente":
        raise ErrorCotizacion("La cotización sigue pendiente: puede editarla directamente sin duplicarla.")

    id_cliente = int(id_cliente) if id_cliente not in (None, "") else origen["id_cliente"]
    if id_direccion in (None, ""):
        id_direccion = origen["id_direccion"] if id_cliente == origen["id_cliente"] else None
    renglones = [{"id_concepto": p["id_concepto"], "cantidad": p["cantidad_milesimas"]}  # sin precio: vigente
                 for p in origen["partidas"]]
    return cotizaciones_creacion.crear_cotizacion(conexion, id_cliente, renglones, id_direccion, id_origen=id_origen)


def conceptos_por_revisar(conexion, cotizacion):
    """{id_concepto: motivo} para un duplicado pendiente (CA-67). Vacío en otros casos."""
    if not cotizacion.get("id_origen") or cotizacion["estatus"] != "pendiente":
        return {}
    origen = almacenamiento_datos.obtener_cotizacion(conexion, cotizacion["id_origen"])
    if origen is None:
        return {}
    precios_origen = {p["id_concepto"]: p["precio_unitario_centavos"] for p in origen["partidas"]}
    catalogo = almacenamiento_datos.obtener_conceptos(conexion, [p["id_concepto"] for p in cotizacion["partidas"]])
    alertas = {}
    for partida in cotizacion["partidas"]:
        concepto = catalogo.get(partida["id_concepto"])
        anterior = precios_origen.get(partida["id_concepto"])
        motivos = []
        if concepto and concepto["origen"] == "syscom" and concepto["existencia"] == 0:
            motivos.append("SYSCOM lo reporta sin existencia")
        if anterior is not None and anterior != partida["precio_unitario_centavos"]:
            cambio = Decimal(partida["precio_unitario_centavos"] - anterior) / anterior if anterior else Decimal(1)
            if abs(cambio) > UMBRAL_CAMBIO:
                motivos.append(f"el precio cambió {cambio * 100:+.1f} % respecto a la cotización original")
        if motivos:
            alertas[partida["id_concepto"]] = "Revisar: " + "; ".join(motivos) + "."
    return alertas
