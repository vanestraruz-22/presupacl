"""catalogo_syscom: búsqueda de productos SYSCOM con precio y existencia (RF-05, HU-05).

Consulta la API por medio de cliente_api_syscom y guarda lo encontrado en el
catálogo local, para poder cotizarlo. Si la API falla, muestra los últimos
datos guardados y lo avisa (CA-12, RNF-09). No ejecuta SQL.
"""

from proyecto.catalogo import cliente_api_syscom
from proyecto.infraestructura import almacenamiento_datos

AVISO_SIN_API = (
    "SYSCOM no está disponible en este momento ({motivo}). Se muestran los últimos datos guardados; "
    "también puede agregar conceptos manuales."
)


class ErrorCatalogo(Exception):
    pass


def buscar_productos(conexion, cliente_api, texto="", categoria="", marca=""):
    """Regresa {"resultados", "aviso", "fuente"} con fuente "syscom" o "local".

    - API disponible: guarda/actualiza los productos y regresa precio y existencia
      vigentes; existencia 0 se muestra como 0 (CA-11, CA-41).
    - API caída, sin configurar o con límite: datos locales previos + aviso (CA-12).
    Los productos con datos inválidos se omiten y se avisa cuántos fueron.
    """
    texto, categoria, marca = (v.strip() if v else "" for v in (texto, categoria, marca))
    if not (texto or categoria or marca):
        raise ErrorCatalogo("Escriba una palabra clave, categoría o marca para buscar.")

    if cliente_api is None:
        return _locales(conexion, texto, categoria, marca, "no hay credenciales de SYSCOM configuradas")
    try:
        crudos = cliente_api.buscar_productos(texto, categoria, marca)
    except cliente_api_syscom.ErrorApiSyscom as error:
        motivo = "se excedió el límite de peticiones" if error.tipo == "limite" else str(error)
        return _locales(conexion, texto, categoria, marca, motivo)

    validos, omitidos = [], 0
    for crudo in crudos:
        try:
            validos.append(cliente_api_syscom.normalizar_producto(crudo))
        except cliente_api_syscom.ErrorApiSyscom:
            omitidos += 1
    ids = almacenamiento_datos.guardar_productos_syscom(conexion, validos)
    resultados = list(almacenamiento_datos.obtener_conceptos(conexion, ids.values()).values())
    resultados.sort(key=lambda c: c["descripcion"])
    aviso = None
    if omitidos:
        aviso = f"Se omitieron {omitidos} producto(s) de SYSCOM con datos incompletos."
    elif not resultados:
        aviso = "No hay productos de SYSCOM que coincidan con la búsqueda."
    return {"resultados": resultados, "aviso": aviso, "fuente": "syscom"}


def _locales(conexion, texto, categoria, marca, motivo):
    resultados = almacenamiento_datos.buscar_conceptos(
        conexion, origen="syscom", texto=texto, categoria=categoria, marca=marca
    )
    aviso = AVISO_SIN_API.format(motivo=motivo)
    if not resultados:
        aviso += " No hay datos previos que coincidan."
    return {"resultados": resultados, "aviso": aviso, "fuente": "local"}
