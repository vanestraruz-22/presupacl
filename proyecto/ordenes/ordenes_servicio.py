"""ordenes_servicio: orden de servicio automática al aceptar una cotización (RF-16, HU-14).

La orden lleva cliente, dirección elegida y conceptos de instalación, SIN
precios, utilidad, IVA ni total. Se crea junto con el cambio a "aceptada" en
una sola transacción; si falta la dirección no se acepta ni se crea nada.

SUPUESTO D05 — validar con Sofía Quesada y ACL: son de instalación los tipos
SYSCOM, manual, insumos, equipo de seguridad, programación y mano de obra; no
lo son viáticos ni el cargo por domingo o día festivo.
"""

import json

from proyecto.comunicacion import mensajeria_whatsapp
from proyecto.cotizaciones.calculadora_cotizacion import formato_cantidad
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos

TIPOS_INSTALACION = ("SYSCOM", "manual", "insumos", "equipo_seguridad", "programacion", "mano_obra")


def preparar_orden(cotizacion):
    """Datos de la orden o ErrorCotizacion si falta dirección o conceptos de instalación (CA-29)."""
    if not cotizacion.get("id_direccion") or not (cotizacion.get("direccion_snapshot") or "").strip():
        raise ErrorCotizacion("La cotización no tiene dirección de instalación. Edítela y elija una dirección; "
                              "no se aceptó ni se generó la orden.")
    tareas = [{"descripcion": p["descripcion_snapshot"], "unidad": p["unidad_snapshot"],
               "cantidad_milesimas": p["cantidad_milesimas"]}
              for p in cotizacion["partidas"] if p["tipo_snapshot"] in TIPOS_INSTALACION]
    if not tareas:
        raise ErrorCotizacion("La cotización no tiene conceptos de instalación; no se generó la orden.")
    return {
        "id_direccion": cotizacion["id_direccion"],
        "cliente_nombre_snapshot": cotizacion["cliente_nombre_snapshot"],
        "cliente_telefono_snapshot": cotizacion["cliente_telefono_snapshot"],
        "direccion_snapshot": cotizacion["direccion_snapshot"],
        "tareas_json": json.dumps(tareas, ensure_ascii=False),
    }


def aceptar_y_generar(conexion, cotizacion):
    """Acepta la cotización y genera su orden juntas (CA-28, CA-58). Regresa id_orden."""
    orden = preparar_orden(cotizacion)
    try:
        return almacenamiento_datos.aceptar_con_orden(conexion, cotizacion["id_cotizacion"], orden)
    except almacenamiento_datos.ErrorAlmacenamiento as error:
        raise ErrorCotizacion(str(error)) from error


def obtener(conexion, id_cotizacion):
    """Orden de la cotización con "tareas" como lista, o None."""
    orden = almacenamiento_datos.obtener_orden_por_cotizacion(conexion, id_cotizacion)
    if orden:
        orden["tareas"] = json.loads(orden["tareas_json"])
    return orden


def mensaje_tecnico(orden, folio):
    """Texto para el técnico: solo datos de instalación, sin importes (CA-30, CA-59)."""
    lineas = [f"Orden de servicio (cotización {folio})",
              f"Cliente: {orden['cliente_nombre_snapshot']}",
              f"Teléfono del cliente: {orden['cliente_telefono_snapshot']}",
              f"Dirección: {orden['direccion_snapshot']}",
              "Trabajos y materiales:"]
    lineas += [f"- {formato_cantidad(t['cantidad_milesimas'])} {t['unidad']}: {t['descripcion']}" for t in orden["tareas"]]
    return "\n".join(lineas)


def enlace_tecnico(orden, folio, telefono_tecnico):
    """Enlace de WhatsApp para el técnico; ErrorTelefono si falta o no es válido (CA-31)."""
    return mensajeria_whatsapp.enlace(telefono_tecnico, mensaje_tecnico(orden, folio))
