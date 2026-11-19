"""cliente_api_syscom: acceso a la API de SYSCOM (RF-05, RF-09, RF-10).

Es el único módulo que habla con SYSCOM. Entrega productos ya normalizados al
formato del catálogo local, así catalogo_syscom y el sincronizador no dependen
de cómo responde la API (RNF-05).

Credenciales SOLO por variables de entorno (RNF-03), nunca en el código:
    SYSCOM_CLIENT_ID, SYSCOM_CLIENT_SECRET
Modo de demostración sin API real:  PRESUPACL_SYSCOM=demo

Catálogo local (T-34, decisión del equipo del 19-nov-2026: no se usará la API):
si no hay credenciales, los productos se leen de un archivo CSV que ACL puede
editar en Excel o reemplazar desde la página Catálogo. Ruta por defecto:
proyecto/catalogo/catalogo_local.csv; se puede cambiar con PRESUPACL_CATALOGO.

AVISO: ClienteApiSyscom sigue la documentación pública de SYSCOM (OAuth2
client_credentials y /api/v1/productos), pero NO se ha probado contra la API
real porque el equipo no tiene credenciales. Los nombres de campos de la
respuesta son SUPUESTO — validar con la API (D02, D06). Las pruebas usan
ClienteSyscomSimulado.
"""

import csv
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

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

    def verificar(self):
        """Comprueba que la API responde (obtiene el token de acceso)."""
        self._obtener_token()

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

    def verificar(self):
        self._revisar()

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


RUTA_CATALOGO_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogo_local.csv")
COLUMNAS_CSV = ["clave", "descripcion", "marca", "categoria", "unidad", "precio", "existencia"]
MAX_PRODUCTOS_CSV = 20_000
# D02 (equipo, 19-nov-2026): se cotiza en MXN y los precios del catálogo YA
# incluyen IVA. Al leerlos se les quita el IVA para que la cotización no lo
# cobre dos veces (el IVA se suma una sola vez al final). SUPUESTO: tasa 16 %.
IVA_INCLUIDO_TASA = Decimal("0.16")


def quitar_iva(precio_texto):
    """'1160.00' (con IVA) -> '1000.00' (sin IVA), redondeo al centavo. Texto inválido se regresa igual."""
    try:
        precio = Decimal(str(precio_texto).replace(",", ""))
    except (InvalidOperation, ValueError):
        return precio_texto
    if not precio.is_finite() or precio < 0 or abs(precio) >= Decimal("1e15"):
        return precio_texto
    return str((precio / (1 + IVA_INCLUIDO_TASA)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def leer_csv_catalogo(texto):
    """Valida el texto de un CSV de catálogo y regresa sus productos en formato de la API.

    Acepta separador coma o punto y coma (Excel en español) y precios con "$" o
    comas de miles. Lanza ErrorApiSyscom(tipo="respuesta_invalida") indicando la
    fila con problemas; si hay un error no se acepta ninguna fila.
    """
    texto = texto.lstrip("\ufeff")
    primera = texto.split("\n", 1)[0]
    separador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=separador)
    encabezados = [(c or "").strip().lower() for c in (lector.fieldnames or [])]
    faltantes = [c for c in ("clave", "descripcion", "precio") if c not in encabezados]
    if faltantes:
        raise ErrorApiSyscom("El archivo no tiene las columnas obligatorias: " + ", ".join(faltantes)
                             + f". Columnas esperadas: {', '.join(COLUMNAS_CSV)}.", "respuesta_invalida")
    productos, claves = [], set()
    for numero, fila in enumerate(lector, start=2):
        fila = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items() if k}
        if not any(fila.values()):
            continue  # renglón vacío
        crudo = {
            "producto_id": fila.get("clave"), "titulo": fila.get("descripcion"),
            "marca": fila.get("marca") or None, "categoria": fila.get("categoria") or None,
            "unidad": fila.get("unidad") or "pieza",
            "precio": fila.get("precio", "").replace("$", "").strip() or None,
            "existencia": fila.get("existencia") or None,
        }
        try:
            producto = normalizar_producto(crudo)
        except ErrorApiSyscom as error:
            raise ErrorApiSyscom(f"Fila {numero}: {error}", "respuesta_invalida") from None
        if producto["syscom_id"] in claves:
            raise ErrorApiSyscom(f"Fila {numero}: la clave {producto['syscom_id']} está repetida.",
                                 "respuesta_invalida")
        claves.add(producto["syscom_id"])
        crudo["producto_id"] = producto["syscom_id"]
        crudo["precio_con_iva"] = crudo["precio"]
        crudo["precio"] = quitar_iva(crudo["precio"])
        productos.append(crudo)
        if len(productos) > MAX_PRODUCTOS_CSV:
            raise ErrorApiSyscom(f"El archivo tiene más de {MAX_PRODUCTOS_CSV} productos.", "respuesta_invalida")
    if not productos:
        raise ErrorApiSyscom("El archivo no tiene productos.", "respuesta_invalida")
    return productos


