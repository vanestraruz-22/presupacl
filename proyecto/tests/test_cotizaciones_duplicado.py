"""Pruebas de cotizaciones_duplicado (RF-15): PT-15-N, PT-15-L, PT-15-D-L y PT-15-D-E."""

import pytest

from proyecto.clientes import clientes_registro
from proyecto.conceptos import conceptos_manuales
from proyecto.cotizaciones import cotizaciones_duplicado as dup
from proyecto.cotizaciones import cotizaciones_estado as est
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos as ad


def contar(bd):
    return bd.execute("SELECT COUNT(*) FROM cotizaciones").fetchone()[0]


@pytest.mark.parametrize("estatus", ["aceptada", "rechazada"])
def test_CA27_1_duplicar_con_precios_vigentes_sin_tocar_original(bd_config, cotizacion, conceptos, estatus):
    est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], estatus)
    original = ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])
    conceptos_manuales.modificar_concepto(bd_config, conceptos["mano_obra"], "mano_obra", "Concepto mano_obra",
                                          "servicio", "520")
    ad.guardar_productos_syscom(bd_config, [{"syscom_id": "DEMO-001", "descripcion": "Cámara de prueba", "unidad": "pieza",
                                             "precio_unitario_centavos": 90000, "moneda": "MXN", "existencia": 5}])

    id_nueva, folio = dup.duplicar(bd_config, cotizacion["id_cotizacion"])
    nueva = ad.obtener_cotizacion(bd_config, id_nueva)
    assert nueva["estatus"] == "pendiente" and nueva["id_origen"] == cotizacion["id_cotizacion"] and folio != cotizacion["folio"]
    assert [(p["id_concepto"], p["cantidad_milesimas"]) for p in nueva["partidas"]] == \
        [(p["id_concepto"], p["cantidad_milesimas"]) for p in original["partidas"]]
    assert [p["precio_unitario_centavos"] for p in nueva["partidas"]] == [90000, 52000]
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"]) == original


def test_CA57_un_concepto_para_otro_cliente_y_direccion(bd_config, cliente, conceptos):
    from proyecto.cotizaciones import cotizaciones_creacion as cc
    id_cot, _ = cc.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": conceptos["mano_obra"], "cantidad": "1"}],
                                    cliente["direcciones"][0]["id_direccion"])  # aceptar exige dirección (RF-16)
    est.cambiar_estatus(bd_config, id_cot, "aceptada")
    otro = clientes_registro.registrar_cliente(bd_config, "Otro cliente", "4771112222", ["Calle Otra 5"])
    dir_otro = ad.obtener_cliente(bd_config, otro)["direcciones"][0]["id_direccion"]

    id_nueva, _ = dup.duplicar(bd_config, id_cot, id_cliente=otro, id_direccion=dir_otro)
    nueva = ad.obtener_cotizacion(bd_config, id_nueva)
    assert (nueva["cliente_nombre_snapshot"], nueva["direccion_snapshot"]) == ("Otro cliente", "Calle Otra 5")
    assert len(nueva["partidas"]) == 1


def test_CA67_senala_cambios_significativos_y_agotados(bd_config, cotizacion, conceptos):
    est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], "aceptada")
    ad.guardar_productos_syscom(bd_config, [{"syscom_id": "DEMO-001", "descripcion": "Cámara de prueba", "unidad": "pieza",
                                             "precio_unitario_centavos": 100000, "moneda": "MXN", "existencia": 0}])
    conceptos_manuales.modificar_concepto(bd_config, conceptos["mano_obra"], "mano_obra", "Concepto mano_obra",
                                          "servicio", "525")  # +5 %: no se señala
    id_nueva, _ = dup.duplicar(bd_config, cotizacion["id_cotizacion"])
    alertas = dup.conceptos_por_revisar(bd_config, ad.obtener_cotizacion(bd_config, id_nueva))
    assert set(alertas) == {conceptos["SYSCOM"]}
    assert "sin existencia" in alertas[conceptos["SYSCOM"]] and "+17.6 %" in alertas[conceptos["SYSCOM"]]


def test_CA66_origen_inexistente_no_crea_copia(bd_config):
    with pytest.raises(ErrorCotizacion):
        dup.duplicar(bd_config, 999)
    assert contar(bd_config) == 0


def test_pendiente_no_se_duplica(bd_config, cotizacion):
    with pytest.raises(ErrorCotizacion):
        dup.duplicar(bd_config, cotizacion["id_cotizacion"])
    assert contar(bd_config) == 1
