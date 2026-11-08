"""Pruebas de mensajeria_whatsapp para la cotización (RF-12)."""

import urllib.parse

import pytest

from proyecto.comunicacion import mensajeria_whatsapp as wa


def test_CA22_enlace_con_destinatario_y_resumen(cotizacion):
    enlace = wa.enlace_cotizacion(cotizacion)
    assert enlace.startswith("https://wa.me/524770000000?text=")
    texto = urllib.parse.unquote(enlace.split("text=")[1])
    assert cotizacion["folio"] in texto and "$3,062.40 MXN" in texto and cotizacion["vigencia_hasta"] in texto


@pytest.mark.parametrize("telefono, esperado", [("477 123 4567", "524771234567"), ("+52 477-123-4567", "524771234567"),
                                                 ("5214771234567", "524771234567")])
def test_normalizar_telefono(telefono, esperado):
    assert wa.normalizar_telefono(telefono) == esperado


@pytest.mark.parametrize("telefono", ["", None, "123", "abc"])
def test_CA23_telefono_no_viable_no_genera_enlace(cotizacion, telefono):
    with pytest.raises(wa.ErrorTelefono):
        wa.enlace_cotizacion({**cotizacion, "cliente_telefono_snapshot": telefono})
