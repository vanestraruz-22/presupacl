"""Pruebas de cotizaciones_estado (RF-13) y bloqueo de cerradas (RF-15, CA-27)."""

import pytest

from proyecto.cotizaciones import cotizaciones_estado as est
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.cotizaciones import cotizaciones_creacion as cc
from proyecto.infraestructura import almacenamiento_datos as ad


@pytest.mark.parametrize("nuevo", ["aceptada", "rechazada"])
def test_CA24_pendiente_a_aceptada_o_rechazada(bd_config, cotizacion, nuevo):
    assert est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], nuevo) is True
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["estatus"] == nuevo


def test_CA53_mismo_estatus_no_cambia_datos(bd_config, cotizacion):
    assert est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], "pendiente") is False
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"]) == cotizacion


@pytest.mark.parametrize("nuevo", ["cancelada", "", "ACEPTADA", None])
def test_CA54_estatus_no_permitido_se_rechaza(bd_config, cotizacion, nuevo):
    with pytest.raises(ErrorCotizacion):
        est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], nuevo)
    assert ad.obtener_cotizacion(bd_config, cotizacion["id_cotizacion"])["estatus"] == "pendiente"


def test_cerrada_no_se_reabre(bd_config, cotizacion):
    est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], "rechazada")
    with pytest.raises(ErrorCotizacion) as error:
        est.cambiar_estatus(bd_config, cotizacion["id_cotizacion"], "pendiente")
    assert "duplíquela" in str(error.value)


def test_inexistente(bd_config):
    with pytest.raises(ErrorCotizacion):
        est.cambiar_estatus(bd_config, 999, "aceptada")
