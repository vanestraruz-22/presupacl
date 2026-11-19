"""settings (configuracion_acl): datos de identificación de ACL y condiciones
comerciales por defecto (RF-21, HU-18).

Se capturan una sola vez y se copian a cada cotización nueva (snapshots), por
eso cambiarlos después no altera cotizaciones ya emitidas.

DECIDIDO por el equipo el 19-nov-2026 (D01): la utilidad es MARGEN sobre el
precio de venta. Método por defecto "margen"; "recargo" sigue disponible.
SUPUESTOS — validar con ACL: IVA por defecto 0.16; utilidad por defecto 0.20.
Son valores editables.
- Vigencia por defecto 15 días.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from proyecto.infraestructura import almacenamiento_datos

CARPETA_LOGO = Path(__file__).resolve().parents[2] / "recursos" / "logo_acl"
EXTENSIONES_LOGO = {".png", ".jpg", ".jpeg"}

VALORES_INICIALES = {
    "nombre_comercial": "ACL Alarmas y Cámaras de León",
    "telefono": "",
    "correo": "",
    "logo_ruta": None,
    "condiciones_default": "",
    "vigencia_dias_default": 15,
    "iva_tasa_default": "0.16",
    "utilidad_tasa_default": "0.20",
    "metodo_utilidad": "margen",  # D01 decidido el 19-nov-2026
}

MENSAJE_FALLA = "No se pudo guardar la configuración. Los cambios NO se guardaron."


class ErrorConfiguracion(Exception):
    """Datos inválidos o falla al guardar; nunca se declara éxito (CA-65)."""

    def __init__(self, mensaje, campos=None):
        super().__init__(mensaje)
        self.campos = campos or []


def _tasa(texto):
    """Valida una fracción decimal entre 0 y 1 (excluyendo 1) y la regresa como texto."""
    try:
        valor = Decimal(str(texto).strip())
    except (InvalidOperation, ValueError):
        return None
    if not valor.is_finite() or valor < 0 or valor >= 1:
        return None
    return str(valor)


def validar_configuracion(datos):
    """Regresa (datos_limpios, campos_con_error)."""
    limpio = {}
    errores = []
    for campo in ("nombre_comercial", "telefono", "correo"):
        limpio[campo] = (datos.get(campo) or "").strip()
        if not limpio[campo]:
            errores.append(campo)
    if limpio["correo"] and "@" not in limpio["correo"]:
        errores.append("correo")

    # CA-64: las condiciones se guardan completas, con todos sus saltos de línea.
    limpio["condiciones_default"] = (datos.get("condiciones_default") or "").replace("\r\n", "\n").strip("\n")
    limpio["logo_ruta"] = datos.get("logo_ruta") or None

    try:
        limpio["vigencia_dias_default"] = int(datos.get("vigencia_dias_default"))
        if limpio["vigencia_dias_default"] <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errores.append("vigencia_dias_default")

    for campo in ("iva_tasa_default", "utilidad_tasa_default"):
        limpio[campo] = _tasa(datos.get(campo, ""))
        if limpio[campo] is None:
            errores.append(campo)

    limpio["metodo_utilidad"] = datos.get("metodo_utilidad")
    if limpio["metodo_utilidad"] not in ("margen", "recargo"):
        errores.append("metodo_utilidad")
    return limpio, errores


def guardar_configuracion(conexion, datos):
    """Valida y guarda la configuración. Regresa la configuración guardada.

    Lanza ErrorConfiguracion si hay datos inválidos o si el guardado falla (CA-65).
    """
    limpio, errores = validar_configuracion(datos)
    if errores:
        raise ErrorConfiguracion("Revise los campos marcados. No se guardó la configuración.", errores)
    try:
        almacenamiento_datos.guardar_configuracion(conexion, limpio)
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        raise ErrorConfiguracion(MENSAJE_FALLA) from error
    return obtener_configuracion(conexion)


def obtener_configuracion(conexion):
    """Configuración guardada, o VALORES_INICIALES si aún no se captura."""
    return almacenamiento_datos.obtener_configuracion(conexion) or dict(VALORES_INICIALES)


def configuracion_completa(conexion):
    """True si ya se capturó la configuración (requisito para emitir cotizaciones)."""
    return almacenamiento_datos.obtener_configuracion(conexion) is not None


def guardar_logo(contenido, nombre_archivo, carpeta=None):
    """Guarda el logo en recursos/logo_acl/ con nombre único y regresa su ruta.

    No se sobrescriben logos anteriores: los PDF ya emitidos apuntan a su copia.
    """
    extension = Path(nombre_archivo or "").suffix.lower()
    if extension not in EXTENSIONES_LOGO:
        raise ErrorConfiguracion("El logo debe ser una imagen PNG o JPG.", ["logo_ruta"])
    carpeta = Path(carpeta) if carpeta else CARPETA_LOGO
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"logo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
    ruta.write_bytes(contenido)
    return str(ruta)
