"""mensajeria_whatsapp: enlaces de WhatsApp prellenados para envío MANUAL (RF-12, RF-17).

El sistema no envía mensajes: arma un enlace https://wa.me/... que la persona
abre, revisa y envía. No hay tabla de mensajes (sección 3.7).

SUPUESTO — validar con ACL (D05, D07): teléfonos de México; 10 dígitos se
completan con la clave 52. El PDF no se enlaza porque vive en la computadora
de ACL y el cliente no puede abrirlo; se descarga y se adjunta a mano (RF-12).
"""

import re
import urllib.parse

from proyecto.cotizaciones.calculadora_cotizacion import formato_moneda


class ErrorTelefono(Exception):
    """Teléfono vacío o inválido; no se genera enlace (CA-31)."""


def normalizar_telefono(telefono):
    """'477 123 4567' -> '524771234567'. Lanza ErrorTelefono si no es válido."""
    digitos = re.sub(r"\D", "", telefono or "")
    if len(digitos) == 10:
        return "52" + digitos
    if len(digitos) == 12 and digitos.startswith("52"):
        return digitos
    if len(digitos) == 13 and digitos.startswith("521"):
        return "52" + digitos[3:]
    if not digitos:
        raise ErrorTelefono("Falta el número de teléfono; no se generó el enlace.")
    raise ErrorTelefono(f"El teléfono «{telefono}» no es válido (use 10 dígitos); no se generó el enlace.")


def enlace(telefono, mensaje):
    return f"https://wa.me/{normalizar_telefono(telefono)}?text={urllib.parse.quote(mensaje)}"


def mensaje_cotizacion(cotizacion):
    """Resumen para el cliente (CA-22)."""
    return (
        f"Hola {cotizacion['cliente_nombre_snapshot']}, le saluda {cotizacion['acl_nombre_snapshot']}.\n"
        f"Le compartimos la cotización {cotizacion['folio']} por un total de "
        f"{formato_moneda(cotizacion['total_centavos'], cotizacion['moneda'])} (IVA incluido), "
        f"vigente hasta el {cotizacion['vigencia_hasta']}.\n"
        "En seguida le enviamos el PDF con el detalle. Quedamos atentos a sus dudas."
    )


def enlace_cotizacion(cotizacion):
    """Enlace para el teléfono del cliente; ErrorTelefono si no es viable (CA-23 ofrece descarga)."""
    return enlace(cotizacion["cliente_telefono_snapshot"], mensaje_cotizacion(cotizacion))
