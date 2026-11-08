"""registro_eventos: bitácora técnica en logs/presupacl.log.

Registra sincronizaciones, fallas de PDF y errores de guardado para poder
diagnosticar. Nunca escribe contraseñas, tokens ni credenciales (RNF-03).
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

RUTA_LOG = Path(__file__).resolve().parents[2] / "logs" / "presupacl.log"
_bitacora = logging.getLogger("presupacl")


def _configurar():
    if _bitacora.handlers:
        return
    _bitacora.setLevel(logging.INFO)
    try:
        RUTA_LOG.parent.mkdir(parents=True, exist_ok=True)
        manejador = RotatingFileHandler(RUTA_LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        manejador = logging.NullHandler()  # sin permiso de escritura: la app sigue funcionando
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _bitacora.addHandler(manejador)


def registrar(evento, detalle="", nivel=logging.INFO):
    _configurar()
    _bitacora.log(nivel, "%s | %s", evento, detalle)


def error(evento, detalle=""):
    registrar(evento, detalle, logging.ERROR)
