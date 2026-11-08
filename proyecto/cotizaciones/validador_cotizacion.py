"""validador_cotizacion: una cotización necesita al menos un concepto válido (RF-20, HU-19).

Lo usan la creación (RF-07) y la edición (RF-14) antes de guardar.
"""

MENSAJE_SIN_CONCEPTOS = "La cotización debe tener al menos un concepto (producto o servicio). No se guardó."


class ErrorCotizacion(Exception):
    """Regla de negocio de la cotización no cumplida; no se guarda nada."""


def validar_partidas(partidas):
    """Lanza ErrorCotizacion si no hay partidas o alguna tiene cantidad <= 0 (CA-15, CA-63, CA-16)."""
    if not partidas:
        raise ErrorCotizacion(MENSAJE_SIN_CONCEPTOS)
    for numero, partida in enumerate(partidas, start=1):
        cantidad = partida.get("cantidad_milesimas")
        if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
            raise ErrorCotizacion(f"Renglón {numero}: la cantidad debe ser mayor que cero. No se guardó.")
        if not partida.get("id_concepto"):
            raise ErrorCotizacion(f"Renglón {numero}: falta el concepto. No se guardó.")
