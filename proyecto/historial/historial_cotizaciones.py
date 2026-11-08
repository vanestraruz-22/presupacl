"""historial_cotizaciones: historial por cliente y filtros por estatus y fechas (RF-18, RF-19).

SUPUESTO D08 — validar: el rango de fechas es inclusivo en ambos extremos y
usa la fecha local de creación de la cotización.
"""

from datetime import date

from proyecto.cotizaciones.cotizaciones_estado import ESTATUS
from proyecto.infraestructura import almacenamiento_datos

SIN_COTIZACIONES = "Este cliente no tiene cotizaciones registradas."
SIN_RESULTADOS = "No hay cotizaciones con esos filtros."


class ErrorHistorial(Exception):
    pass


def historial_cliente(conexion, id_cliente):
    """{"cliente", "cotizaciones", "mensaje"} (CA-32, CA-33). Cliente inexistente: error (CA-60)."""
    cliente = almacenamiento_datos.obtener_cliente(conexion, id_cliente)
    if cliente is None:
        raise ErrorHistorial(f"El cliente {id_cliente} no existe.")
    cotizaciones = almacenamiento_datos.listar_cotizaciones(conexion, id_cliente=cliente["id_cliente"])
    return {"cliente": cliente, "cotizaciones": cotizaciones, "mensaje": None if cotizaciones else SIN_COTIZACIONES}


def _fecha(texto, nombre):
    if not texto:
        return None
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        raise ErrorHistorial(f"La fecha {nombre} «{texto}» no es válida (use AAAA-MM-DD). No se aplicó el filtro.") from None


def filtrar(conexion, estatus="", desde="", hasta="", id_cliente=None):
    """Cotizaciones que cumplen TODOS los filtros dados (CA-34, CA-61).

    Rango invertido o estatus desconocido: ErrorHistorial y no se filtra (CA-35).
    """
    if estatus and estatus not in ESTATUS:
        raise ErrorHistorial(f"Estatus «{estatus}» no válido. No se aplicó el filtro.")
    desde, hasta = _fecha(desde, "inicial"), _fecha(hasta, "final")
    if desde and hasta and desde > hasta:
        raise ErrorHistorial("Rango inválido: la fecha inicial es posterior a la final. No se aplicó el filtro.")
    cotizaciones = almacenamiento_datos.listar_cotizaciones(conexion, id_cliente, estatus or None, desde, hasta)
    return {"cotizaciones": cotizaciones, "mensaje": None if cotizaciones else SIN_RESULTADOS}