class ClienteCatalogoLocal:
    """Lee los productos de un archivo CSV local en lugar de la API (T-34).

    Cumple la misma interfaz que ClienteApiSyscom, así la búsqueda (RF-05) y la
    sincronización de precios (RF-09/RF-10) funcionan igual: al editar el
    archivo y sincronizar, los precios del catálogo se actualizan.
    """

    es_local = True
    descripcion = "archivo local de productos (catalogo_local.csv)"

    def __init__(self, ruta=RUTA_CATALOGO_LOCAL):
        self.ruta = ruta

    def _productos(self):
        try:
            with open(self.ruta, encoding="utf-8-sig", newline="") as archivo:
                texto = archivo.read()
        except FileNotFoundError:
            raise ErrorApiSyscom("No se encontró el archivo del catálogo local.") from None
        except (OSError, UnicodeDecodeError):
            raise ErrorApiSyscom("No se pudo leer el archivo del catálogo local.", "respuesta_invalida") from None
        return {p["producto_id"]: p for p in leer_csv_catalogo(texto)}

    def verificar(self):
        self._productos()

    def buscar_productos(self, texto="", categoria="", marca=""):
        def coincide(valor, filtro):
            return not filtro or filtro.lower() in str(valor or "").lower()

        return [dict(p) for p in self._productos().values()
                if (coincide(p["titulo"], texto) or coincide(p["producto_id"], texto))
                and coincide(p["categoria"], categoria) and coincide(p["marca"], marca)]

    def obtener_producto(self, syscom_id):
        productos = self._productos()
        if str(syscom_id) not in productos:
            raise ErrorApiSyscom(f"Producto {syscom_id} no está en el catálogo local.", "no_encontrado")
        return dict(productos[str(syscom_id)])

    def reemplazar_archivo(self, texto):
        """Valida y guarda un CSV nuevo. Regresa cuántos productos tiene."""
        productos = leer_csv_catalogo(texto)
        temporal = self.ruta + ".tmp"
        with open(temporal, "w", encoding="utf-8", newline="") as archivo:
            archivo.write(texto.lstrip("\ufeff"))
        os.replace(temporal, self.ruta)
        return len(productos)


def obtener_cliente_configurado():
    """Cliente según el entorno: demo, API real con credenciales o catálogo local (CSV)."""
    if os.environ.get("PRESUPACL_SYSCOM", "").lower() == "demo":
        return ClienteSyscomSimulado(PRODUCTOS_DEMO)
    client_id = os.environ.get("SYSCOM_CLIENT_ID")
    client_secret = os.environ.get("SYSCOM_CLIENT_SECRET")
    if client_id and client_secret:
        return ClienteApiSyscom(client_id, client_secret)
    return ClienteCatalogoLocal(os.environ.get("PRESUPACL_CATALOGO") or RUTA_CATALOGO_LOCAL)
