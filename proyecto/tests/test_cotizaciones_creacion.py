"""Pruebas de creación de cotizaciones (RF-07) y validador (RF-20)."""

import pytest

from proyecto.cotizaciones import cotizaciones_creacion as cc
from proyecto.cotizaciones import validador_cotizacion as val
from proyecto.infraestructura import almacenamiento_datos as ad


def contar(bd):
    return bd.execute("SELECT COUNT(*) FROM cotizaciones").fetchone()[0]


def test_CA14_ocho_tipos_y_uno_repetido_se_guarda_pendiente(bd_config, cliente, conceptos):
    renglones = [{"id_concepto": i, "cantidad": "1"} for i in conceptos.values()]
    renglones.append({"id_concepto": conceptos["mano_obra"], "cantidad": "2"})
    id_cot, folio = cc.crear_cotizacion(bd_config, cliente["id_cliente"], renglones,
                                        cliente["direcciones"][0]["id_direccion"])

    cot = ad.obtener_cotizacion(bd_config, id_cot)
    assert cot["estatus"] == "pendiente" and folio.startswith("COT-") and folio.endswith("-0001")
    assert {p["tipo_snapshot"] for p in cot["partidas"]} == set(cc.TIPOS)
    assert len(cot["partidas"]) == 9
    assert cot["subtotal_centavos"] == sum(p["importe_centavos"] for p in cot["partidas"])
    assert cot["direccion_snapshot"] == "Calle de Prueba 10, León"
    assert cot["acl_correo_snapshot"] == "contacto@ejemplo.com"
    assert "Garantía" in cot["condiciones"]


def test_CA44_solo_mano_de_obra_sin_syscom(bd_config, cliente, conceptos):
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"],
                                    [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])
    cot = ad.obtener_cotizacion(bd_config, id_cot)
    assert [p["tipo_snapshot"] for p in cot["partidas"]] == ["mano_obra"]
    assert cot["total_centavos"] == 69600  # 500 + 20 % + 16 %


@pytest.mark.parametrize("cantidad", ["0", "-1", 0, -1000])
def test_CA16_cantidad_cero_o_negativa_se_rechaza(bd_config, cliente, conceptos, cantidad):
    with pytest.raises(val.ErrorCotizacion):
        cc.crear_cotizacion(bd_config, cliente["id_cliente"], [
            {"id_concepto": conceptos["mano_obra"], "cantidad": "1"},
            {"id_concepto": conceptos["insumos"], "cantidad": cantidad},
        ])
    assert contar(bd_config) == 0


def test_CA62_un_concepto_valido_permite_guardar(bd_config, cliente, conceptos):
    cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])
    assert contar(bd_config) == 1


def test_CA15_cotizacion_vacia_se_rechaza(bd_config, cliente):
    with pytest.raises(val.ErrorCotizacion) as error:
        cc.crear_cotizacion(bd_config, cliente["id_cliente"], [])
    assert str(error.value) == val.MENSAJE_SIN_CONCEPTOS
    assert contar(bd_config) == 0


def test_CA63_validador_detecta_lista_sin_conceptos():
    with pytest.raises(val.ErrorCotizacion):
        val.validar_partidas([])
    val.validar_partidas([{"id_concepto": 1, "cantidad_milesimas": 1000}])


def test_precio_personalizado_y_snapshot(bd_config, cliente, conceptos):
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"],
                                    [{"id_concepto": conceptos["SYSCOM"], "cantidad": "2", "precio": "800"}])
    partida = ad.obtener_cotizacion(bd_config, id_cot)["partidas"][0]
    assert (partida["precio_unitario_centavos"], partida["importe_centavos"]) == (80000, 160000)


def test_folios_consecutivos(bd_config, cliente, conceptos):
    folios = [cc.crear_cotizacion(bd_config, cliente["id_cliente"],
                                  [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}])[1] for _ in range(2)]
    assert folios[0][-4:] == "0001" and folios[1][-4:] == "0002"


@pytest.mark.parametrize("caso", ["sin_config", "cliente", "direccion", "concepto", "precio"])
def test_errores_no_guardan_nada(bd, cliente, conceptos, caso):
    from proyecto.config import settings
    from proyecto.tests.conftest import CONFIG
    if caso != "sin_config":
        settings.guardar_configuracion(bd, CONFIG)
    otro = ad.crear_cliente_con_direcciones(bd, "Otro", "1", ["Ajena"])
    args = {"id_cliente": cliente["id_cliente"], "renglones": [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}]}
    if caso == "cliente":
        args["id_cliente"] = 999
    if caso == "direccion":
        args["id_direccion"] = ad.obtener_cliente(bd, otro)["direcciones"][0]["id_direccion"]
    if caso == "concepto":
        args["renglones"] = [{"id_concepto": 999, "cantidad": "1"}]
    if caso == "precio":
        args["renglones"][0]["precio"] = "abc"
    with pytest.raises(val.ErrorCotizacion):
        cc.crear_cotizacion(bd, **args)
    assert contar(bd) == 0
