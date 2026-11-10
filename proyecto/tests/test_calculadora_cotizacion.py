"""Pruebas de calculadora_cotizacion (RF-08): PT-08-N, PT-08-L y PT-08-E."""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from proyecto.cotizaciones import calculadora_cotizacion as calc


def referencia(partidas, metodo, utilidad, iva):
    """Cálculo independiente en pesos con Decimal, para comparar (CA-17)."""
    def r(x):
        return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    importes = [r(Decimal(c) * Decimal(p)) for c, p in partidas]
    sub = sum(importes)
    util = r(sub * Decimal(utilidad)) if metodo == "recargo" else r(sub / (1 - Decimal(utilidad)) - sub)
    iv = r((sub + util) * Decimal(iva))
    return [int(x * 100) for x in (sub, util, iv, sub + util + iv)]


@pytest.mark.parametrize("metodo", ["recargo", "margen"])
def test_CA17_coincide_con_calculo_de_referencia(metodo):
    datos = [("2", "850.00"), ("1.5", "500.00"), ("3", "99.99"), ("0.25", "1234.57")]
    partidas = [{"cantidad_milesimas": calc.texto_a_milesimas(c), "precio_unitario_centavos": calc.texto_a_centavos(p)}
                for c, p in datos]
    r = calc.calcular(partidas, metodo, "0.20", "0.16")
    assert [r["subtotal_centavos"], r["utilidad_centavos"], r["iva_centavos"], r["total_centavos"]] == \
        referencia(datos, metodo, "0.20", "0.16")


def test_recargo_ejemplo_a_mano():
    r = calc.calcular([{"cantidad_milesimas": 2000, "precio_unitario_centavos": 50000}], "recargo", "0.20", "0.16")
    # 2 × 500 = 1000; utilidad 200; IVA 16 % de 1200 = 192; total 1392
    assert (r["subtotal_centavos"], r["utilidad_centavos"], r["iva_centavos"], r["total_centavos"]) == \
        (100000, 20000, 19200, 139200)


def test_margen_ejemplo_a_mano():
    r = calc.calcular([{"cantidad_milesimas": 1000, "precio_unitario_centavos": 80000}], "margen", "0.20", "0.16")
    # venta = 800 / 0.8 = 1000 → utilidad 200
    assert r["utilidad_centavos"] == 20000


def test_CA45_tres_por_99_99_con_margen_cero_es_exacto():
    r = calc.calcular([{"cantidad_milesimas": 3000, "precio_unitario_centavos": 9999}], "recargo", "0", "0.16")
    assert r["subtotal_centavos"] == 29997
    assert r["utilidad_centavos"] == 0
    assert r["iva_centavos"] == 4800  # 299.97 × 0.16 = 47.9952 → 48.00
    assert r["total_centavos"] == 34797


def test_redondeo_mitad_hacia_arriba():
    assert calc.importe_centavos(500, 1) == 1  # 0.5 centavo → 1
    assert calc.importe_centavos(1500, 333) == 500  # 499.5 → 500


@pytest.mark.parametrize("precio", ["abc", "", None, "12.345", "-5", "NaN", "1e400"])
def test_CA46_precio_no_numerico_se_rechaza(precio):
    with pytest.raises(calc.ErrorCalculo):
        calc.texto_a_centavos(precio)


def test_CA46_calcular_con_precio_invalido_no_regresa_total():
    with pytest.raises(calc.ErrorCalculo):
        calc.calcular([{"cantidad_milesimas": 1000, "precio_unitario_centavos": "abc"}], "recargo", "0.2", "0.16")


@pytest.mark.parametrize("cantidad", ["0", "-1", "dos", "1.0005"])
def test_cantidades_invalidas(cantidad):
    with pytest.raises(calc.ErrorCalculo):
        calc.texto_a_milesimas(cantidad)


def test_conversiones_y_formato():
    assert calc.texto_a_centavos("1,500.50") == 150050
    assert calc.texto_a_centavos("$85") == 8500
    assert calc.texto_a_milesimas("2.5") == 2500
    assert calc.formato_moneda(150050) == "$1,500.50 MXN"
    assert calc.formato_cantidad(2500) == "2.5" and calc.formato_cantidad(1000) == "1"


@pytest.mark.parametrize("metodo, tasa", [("otro", "0.2"), ("recargo", "1"), ("recargo", "x")])
def test_reglas_invalidas(metodo, tasa):
    with pytest.raises(calc.ErrorCalculo):
        calc.calcular([{"cantidad_milesimas": 1000, "precio_unitario_centavos": 100}], metodo, tasa, "0.16")
