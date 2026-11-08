"""Pruebas del PDF (RF-11) y de los datos de ACL en el PDF (RF-21: CA-36, CA-64)."""

import io
import os

import pytest
from pypdf import PdfReader

from proyecto.config import settings
from proyecto.cotizaciones import cotizaciones_creacion as cc
from proyecto.documentos import generador_pdf_cotizacion as gen
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.tests.conftest import CONFIG


def texto_pdf(ruta):
    lector = PdfReader(ruta)
    return "\n".join(p.extract_text() for p in lector.pages), len(lector.pages)


def test_CA20_pdf_incluye_todos_los_datos(bd_config, cotizacion, tmp_path):
    ruta = gen.generar_pdf(bd_config, cotizacion["id_cotizacion"], tmp_path)
    texto, _ = texto_pdf(ruta)
    for esperado in ["ACL Alarmas y Cámaras de León", "4770000000", "contacto@ejemplo.com", cotizacion["folio"],
                     "Cliente de prueba", "Av. Ficticia 200, León", "Cámara de prueba", "Concepto mano_obra",
                     "Subtotal", "Utilidad", "IVA", "Total", "$2,200.00", "$3,062.40 MXN", cotizacion["vigencia_hasta"],
                     "Anticipo del 50 %", "Garantía de 1 año"]:
        assert esperado in texto, esperado
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["pdf_ruta"] == ruta


def test_CA21_dieciseis_conceptos_en_varias_paginas_sin_cortes(bd_config, cliente, conceptos, tmp_path):
    from proyecto.conceptos import conceptos_manuales
    renglones = []
    for i in range(16):
        id_c = conceptos_manuales.registrar_concepto(
            bd_config, "insumos", f"Material número {i + 1:02d} con una descripción larga para ocupar dos líneas "
                                  f"en la columna de concepto del documento", "pieza", "10")
        renglones.append({"id_concepto": id_c, "cantidad": "1"})
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], renglones)
    texto, paginas = texto_pdf(gen.generar_pdf(bd_config, id_cot, tmp_path))
    assert paginas >= 2
    for i in range(16):
        assert f"Material número {i + 1:02d}" in texto
    lector = PdfReader(os.path.join(tmp_path, f"{ad.obtener_cotizacion(bd_config, id_cot)['folio']}.pdf"))
    ultima = lector.pages[-1].extract_text()
    assert all(e in ultima for e in ("Subtotal", "IVA", "Total"))  # totales juntos


def test_CA51_fallo_del_generador_informa_y_conserva_cotizacion(bd_config, cotizacion, tmp_path, monkeypatch):
    def falla(_):
        raise RuntimeError("falla simulada")
    monkeypatch.setattr(gen, "construir_pdf", falla)
    salida = tmp_path / "salida"
    with pytest.raises(gen.ErrorPdf) as error:
        gen.generar_pdf(bd_config, cotizacion["id_cotizacion"], salida)
    assert "sigue guardada" in str(error.value)
    guardada = ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])
    assert guardada["total_centavos"] == cotizacion["total_centavos"] and guardada["pdf_ruta"] is None
    assert not salida.exists() or list(salida.iterdir()) == []  # ni PDF vacío ni temporales


def test_CA36_configuracion_se_usa_en_dos_pdf_sin_pedirla_otra_vez(bd_config, cliente, conceptos, tmp_path):
    from PIL import Image
    logo = tmp_path / "logo.png"
    Image.new("RGB", (60, 30), (31, 78, 121)).save(logo)
    settings.guardar_configuracion(bd_config, {**CONFIG, "logo_ruta": str(logo)})
    for _ in range(2):
        id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])
        ruta = gen.generar_pdf(bd_config, id_cot, tmp_path / "salida")
        texto, _ = texto_pdf(ruta)
        assert "contacto@ejemplo.com" in texto
        assert len(PdfReader(ruta).pages[0].images) == 1  # logo


def test_CA64_condiciones_de_varias_lineas_completas_en_pdf(bd_config, cliente, conceptos, tmp_path):
    lineas = [f"{i}. Condición comercial número {i}, con texto suficiente para revisar que no se recorta." for i in range(1, 13)]
    settings.guardar_configuracion(bd_config, {**CONFIG, "condiciones_default": "\n".join(lineas)})
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])
    texto, _ = texto_pdf(gen.generar_pdf(bd_config, id_cot, tmp_path))
    plano = " ".join(texto.split())
    for linea in lineas:
        assert linea in plano


def test_snapshot_pdf_no_cambia_al_cambiar_configuracion(bd_config, cotizacion, tmp_path):
    settings.guardar_configuracion(bd_config, {**CONFIG, "correo": "nuevo@ejemplo.com"})
    texto, _ = texto_pdf(gen.generar_pdf(bd_config, cotizacion["id_cotizacion"], tmp_path))
    assert "contacto@ejemplo.com" in texto and "nuevo@ejemplo.com" not in texto


def test_ruta_pdf_vigente(cotizacion, tmp_path):
    assert gen.ruta_pdf_vigente(cotizacion) is None
    vacio = tmp_path / "vacio.pdf"
    vacio.write_bytes(b"")
    assert gen.ruta_pdf_vigente({**cotizacion, "pdf_ruta": str(vacio)}) is None
