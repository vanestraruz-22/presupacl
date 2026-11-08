"""sincronizador_precios_syscom: actualización diaria de precios y existencias (RF-09, RF-10).

Consulta cada producto SYSCOM del catálogo local y, solo si TODAS las respuestas
son válidas, actualiza precios y existencias y registra el éxito. Ante falla,
límite de peticiones o datos corruptos no toca los datos vigentes y deja el
aviso para el administrador (RNF-09).

SUPUESTOS — validar con el equipo y ACL (D06):
- Se sincroniza si pasaron 24 horas desde el último éxito (o nunca ha habido
  uno) mientras la aplicación está abierta; se revisa cada hora.
- Tras una falla se reintenta una hora después.
- Un producto que SYSCOM ya no encuentra se deja como estaba y se menciona en
  el detalle.
"""

import threading
from datetime import datetime, timedelta

from proyecto.catalogo import cliente_api_syscom
from proyecto.infraestructura import almacenamiento_datos, registro_eventos

INTERVALO_EXITO = timedelta(hours=24)
INTERVALO_REINTENTO = timedelta(hours=1)


def _fecha(texto):
    return datetime.fromisoformat(texto) if texto else None


def sincronizar(conexion, cliente_api):
    """Ejecuta un intento y regresa {"resultado": "exitosa"|"fallida", "detalle"}."""
    id_sinc = almacenamiento_datos.iniciar_sincronizacion(conexion)
    if cliente_api is None:
        return _fallida(conexion, id_sinc, "No hay credenciales de SYSCOM configuradas.")
    locales = almacenamiento_datos.buscar_conceptos(conexion, origen="syscom", limite=100_000)
    nuevos, no_encontrados = [], []
    try:
        if not locales:
            cliente_api.verificar()  # primera ejecución: confirmar que SYSCOM responde (CA-49)
        for concepto in locales:
            try:
                crudo = cliente_api.obtener_producto(concepto["syscom_id"])
            except cliente_api_syscom.ErrorApiSyscom as error:
                if error.tipo == "no_encontrado":
                    no_encontrados.append(concepto["syscom_id"])
                    continue
                raise
            producto = cliente_api_syscom.normalizar_producto(crudo)
            if producto["syscom_id"] != concepto["syscom_id"]:
                raise cliente_api_syscom.ErrorApiSyscom("SYSCOM regresó un producto distinto al pedido.",
                                                         "respuesta_invalida")
            nuevos.append(producto)
    except cliente_api_syscom.ErrorApiSyscom as error:
        motivo = {"limite": "SYSCOM rechazó la consulta por límite de peticiones",
                  "respuesta_invalida": "SYSCOM envió datos incompletos o inválidos"}.get(error.tipo, "SYSCOM no respondió")
        return _fallida(conexion, id_sinc, f"{motivo} ({error}). Se conservan los precios anteriores.")

    detalle = f"{len(nuevos)} producto(s) actualizados."
    if no_encontrados:
        detalle += f" {len(no_encontrados)} ya no aparecen en SYSCOM y se dejaron como estaban: {', '.join(no_encontrados)}."
    if not locales:
        detalle = "No hay productos SYSCOM en el catálogo local; nada que actualizar."
    try:
        almacenamiento_datos.finalizar_sincronizacion(conexion, id_sinc, "exitosa", detalle, nuevos)
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        return _fallida(conexion, id_sinc, f"{error} Se conservan los precios anteriores.")
    registro_eventos.registrar("sincronizacion_exitosa", detalle)
    return {"resultado": "exitosa", "detalle": detalle}


def _fallida(conexion, id_sinc, detalle):
    almacenamiento_datos.finalizar_sincronizacion(conexion, id_sinc, "fallida", detalle)
    registro_eventos.error("sincronizacion_fallida", detalle)
    return {"resultado": "fallida", "detalle": detalle}


def debe_sincronizar(conexion, ahora=None):
    ahora = ahora or datetime.now().astimezone()
    exito = almacenamiento_datos.ultima_sincronizacion(conexion, "exitosa")
    intento = almacenamiento_datos.ultima_sincronizacion(conexion)
    if exito and ahora - _fecha(exito["finalizada_en"]) < INTERVALO_EXITO:
        return False
    if intento and intento["resultado"] == "fallida" and ahora - _fecha(intento["iniciada_en"]) < INTERVALO_REINTENTO:
        return False
    return True


def estado(conexion):
    """Para el panel: última sincronización exitosa y aviso si el último intento falló (RF-10)."""
    exito = almacenamiento_datos.ultima_sincronizacion(conexion, "exitosa")
    intento = almacenamiento_datos.ultima_sincronizacion(conexion)
    aviso = None
    if intento and intento["resultado"] == "fallida":
        aviso = (f"La actualización de precios SYSCOM del {intento['iniciada_en'][:16].replace('T', ' ')} no se completó: "
                 f"{intento['detalle']} Puede seguir cotizando con los últimos precios guardados y con conceptos manuales.")
    return {"ultima_exitosa": exito["finalizada_en"] if exito else None, "aviso": aviso,
            "ultimo_intento": intento}


class ProgramadorSincronizacion:
    """Revisa periódicamente si toca sincronizar mientras la aplicación está abierta (CA-47)."""

    def __init__(self, abrir_conexion, obtener_cliente, cada_segundos=3600):
        self._abrir_conexion = abrir_conexion
        self._obtener_cliente = obtener_cliente
        self._cada = cada_segundos
        self._detener = threading.Event()
        self._hilo = None

    def revisar(self, ahora=None):
        """Un ciclo: sincroniza si corresponde. Regresa el resultado o None."""
        conexion = None
        try:
            conexion = self._abrir_conexion()
            if debe_sincronizar(conexion, ahora):
                return sincronizar(conexion, self._obtener_cliente())
            return None
        except Exception as error:  # el hilo nunca debe tirar la aplicación
            registro_eventos.error("programador_sincronizacion", repr(error))
            return None
        finally:
            if conexion is not None:
                conexion.close()

    def iniciar(self):
        def ciclo():
            while not self._detener.is_set():
                self.revisar()
                self._detener.wait(self._cada)
        self._hilo = threading.Thread(target=ciclo, name="sincronizacion-syscom", daemon=True)
        self._hilo.start()

    def detener(self):
        self._detener.set()
