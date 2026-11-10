"""Pruebas de ordenes_servicio (RF-16) y del mensaje para el técnico (RF-17)."""

import json
import urllib.parse

import pytest

from proyecto.comunicacion.mensajeria_whatsapp import ErrorTelefono
from proyecto.cotizaciones import cotizaciones_creacion as cc
from proyecto.cotizaciones import cotizaciones_estado as est
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.ordenes import ordenes_servicio as ords


def todos_los_tipos(bd_config, cliente, conceptos, indice_direccion=0):
    renglones = [{"id_concepto": i, "cantidad": "2"} for i in conceptos.values()]
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], renglones,
                                    cliente["direcciones"][indice_direccion]["id_direccion"])
    return id_cot


def test_CA28_aceptar_genera_orden_sin_precios(bd_config, cliente, conceptos):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    orden = ords.obtener(bd_config, id_cot)
    assert orden["cliente_nombre_snapshot"] == "Cliente de prueba"
    assert {t["descripcion"] for t in orden["tareas"]} == {
        "Cámara de prueba", "Concepto manual", "Concepto insumos", "Concepto equipo_seguridad",
        "Concepto programacion", "Concepto mano_obra"}
    sin_cobros = json.dumps(orden, ensure_ascii=False).lower()
    for prohibido in ("precio", "importe", "total", "iva", "utilidad", "centavos\": 8", "$"):
        assert prohibido not in sin_cobros.replace("cantidad_milesimas", "")


def test_CA58_usa_la_direccion_elegida(bd_config, cliente, conceptos):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos, indice_direccion=1)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    orden = ords.obtener(bd_config, id_cot)
    assert orden["direccion_snapshot"] == "Av. Ficticia 200, León"
    assert orden["id_direccion"] == cliente["direcciones"][1]["id_direccion"]


def test_CA29_sin_direccion_no_acepta_ni_genera_orden(bd_config, cliente, conceptos):
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])
    with pytest.raises(ErrorCotizacion) as error:
        est.cambiar_estatus(bd_config, id_cot, "aceptada")
    assert "dirección" in str(error.value)
    assert ad.obtener_cotizacion(bd_config, id_cot)["estatus"] == "pendiente"
    assert ords.obtener(bd_config, id_cot) is None


def test_solo_viaticos_no_genera_orden(bd_config, cliente, conceptos):
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["viaticos"], "cantidad": "1"}],
                                    cliente["direcciones"][0]["id_direccion"])
    with pytest.raises(ErrorCotizacion):
        est.cambiar_estatus(bd_config, id_cot, "aceptada")
    assert ad.obtener_cotizacion(bd_config, id_cot)["estatus"] == "pendiente"


def test_falla_al_guardar_orden_revierte_aceptacion(bd_config, cliente, conceptos):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos)
    bd_config.execute("CREATE TRIGGER romper BEFORE INSERT ON ordenes_servicio BEGIN SELECT RAISE(ABORT, 'x'); END")
    with pytest.raises(ErrorCotizacion):
        est.cambiar_estatus(bd_config, id_cot, "aceptada")
    assert ad.obtener_cotizacion(bd_config, id_cot)["estatus"] == "pendiente"


def test_una_sola_orden_por_cotizacion(bd_config, cliente, conceptos):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    assert est.cambiar_estatus(bd_config, id_cot, "aceptada") is False
    assert bd_config.execute("SELECT COUNT(*) FROM ordenes_servicio").fetchone()[0] == 1


def test_CA30_mensaje_para_tecnico_sin_importes(bd_config, cliente, conceptos):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    folio = ad.obtener_cotizacion(bd_config, id_cot)["folio"]
    enlace = ords.enlace_tecnico(ords.obtener(bd_config, id_cot), folio, "477 999 8888")
    assert enlace.startswith("https://wa.me/524779998888?text=")
    texto = urllib.parse.unquote(enlace.split("text=")[1])
    assert "Av." not in texto and "Calle de Prueba 10, León" in texto
    assert "$" not in texto and "MXN" not in texto and "IVA" not in texto and "Total" not in texto


def test_CA59_orden_con_un_solo_concepto(bd_config, cliente, conceptos):
    id_cot, folio = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}],
                                        cliente["direcciones"][0]["id_direccion"])
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    texto = ords.mensaje_tecnico(ords.obtener(bd_config, id_cot), folio)
    assert "- 1 servicio: Concepto mano_obra" in texto and "Calle de Prueba 10, León" in texto


@pytest.mark.parametrize("telefono", ["", None, "12345"])
def test_CA31_tecnico_sin_telefono_no_genera_enlace(bd_config, cliente, conceptos, telefono):
    id_cot = todos_los_tipos(bd_config, cliente, conceptos)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    with pytest.raises(ErrorTelefono):
        ords.enlace_tecnico(ords.obtener(bd_config, id_cot), "COT", telefono)
