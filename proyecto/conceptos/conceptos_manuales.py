"""conceptos_manuales: productos y servicios que no vienen de SYSCOM (RF-06, HU-06).

El catálogo guarda descripción, unidad, tipo y precio vigente. La cantidad se
captura en cada cotización, porque pertenece a la partida y no al catálogo (D07).
"""

from proyecto.cotizaciones import calculadora_cotizacion as calc
from proyecto.infraestructura import almacenamiento_datos

# Tipos de RF-07 que se capturan a mano (SYSCOM viene del catálogo).
TIPOS_MANUALES = {
    "manual": "Producto o material manual",
    "mano_obra": "Mano de obra",
    "viaticos": "Viáticos",
    "insumos": "Insumos de instalación",
    "programacion": "Programación",
    "equipo_seguridad": "Equipo de seguridad",
    "dia_festivo": "Cargo por domingo o día festivo",
}
MONEDA = "MXN"  # SUPUESTO D02 — validar con ACL.


class ErrorConcepto(Exception):
    """Datos inválidos del concepto; no se guardó (CA-43)."""

    def __init__(self, errores):
        self.errores = errores
        super().__init__("Revise los datos: " + "; ".join(errores.values()) + ". No se guardó el concepto.")


def validar(tipo, descripcion, unidad, precio):
    """Regresa (datos_limpios, errores) donde errores es {campo: mensaje}."""
    errores = {}
    datos = {"tipo": tipo, "descripcion": (descripcion or "").strip(), "unidad": (unidad or "").strip()}
    if tipo not in TIPOS_MANUALES:
        errores["tipo"] = "elija un tipo de concepto"
    if not datos["descripcion"]:
        errores["descripcion"] = "la descripción es obligatoria"
    if not datos["unidad"]:
        errores["unidad"] = "la unidad es obligatoria"
    try:
        datos["precio_unitario_centavos"] = calc.texto_a_centavos(precio)
    except calc.ErrorCalculo as error:
        errores["precio"] = str(error)
    return datos, errores


def registrar_concepto(conexion, tipo, descripcion, unidad, precio):
    """Guarda un concepto manual y regresa su id (CA-13). Precio cero se permite (CA-42)."""
    datos, errores = validar(tipo, descripcion, unidad, precio)
    if errores:
        raise ErrorConcepto(errores)
    return almacenamiento_datos.crear_concepto_manual(
        conexion, datos["tipo"], datos["descripcion"], datos["unidad"], datos["precio_unitario_centavos"], MONEDA
    )


def modificar_concepto(conexion, id_concepto, tipo, descripcion, unidad, precio):
    """Modifica un concepto manual. Las cotizaciones ya guardadas no cambian (snapshots)."""
    datos, errores = validar(tipo, descripcion, unidad, precio)
    if errores:
        raise ErrorConcepto(errores)
    almacenamiento_datos.actualizar_concepto_manual(
        conexion, id_concepto, datos["tipo"], datos["descripcion"], datos["unidad"], datos["precio_unitario_centavos"]
    )


def listar(conexion, texto=""):
    return almacenamiento_datos.buscar_conceptos(conexion, origen="manual", texto=texto)
