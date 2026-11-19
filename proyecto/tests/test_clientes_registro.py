"""Pruebas unitarias de clientes_registro (RF-02, T-05).

El almacenamiento se reemplaza por un simulador para probar solo la validación.
"""

import pytest

from proyecto.clientes import clientes_registro as cr

NOMBRE = "Cliente de prueba"
TELEFONO = "4770000000"
DIRECCION = "Calle de Prueba 10, León"


class AlmacenamientoSimulado:
    """Registra lo que se le pide guardar, sin tocar ninguna BD."""

    def __init__(self):
        self.llamadas = []

    def crear_cliente_con_direcciones(self, conexion, nombre, telefono, direcciones):
        self.llamadas.append((nombre, telefono, direcciones))
        return 101

    def listar_telefonos_clientes(self, conexion):
        return []  # ningún cliente previo: no hay teléfonos repetidos


@pytest.fixture
def simulado(monkeypatch):
    sim = AlmacenamientoSimulado()
    monkeypatch.setattr(cr, "almacenamiento_datos", sim)
    return sim


# ---------- Casos normales y límite ----------

def test_datos_completos_se_envian_a_guardar(simulado):
    id_cliente = cr.registrar_cliente(None, NOMBRE, TELEFONO, [DIRECCION, "Av. Ficticia 200, León"])
    assert id_cliente == 101
    assert simulado.llamadas == [(NOMBRE, TELEFONO, [DIRECCION, "Av. Ficticia 200, León"])]


def test_limite_espacios_alrededor_se_recortan(simulado):
    cr.registrar_cliente(None, "  Cliente de prueba ", " 4770000000 ", ["  Calle de Prueba 10, León  "])
    assert simulado.llamadas == [(NOMBRE, TELEFONO, [DIRECCION])]


# ---------- CA-05 · PT-02-E: falta nombre o teléfono ----------

@pytest.mark.parametrize(
    "nombre, telefono, faltantes",
    [
        ("", TELEFONO, ["nombre"]),
        (NOMBRE, "", ["telefono"]),
        ("   ", None, ["nombre", "telefono"]),
    ],
)
def test_CA05_campos_faltantes_no_se_guardan(simulado, nombre, telefono, faltantes):
    with pytest.raises(cr.ErrorValidacion) as error:
        cr.registrar_cliente(None, nombre, telefono, [DIRECCION])

    assert error.value.campos_faltantes == faltantes
    assert "No se guardó el cliente" in str(error.value)
    assert simulado.llamadas == []


# ---------- CA-68 · PT-02-E2: sin direcciones o con una en blanco ----------

@pytest.mark.parametrize("direcciones", [[], None, [DIRECCION, "   "]])
def test_CA68_sin_direccion_valida_no_se_guarda(simulado, direcciones):
    with pytest.raises(cr.ErrorValidacion) as error:
        cr.registrar_cliente(None, NOMBRE, TELEFONO, direcciones)

    assert error.value.campos_faltantes == ["direcciones"]
    assert "al menos una dirección" in str(error.value)
    assert simulado.llamadas == []


def test_todos_los_faltantes_se_informan_juntos(simulado):
    with pytest.raises(cr.ErrorValidacion) as error:
        cr.registrar_cliente(None, "", "", [])

    assert error.value.campos_faltantes == ["nombre", "telefono", "direcciones"]
    assert str(error.value) == (
        "Faltan datos obligatorios: nombre, teléfono, al menos una dirección. No se guardó el cliente."
    )
