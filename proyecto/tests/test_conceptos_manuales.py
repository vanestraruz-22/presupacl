"""Pruebas de conceptos_manuales (RF-06): PT-06-N, PT-06-L y PT-06-E."""

import pytest

from proyecto.conceptos import conceptos_manuales as cm
from proyecto.cotizaciones import calculadora_cotizacion as calc
from proyecto.infraestructura import almacenamiento_datos as ad


def test_CA13_registrar_y_modificar_concepto_con_unidad(bd):
    id_concepto = cm.registrar_concepto(bd, "insumos", "Tubo conduit 1/2", "tramo", "45.50")
    cm.modificar_concepto(bd, id_concepto, "insumos", "Tubo conduit 3/4", "tramo", "52.00")

    concepto = ad.obtener_concepto(bd, id_concepto)
    assert (concepto["descripcion"], concepto["unidad"], concepto["precio_unitario_centavos"]) == \
        ("Tubo conduit 3/4", "tramo", 5200)
    assert concepto["origen"] == "manual" and concepto["syscom_id"] is None
    assert calc.importe_centavos(calc.texto_a_milesimas("3"), concepto["precio_unitario_centavos"]) == 15600


def test_CA42_precio_cero_importe_cero(bd):
    id_concepto = cm.registrar_concepto(bd, "programacion", "Configuración de app (cortesía)", "servicio", "0")
    precio = ad.obtener_concepto(bd, id_concepto)["precio_unitario_centavos"]
    assert calc.importe_centavos(1000, precio) == 0


@pytest.mark.parametrize(
    "tipo, descripcion, unidad, precio, campo",
    [("insumos", "", "pieza", "10", "descripcion"), ("insumos", "Cinta", "", "10", "unidad"),
     ("insumos", "Cinta", "pieza", "diez", "precio"), ("otro", "Cinta", "pieza", "10", "tipo"),
     ("insumos", "Cinta", "pieza", "-1", "precio")],
)
def test_CA43_datos_invalidos_se_rechazan_e_indican(bd, tipo, descripcion, unidad, precio, campo):
    with pytest.raises(cm.ErrorConcepto) as error:
        cm.registrar_concepto(bd, tipo, descripcion, unidad, precio)
    assert campo in error.value.errores
    assert cm.listar(bd) == []


def test_modificar_inexistente(bd):
    with pytest.raises(ad.ErrorNoEncontrado):
        cm.modificar_concepto(bd, 999, "insumos", "X", "pieza", "1")
