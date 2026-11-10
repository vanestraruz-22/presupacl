"""cotizaciones_estado: cambio de estatus y bloqueo de cotizaciones cerradas (RF-13, RF-15).

Estatus permitidos: pendiente, aceptada y rechazada.
SUPUESTO D04 — validar con ACL: solo una cotización pendiente cambia de
estatus; una aceptada o rechazada no se reabre (para cambiarla se duplica).
"""

from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos

ESTATUS = ("pendiente", "aceptada", "rechazada")
AVISO_CERRADA = ("La cotización está {estatus} y ya no se puede modificar. "
                 "Si necesita cambios, duplíquela para crear una nueva pendiente.")


def puede_editarse(cotizacion):
    return cotizacion["estatus"] == "pendiente"


def exigir_pendiente(cotizacion):
    """Lanza ErrorCotizacion con el aviso de RF-15 si la cotización está cerrada (CA-27)."""
    if not puede_editarse(cotizacion):
        raise ErrorCotizacion(AVISO_CERRADA.format(estatus=cotizacion["estatus"]))


def cambiar_estatus(conexion, id_cotizacion, nuevo):
    """Guarda el nuevo estatus. Regresa True si cambió y False si ya lo tenía.

    - Estatus fuera de los tres permitidos: error y no cambia nada (CA-54).
    - Mismo estatus: se conserva sin modificar datos (CA-53).
    - Cotización cerrada: no cambia (D04).
    """
    if nuevo not in ESTATUS:
        raise ErrorCotizacion(f"Estatus «{nuevo}» no permitido; use pendiente, aceptada o rechazada. No se cambió.")
    cotizacion = almacenamiento_datos.obtener_cotizacion(conexion, id_cotizacion)
    if cotizacion is None:
        raise ErrorCotizacion(f"No existe la cotización {id_cotizacion}.")
    if cotizacion["estatus"] == nuevo:
        return False
    exigir_pendiente(cotizacion)
    if nuevo == "aceptada":
        return _aceptar(conexion, cotizacion)
    try:
        almacenamiento_datos.actualizar_estatus(conexion, id_cotizacion, nuevo, "pendiente")
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        raise ErrorCotizacion(str(error)) from error
    return True


def _aceptar(conexion, cotizacion):
    """Aceptar genera la orden de servicio en la misma transacción (RF-16, incremento 5)."""
    from proyecto.ordenes import ordenes_servicio  # import local: evita un ciclo entre módulos
    ordenes_servicio.aceptar_y_generar(conexion, cotizacion)
    return True
