"""Pruebas de edición de clientes (RF-03): PT-03-N, PT-03-L y PT-03-E.

Usan una BD SQLite temporal real porque la edición depende de qué direcciones
pertenecen a qué cliente.
"""

import pytest

from proyecto.clientes import clientes_registro as cr
from proyecto.infraestructura import almacenamiento_datos as ad


@pytest.fixture
def conexion(tmp_path):
    con = ad.abrir_conexion(tmp_path / "prueba.db")
    ad.crear_esquema(con)
    yield con
    con.close()


@pytest.fixture
def cliente(conexion):
    id_cliente = cr.registrar_cliente(conexion, "Cliente de prueba", "4770000000", ["Calle de Prueba 10, León"])
    return ad.obtener_cliente(conexion, id_cliente)


def contar(conexion, tabla):
    return conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


def test_CA07_editar_telefono_y_agregar_direccion(conexion, cliente):
    cr.editar_cliente(conexion, cliente["id_cliente"], "Cliente de prueba", "4771111111",
                      direcciones_nuevas=["Av. Ficticia 200, León", "   "])

    editado = ad.obtener_cliente(conexion, cliente["id_cliente"])
    assert editado["telefono"] == "4771111111"
    assert [d["direccion"] for d in editado["direcciones"]] == ["Calle de Prueba 10, León", "Av. Ficticia 200, León"]
    assert editado["actualizado_en"] >= cliente["actualizado_en"]


def test_CA39_editar_la_unica_direccion_conserva_una_valida(conexion, cliente):
    id_dir = cliente["direcciones"][0]["id_direccion"]
    cr.editar_cliente(conexion, cliente["id_cliente"], "Cliente de prueba", "4770000000",
                      {id_dir: "  Calle Corregida 12, León "})

    direcciones = ad.obtener_cliente(conexion, cliente["id_cliente"])["direcciones"]
    assert direcciones == [{"id_direccion": id_dir, "direccion": "Calle Corregida 12, León"}]


def test_CA39_la_unica_direccion_no_puede_quedar_en_blanco(conexion, cliente):
    id_dir = cliente["direcciones"][0]["id_direccion"]
    with pytest.raises(cr.ErrorValidacion):
        cr.editar_cliente(conexion, cliente["id_cliente"], "Cliente de prueba", "4770000000", {id_dir: "  "})

    assert ad.obtener_cliente(conexion, cliente["id_cliente"])["direcciones"][0]["direccion"] == "Calle de Prueba 10, León"


def test_CA08_cliente_inexistente_informa_error_sin_crear_otro(conexion, cliente):
    with pytest.raises(ad.ErrorNoEncontrado):
        cr.editar_cliente(conexion, 9999, "Otro", "4770000000", direcciones_nuevas=["Calle Nueva 1"])

    assert contar(conexion, "clientes") == 1
    assert contar(conexion, "direcciones_cliente") == 1


def test_direccion_de_otro_cliente_revierte_todo(conexion, cliente):
    otro = cr.registrar_cliente(conexion, "Otro cliente", "4772222222", ["Calle Ajena 5"])
    dir_ajena = ad.obtener_cliente(conexion, otro)["direcciones"][0]["id_direccion"]

    with pytest.raises(ad.ErrorNoEncontrado):
        cr.editar_cliente(conexion, cliente["id_cliente"], "Cliente de prueba", "4779999999",
                          {dir_ajena: "Robada"}, ["Calle Nueva 1"])

    assert ad.obtener_cliente(conexion, cliente["id_cliente"])["telefono"] == "4770000000"
    assert ad.obtener_cliente(conexion, otro)["direcciones"][0]["direccion"] == "Calle Ajena 5"
    assert contar(conexion, "direcciones_cliente") == 2


@pytest.mark.parametrize("nombre, telefono", [("", "4770000000"), ("Cliente", "  ")])
def test_editar_sin_nombre_o_telefono_no_guarda(conexion, cliente, nombre, telefono):
    with pytest.raises(cr.ErrorValidacion) as error:
        cr.editar_cliente(conexion, cliente["id_cliente"], nombre, telefono)
    assert "No se guardaron los cambios" in str(error.value)
    assert ad.obtener_cliente(conexion, cliente["id_cliente"])["nombre"] == "Cliente de prueba"


# ---------- D07 (equipo, 19-nov-2026): no se permiten teléfonos repetidos ----------

@pytest.mark.parametrize("telefono", ["4770000000", "477 000 0000", "477-000-0000", "+52 477 000 0000"])
def test_D07_registrar_telefono_repetido_se_rechaza(conexion, cliente, telefono):
    with pytest.raises(cr.ErrorValidacion) as error:
        cr.registrar_cliente(conexion, "Otro", telefono, ["Calle 9"])
    assert error.value.campos_faltantes == ["telefono"] and "ya está registrado" in str(error.value)
    assert contar(conexion, "clientes") == 1


def test_D07_editar_con_telefono_de_otro_se_rechaza_y_el_propio_si(conexion, cliente):
    otro = cr.registrar_cliente(conexion, "Otro cliente", "4772222222", ["Calle Ajena 5"])
    with pytest.raises(cr.ErrorValidacion):
        cr.editar_cliente(conexion, otro, "Otro cliente", "477 000 0000")
    assert ad.obtener_cliente(conexion, otro)["telefono"] == "4772222222"
    cr.editar_cliente(conexion, otro, "Otro cliente renombrado", "4772222222")  # su mismo teléfono: válido
    assert ad.obtener_cliente(conexion, otro)["nombre"] == "Otro cliente renombrado"
