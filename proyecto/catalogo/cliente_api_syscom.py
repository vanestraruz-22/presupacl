"""cliente_api_syscom: acceso a la API de SYSCOM (RF-05, RF-09, RF-10).

Es el único módulo que habla con SYSCOM. Entrega productos ya normalizados al
formato del catálogo local, así catalogo_syscom y el sincronizador no dependen
de cómo responde la API (RNF-05).

Credenciales SOLO por variables de entorno (RNF-03), nunca en el código:
    SYSCOM_CLIENT_ID, SYSCOM_CLIENT_SECRET
Modo de demostración sin API real:  PRESUPACL_SYSCOM=demo

AVISO: ClienteApiSyscom sigue la documentación pública de SYSCOM (OAuth2
client_credentials y /api/v1/productos), pero NO se ha probado contra la API
real porque el equipo no tiene credenciales. Los nombres de campos de la
respuesta son SUPUESTO — validar con la API (D02, D06). Las pruebas usan
ClienteSyscomSimulado.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

URL_BASE = "https://developers.syscom.mx"
MONEDA = "MXN"  # SUPUESTO D02


class ErrorApiSyscom(Exception):
    """La API no respondió como se esperaba. tipo: no_disponible, limite o respuesta_invalida."""

    def __init__(self, mensaje, tipo="no_disponible"):
        super().__init__(mensaje)
        self.tipo = tipo


def normalizar_producto(crudo):
    """Valida un producto y lo convierte al formato del catálogo (CA-48).

    Regresa el dict normalizado o lanza ErrorApiSyscom(tipo="respuesta_invalida")
    si falta el id, la descripción o el precio no es un número válido no negativo.
    """
    if not isinstance(crudo, dict):
        raise ErrorApiSyscom("Producto con formato inválido.", "respuesta_invalida")
    syscom_id = str(crudo.get("producto_id") or crudo.get("syscom_id") or "").strip()
    descripcion = str(crudo.get("titulo") or crudo.get("descripcion") or "").strip()
    if not syscom_id or not descripcion:
        raise ErrorApiSyscom("Producto sin identificador o sin descripción.", "respuesta_invalida")

    precios = crudo.get("precios") if isinstance(crudo.get("precios"), dict) else {}
    precio_texto = precios.get("precio_descuento", crudo.get("precio"))
    try:
        precio = Decimal(str(precio_texto).replace(",", ""))
        if not precio.is_finite() or precio < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ErrorApiSyscom(f"Producto {syscom_id} sin precio válido.", "respuesta_invalida") from None

    existencia = crudo.get("total_existencia", crudo.get("existencia"))
    if existencia is not None:
        try:
            existencia = int(existencia)
        except (TypeError, ValueError):
            raise ErrorApiSyscom(f"Producto {syscom_id} con existencia inválida.", "respuesta_invalida") from None
        if existencia < 0:
            raise ErrorApiSyscom(f"Producto {syscom_id} con existencia negativa.", "respuesta_invalida")

    categoria = crudo.get("categoria")
    if not categoria and isinstance(crudo.get("categorias"), list) and crudo["categorias"]:
        primera = crudo["categorias"][0]
        categoria = primera.get("nombre") if isinstance(primera, dict) else str(primera)

    return {
        "syscom_id": syscom_id,
        "descripcion": descripcion,
        "unidad": str(crudo.get("unidad_de_medida") or crudo.get("unidad") or "pieza"),
        "marca": crudo.get("marca") or None,
        "categoria": categoria or None,
        "precio_unitario_centavos": int((precio * 100).quantize(Decimal(1))),
        "moneda": MONEDA,
        "existencia": existencia,
    }


class ClienteApiSyscom:
    """Cliente HTTP para la API real. Ver AVISO en el encabezado del módulo."""

    def __init__(self, client_id, client_secret, url_base=URL_BASE, tiempo_limite=15):
        self._client_id = client_id
        self._client_secret = client_secret
        self._url_base = url_base.rstrip("/")
        self._tiempo_limite = tiempo_limite
        self._token = None

    def _pedir(self, metodo, ruta, datos=None, autenticar=True):
        cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
        solicitud = urllib.request.Request(self._url_base + ruta, data=cuerpo, method=metodo)
        if autenticar:
            solicitud.add_header("Authorization", f"Bearer {self._obtener_token()}")
        try:
            with urllib.request.urlopen(solicitud, timeout=self._tiempo_limite) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise ErrorApiSyscom("SYSCOM rechazó la consulta por límite de peticiones.", "limite") from None
            raise ErrorApiSyscom(f"SYSCOM respondió con error {error.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ErrorApiSyscom("No hay conexión con SYSCOM.") from None
        except ValueError:
            raise ErrorApiSyscom("SYSCOM regresó una respuesta ilegible.", "respuesta_invalida") from None

    def _obtener_token(self):
        if self._token is None:
            respuesta = self._pedir("POST", "/oauth/token", {
                "client_id": self._client_id, "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            }, autenticar=False)
            self._token = respuesta.get("access_token") if isinstance(respuesta, dict) else None
            if not self._token:
                raise ErrorApiSyscom("SYSCOM no entregó un token de acceso.", "respuesta_invalida")
        return self._token

    def buscar_productos(self, texto="", categoria="", marca=""):
        parametros = {k: v for k, v in (("busqueda", texto), ("categoria", categoria), ("marca", marca)) if v}
        respuesta = self._pedir("GET", "/api/v1/productos?" + urllib.parse.urlencode(parametros))
        productos = respuesta.get("productos") if isinstance(respuesta, dict) else None
        if not isinstance(productos, list):
            raise ErrorApiSyscom("La respuesta de búsqueda no trae productos.", "respuesta_invalida")
        return productos

    def obtener_producto(self, syscom_id):
        return self._pedir("GET", "/api/v1/productos/" + urllib.parse.quote(str(syscom_id)))


class ClienteSyscomSimulado:
    """Sustituto de la API para pruebas y demostraciones (sin red ni credenciales).

    falla: None, "no_disponible", "limite" o "respuesta_invalida" para simular errores.
    """

    def __init__(self, productos=None, falla=None):
        self.productos = {str(p["producto_id"]): dict(p) for p in (productos or [])}
        self.falla = falla
        self.llamadas = 0

    def _revisar(self):
        self.llamadas += 1
        if self.falla:
            raise ErrorApiSyscom(f"Falla simulada de SYSCOM ({self.falla}).", self.falla)

    def buscar_productos(self, texto="", categoria="", marca=""):
        self._revisar()

        def coincide(valor, filtro):
            return not filtro or filtro.lower() in str(valor or "").lower()

        return [dict(p) for p in self.productos.values()
                if coincide(p.get("titulo"), texto) and coincide(p.get("categoria"), categoria)
                and coincide(p.get("marca"), marca)]

    def obtener_producto(self, syscom_id):
        self._revisar()
        if str(syscom_id) not in self.productos:
            raise ErrorApiSyscom(f"Producto {syscom_id} no encontrado en SYSCOM.", "no_encontrado")
        return dict(self.productos[str(syscom_id)])


# Productos ficticios para el modo demostración (no son precios reales de SYSCOM).
PRODUCTOS_DEMO = [
    {"producto_id": "DEMO-001", "titulo": "Cámara bala 2 MP exterior (demostración)", "marca": "MarcaDemo",
     "categoria": "Videovigilancia", "precio": "850.00", "total_existencia": 25},
    {"producto_id": "DEMO-002", "titulo": "Cámara domo 4 MP interior (demostración)", "marca": "MarcaDemo",
     "categoria": "Videovigilancia", "precio": "1199.90", "total_existencia": 8},
    {"producto_id": "DEMO-003", "titulo": "Grabador DVR 8 canales (demostración)", "marca": "OtraMarca",
     "categoria": "Videovigilancia", "precio": "2450.00", "total_existencia": 0},
    {"producto_id": "DEMO-004", "titulo": "Panel de alarma 8 zonas (demostración)", "marca": "OtraMarca",
     "categoria": "Alarmas", "precio": "3100.00", "total_existencia": 4},
    {"producto_id": "DEMO-005", "titulo": "Sensor de movimiento PIR (demostración)", "marca": "MarcaDemo",
     "categoria": "Alarmas", "precio": "320.50", "total_existencia": 60},
    {"producto_id": "DEMO-006", "titulo": "Bobina cable UTP Cat6 305 m (demostración)", "marca": "CableDemo",
     "categoria": "Cableado", "precio": "2890.00", "total_existencia": 12, "unidad_de_medida": "bobina"},
]


def obtener_cliente_configurado():
    """Cliente según el entorno: demo, API real con credenciales, o None (sin API)."""
    if os.environ.get("PRESUPACL_SYSCOM", "").lower() == "demo":
        return ClienteSyscomSimulado(PRODUCTOS_DEMO)
    client_id = os.environ.get("SYSCOM_CLIENT_ID")
    client_secret = os.environ.get("SYSCOM_CLIENT_SECRET")
    if client_id and client_secret:
        return ClienteApiSyscom(client_id, client_secret)
    return None
