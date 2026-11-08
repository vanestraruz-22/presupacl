"""generador_pdf_cotizacion: PDF de la cotización (RF-11, HU-10; RF-14 regeneración, H8).

Usa solo los datos guardados en la cotización (snapshots de ACL y del cliente,
partidas y totales), así un PDF regenerado de una cotización antigua no cambia
aunque después se modifique la configuración o el catálogo.

SUPUESTO D09: biblioteca fpdf2 con la fuente Helvetica (acentos y ñ sí; otros
símbolos poco comunes se sustituyen por "?").
"""

import os
import tempfile
from pathlib import Path

from fpdf import FPDF

from proyecto.cotizaciones.calculadora_cotizacion import formato_cantidad, formato_moneda
from proyecto.cotizaciones.cotizaciones_creacion import TIPOS
from proyecto.infraestructura import almacenamiento_datos

CARPETA_SALIDA = Path(__file__).resolve().parents[2] / "salidas" / "cotizaciones"
AZUL = (31, 78, 121)


class ErrorPdf(Exception):
    """No se pudo generar el PDF; la cotización guardada no cambia (CA-51)."""


def _t(texto):
    """Texto compatible con la fuente base del PDF (latin-1)."""
    return str(texto if texto is not None else "").replace("—", "-").replace("–", "-") \
        .replace("“", '"').replace("”", '"').replace("’", "'") \
        .encode("latin-1", "replace").decode("latin-1")


class _Documento(FPDF):
    def __init__(self, folio):
        super().__init__(format="Letter")
        self.folio = folio
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)
        self.alias_nb_pages()

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110)
        self.cell(0, 6, _t(f"Cotización {self.folio} · página {self.page_no()} de {{nb}}"), align="C")


COLUMNAS = [("Concepto", 78, "L"), ("Tipo", 30, "L"), ("Cant.", 16, "R"), ("Unidad", 18, "L"),
            ("P. unitario", 22, "R"), ("Importe", 22, "R")]


def _encabezado_tabla(pdf):
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*AZUL)
    pdf.set_text_color(255)
    for titulo, ancho, alineacion in COLUMNAS:
        pdf.cell(ancho, 7, _t(titulo), border=1, align=alineacion, fill=True)
    pdf.ln()
    pdf.set_text_color(0)
    pdf.set_font("Helvetica", "", 9)


