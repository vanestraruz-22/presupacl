"""cotizaciones_edicion: modificar una cotización PENDIENTE (RF-14, HU-13).

Recalcula con las tasas guardadas en la propia cotización y, después de
guardar, regenera el PDF (decisión H8). Si el PDF falla, los datos ya quedaron
guardados y se informa para reintentar (sección 3.8).
"""

from proyecto.cotizaciones import cotizaciones_creacion
from proyecto.cotizaciones.cotizaciones_estado import exigir_pendiente
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion, validar_partidas
from proyecto.documentos import generador_pdf_cotizacion
from proyecto.infraestructura import almacenamiento_datos


def renglones_de(cotizacion):
    """Renglones editables a partir de las partidas guardadas."""
    return [{"id_concepto": p["id_concepto"], "cantidad": p["cantidad_milesimas"],
             "precio": p["precio_unitario_centavos"]} for p in cotizacion["partidas"]]


def editar_cotizacion(conexion, id_cotizacion, renglones, id_direccion=None, carpeta_pdf=None):
    """Guarda los cambios y regenera el PDF. Regresa {"pdf_ruta", "aviso"}.

    Errores (ErrorCotizacion, nada cambia): cotización inexistente o cerrada
    (CA-27), sin conceptos (CA-63), renglón inválido o falla al guardar (CA-56).
    """
    cotizacion = almacenamiento_datos.obtener_cotizacion(conexion, id_cotizacion)
    if cotizacion is None:
        raise ErrorCotizacion(f"No existe la cotización {id_cotizacion}.")
    exigir_pendiente(cotizacion)

    if not renglones:
        validar_partidas([])
    partidas = cotizaciones_creacion.preparar_partidas(conexion, renglones, cotizacion["moneda"])
    validar_partidas(partidas)
    totales = cotizaciones_creacion.totales(partidas, cotizacion["metodo_utilidad"],
                                            cotizacion["utilidad_tasa"], cotizacion["iva_tasa"])
    cliente = almacenamiento_datos.obtener_cliente(conexion, cotizacion["id_cliente"])
    if id_direccion in (None, ""):
        id_direccion, direccion = cotizacion["id_direccion"], cotizacion["direccion_snapshot"]
    else:
        direccion = cotizaciones_creacion.validar_direccion(cliente, id_direccion)
        id_direccion = int(id_direccion)

    try:
        almacenamiento_datos.reemplazar_partidas(conexion, id_cotizacion, partidas, totales, id_direccion, direccion)
    except almacenamiento_datos.ErrorEstadoCotizacion as error:
        raise ErrorCotizacion(str(error)) from error
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        raise ErrorCotizacion(f"{error} No se guardaron los cambios.") from error

    try:
        ruta = generador_pdf_cotizacion.generar_pdf(conexion, id_cotizacion, carpeta_pdf)
    except generador_pdf_cotizacion.ErrorPdf as error:
        return {"pdf_ruta": None, "aviso": f"Cambios guardados, pero el PDF no se regeneró: {error}"}
    return {"pdf_ruta": ruta, "aviso": None}
