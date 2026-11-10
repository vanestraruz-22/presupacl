"""Pruebas de cotizaciones_edicion (RF-14) y bloqueo de cerradas (CA-27)."""

import pytest
from pypdf import PdfReader

from proyecto.cotizaciones import cotizaciones_edicion as ed
from proyecto.cotizaciones import cotizaciones_estado as est
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos as ad


def test_CA26_editar_conceptos_cantidades_y_precios_recalcula_y_regenera_pdf(bd_config, cotizacion, conceptos, tmp_path):
    renglones = ed.renglones_de(cotizacion)
    renglones[0]["cantidad"] = "3"                      # cantidad
    renglones[1]["precio"] = "600"                      # precio
    renglones.append({"id_concepto": conceptos["viaticos"], "cantidad": "1"})  # concepto nuevo
    resultado = ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], renglones, carpeta_pdf=tmp_path)

    editada = ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])
    assert editada["subtotal_centavos"] == 3 * 85000 + 60000 + 30000
    assert editada["total_centavos"] == 480240  # 3450 × 1.2 × 1.16
    assert resultado["aviso"] is None and editada["pdf_ruta"] == resultado["pdf_ruta"]
    texto = PdfReader(resultado["pdf_ruta"]).pages[0].extract_text()
    assert "$4,802.40 MXN" in texto and "Concepto viaticos" in texto


def test_CA55_unico_concepto_a_cantidad_uno(bd_config, cliente, conceptos, tmp_path):
    from proyecto.cotizaciones import cotizaciones_creacion as cc
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "4"}])
    ed.editar_cotizacion(bd_config, id_cot, [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}], carpeta_pdf=tmp_path)
    assert ad.obtener_cotizacion(bd_config, id_cot)["subtotal_centavos"] == 50000


def test_CA56_falla_al_guardar_no_declara_exito(bd_config, cotizacion, tmp_path, monkeypatch):
    def falla(*_):
        raise ad.ErrorAlmacenamiento("disco lleno")
    monkeypatch.setattr(ed.almacenamiento_datos, "reemplazar_partidas", falla)
    renglones = ed.renglones_de(cotizacion)
    renglones[0]["cantidad"] = "9"
    with pytest.raises(ErrorCotizacion) as error:
        ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], renglones, carpeta_pdf=tmp_path)
    assert "No se guardaron los cambios" in str(error.value)
    monkeypatch.undo()
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"]) == cotizacion


def test_CA56_falla_real_de_bd_revierte_partidas(bd_config, cotizacion, tmp_path):
    bd_config.execute("CREATE TRIGGER romper BEFORE INSERT ON detalle_cotizacion BEGIN SELECT RAISE(ABORT, 'x'); END")
    with pytest.raises(ErrorCotizacion):
        ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], ed.renglones_de(cotizacion), carpeta_pdf=tmp_path)
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["partidas"] == cotizacion["partidas"]


def test_CA63_quitar_el_ultimo_concepto_no_guarda(bd_config, cotizacion, tmp_path):
    with pytest.raises(ErrorCotizacion):
        ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], [], carpeta_pdf=tmp_path)
    assert len(ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["partidas"]) == 2


@pytest.mark.parametrize("estatus", ["aceptada", "rechazada"])
def test_CA27_cerrada_no_se_edita_y_avisa(bd_config, cotizacion, tmp_path, estatus):
    est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], estatus)
    renglones = ed.renglones_de(cotizacion)
    renglones[0]["cantidad"] = "10"
    with pytest.raises(ErrorCotizacion) as error:
        ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], renglones, carpeta_pdf=tmp_path)
    assert "duplíquela" in str(error.value)
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["partidas"] == cotizacion["partidas"]


def test_pdf_falla_pero_cambios_quedan_guardados(bd_config, cotizacion, tmp_path, monkeypatch):
    from proyecto.documentos import generador_pdf_cotizacion as gen
    monkeypatch.setattr(gen, "construir_pdf", lambda _: (_ for _ in ()).throw(RuntimeError("x")))
    renglones = ed.renglones_de(cotizacion)
    renglones[0]["cantidad"] = "5"
    resultado = ed.editar_cotizacion(bd_config, cotizacion["id_cotizacion"], renglones, carpeta_pdf=tmp_path)
    assert "PDF no se regeneró" in resultado["aviso"]
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["partidas"][0]["cantidad_milesimas"] == 5000