def construir_pdf(cotizacion):
    """Regresa los bytes del PDF de la cotización (dict de obtener_cotizacion)."""
    c = cotizacion
    moneda = c["moneda"]
    pdf = _Documento(c["folio"])
    pdf.add_page()

    # Identificación de ACL (CA-20, CA-36)
    logo = c.get("acl_logo_ruta_snapshot")
    x_texto = 15
    if logo and Path(logo).is_file():
        try:
            pdf.image(logo, x=15, y=12, h=22)
            x_texto = 60
        except Exception:  # logo dañado: el documento sigue sin logo
            x_texto = 15
    pdf.set_xy(x_texto, 13)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 8, _t(c["acl_nombre_snapshot"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x_texto)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60)
    pdf.cell(0, 5, _t(f"Tel. {c['acl_telefono_snapshot']} · {c['acl_correo_snapshot']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(38)

    pdf.set_text_color(0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, _t(f"Cotización {c['folio']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _t(f"Fecha: {c['creada_en'][:10]}    Vigente hasta: {c['vigencia_hasta']}    "
                      f"Estatus: {c['estatus']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Cliente
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Cliente", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _t(f"{c['cliente_nombre_snapshot']} · Tel. {c['cliente_telefono_snapshot']}\n"
                            f"Dirección: {c['direccion_snapshot'] or 'Por definir'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Conceptos: el encabezado se repite en cada página y ningún renglón se corta (CA-21)
    _encabezado_tabla(pdf)
    for p in c["partidas"]:
        valores = [p["descripcion_snapshot"], TIPOS.get(p["tipo_snapshot"], p["tipo_snapshot"]),
                   formato_cantidad(p["cantidad_milesimas"]), p["unidad_snapshot"],
                   formato_moneda(p["precio_unitario_centavos"], ""), formato_moneda(p["importe_centavos"], "")]
        lineas = max(len(pdf.multi_cell(ancho - 2, 5, _t(v), dry_run=True, output="LINES"))
                     for v, (_, ancho, _) in zip(valores, COLUMNAS))
        alto = 5 * lineas + 2
        if pdf.get_y() + alto > pdf.h - pdf.b_margin:
            pdf.add_page()
            _encabezado_tabla(pdf)
        y = pdf.get_y()
        x = pdf.l_margin
        for valor, (_, ancho, alineacion) in zip(valores, COLUMNAS):
            pdf.rect(x, y, ancho, alto)
            pdf.set_xy(x + 1, y + 1)
            pdf.multi_cell(ancho - 2, 5, _t(valor), align=alineacion)
            x += ancho
        pdf.set_xy(pdf.l_margin, y + alto)

    # Totales: se mantienen juntos en la misma página (CA-21)
    filas = [("Subtotal", c["subtotal_centavos"]),
             (f"Utilidad ({c['metodo_utilidad']} {c['utilidad_tasa']})", c["utilidad_centavos"]),
             (f"IVA ({c['iva_tasa']})", c["iva_centavos"]), ("Total", c["total_centavos"])]
    if pdf.get_y() + 7 * len(filas) + 4 > pdf.h - pdf.b_margin:
        pdf.add_page()
    pdf.ln(2)
    for etiqueta, valor in filas:
        es_total = etiqueta == "Total"
        pdf.set_font("Helvetica", "B" if es_total else "", 10 if es_total else 9)
        pdf.cell(142, 7, _t(etiqueta), align="R")
        pdf.cell(44, 7, _t(formato_moneda(valor, moneda)), border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    # Condiciones comerciales completas, con sus saltos de línea (CA-64)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Condiciones comerciales", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _t(c["condiciones"] or "Sin condiciones capturadas."), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 5, _t(f"Esta cotización es válida hasta el {c['vigencia_hasta']}. Importes en {moneda}."))
    return bytes(pdf.output())


def generar_pdf(conexion, id_cotizacion, carpeta=None):
    """Genera el PDF, lo guarda y registra su ruta. Regresa la ruta.

    Se escribe primero en un archivo temporal y luego se renombra, así nunca
    queda un PDF vacío o a medias (CA-52). Si falla, lanza ErrorPdf y la
    cotización en la BD no cambia (CA-51).
    """
    cotizacion = almacenamiento_datos.obtener_cotizacion(conexion, id_cotizacion)
    if cotizacion is None:
        raise ErrorPdf(f"No existe la cotización {id_cotizacion}.")
    carpeta = Path(carpeta) if carpeta else CARPETA_SALIDA
    destino = carpeta / f"{cotizacion['folio']}.pdf"
    temporal = None
    try:
        contenido = construir_pdf(cotizacion)
        if not contenido.startswith(b"%PDF"):
            raise ValueError("salida sin formato PDF")
        carpeta.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(dir=carpeta, suffix=".tmp")
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
        os.replace(temporal, destino)
        temporal = None
    except Exception as error:
        raise ErrorPdf(f"No se pudo generar el PDF de {cotizacion['folio']}: {error}. "
                       "La cotización sigue guardada; intente de nuevo.") from error
    finally:
        if temporal and os.path.exists(temporal):
            os.remove(temporal)
    almacenamiento_datos.guardar_pdf_ruta(conexion, id_cotizacion, str(destino))
    return str(destino)


def ruta_pdf_vigente(cotizacion):
    """Ruta del PDF si existe y no está vacío; si no, None (CA-52)."""
    ruta = cotizacion.get("pdf_ruta")
    if ruta and Path(ruta).is_file() and Path(ruta).stat().st_size > 0:
        return ruta
    return None
