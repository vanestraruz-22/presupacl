"""Pruebas de historial_cotizaciones (RF-18, RF-19)."""

import pytest

from proyecto.clientes import clientes_registro
from proyecto.cotizaciones import cotizaciones_creacion as cc
from proyecto.cotizaciones import cotizaciones_estado as est
from proyecto.historial import historial_cotizaciones as hist
from proyecto.infraestructura import almacenamiento_datos as ad


def nueva(bd, id_cliente, concepto, fecha=None, estatus=None, direccion=None):
    id_cot, _ = cc.crear_cotizacion(bd, id_cliente, [{"id_concepto": concepto, "cantidad": "1"}], direccion)
    if estatus:
        est.cambiar_estatus(bd, id_cot, estatus)
    if fecha:  # fijar la fecha de creación para probar los filtros
        bd.execute("UPDATE cotizaciones SET creada_en = ? WHERE id_cotizacion = ?", (f"{fecha}T10:00:00-06:00", id_cot))
        bd.commit()
    return id_cot


def test_CA32_historial_solo_del_cliente_con_fecha_y_estatus(bd_config, cliente, conceptos):
    otro = clientes_registro.registrar_cliente(bd_config, "Otro", "4771112222", ["Calle Otra"])
    mias = [nueva(bd_config, cliente["id_cliente"], conceptos["mano_obra"]) for _ in range(2)]
    nueva(bd_config, otro, conceptos["mano_obra"])
    r = hist.historial_cliente(bd_config, cliente["id_cliente"])
    assert sorted(c["id_cotizacion"] for c in r["cotizaciones"]) == mias
    assert all(c["creada_en"] and c["estatus"] == "pendiente" for c in r["cotizaciones"])


def test_CA33_cliente_sin_cotizaciones(bd_config, cliente):
    r = hist.historial_cliente(bd_config, cliente["id_cliente"])
    assert r["cotizaciones"] == [] and r["mensaje"] == hist.SIN_COTIZACIONES


def test_CA60_cliente_inexistente(bd_config):
    with pytest.raises(hist.ErrorHistorial) as error:
        hist.historial_cliente(bd_config, 999)
    assert "no existe" in str(error.value)


def test_CA34_filtra_por_estatus_y_rango(bd_config, cliente, conceptos):
    d = cliente["direcciones"][0]["id_direccion"]
    dentro = nueva(bd_config, cliente["id_cliente"], conceptos["mano_obra"], "2026-11-10", "aceptada", d)
    nueva(bd_config, cliente["id_cliente"], conceptos["mano_obra"], "2026-11-10", "rechazada")      # otro estatus
    nueva(bd_config, cliente["id_cliente"], conceptos["mano_obra"], "2026-10-01", "aceptada", d)  # fuera de rango
    r = hist.filtrar(bd_config, "aceptada", "2026-11-01", "2026-11-30")
    assert [c["id_cotizacion"] for c in r["cotizaciones"]] == [dentro]


def test_CA61_mismo_dia_inclusivo(bd_config, cliente, conceptos):
    ids = {f: nueva(bd_config, cliente["id_cliente"], conceptos["mano_obra"], f) for f in ("2026-11-09", "2026-11-10", "2026-11-11")}
    r = hist.filtrar(bd_config, desde="2026-11-10", hasta="2026-11-10")
    assert [c["id_cotizacion"] for c in r["cotizaciones"]] == [ids["2026-11-10"]]
    r = hist.filtrar(bd_config, desde="2026-11-09", hasta="2026-11-11")
    assert len(r["cotizaciones"]) == 3  # ambos extremos incluidos


def test_CA35_rango_invertido_no_filtra(bd_config):
    with pytest.raises(hist.ErrorHistorial) as error:
        hist.filtrar(bd_config, desde="2026-11-30", hasta="2026-11-01")
    assert "Rango inválido" in str(error.value)


@pytest.mark.parametrize("args", [{"estatus": "cancelada"}, {"desde": "30/11/2026"}])
def test_filtros_invalidos(bd_config, args):
    with pytest.raises(hist.ErrorHistorial):
        hist.filtrar(bd_config, **args)


def test_sin_resultados(bd_config):
    assert hist.filtrar(bd_config, "aceptada")["mensaje"] == hist.SIN_RESULTADOS
