"""Pruebas de configuracion_acl (RF-21).

PT-21-N y PT-21-L se completan en el incremento 4 cuando exista el PDF; aquí se
prueba que la configuración se guarda una vez y se recupera completa.
"""

import pytest

from proyecto.config import settings
from proyecto.infraestructura import almacenamiento_datos as ad

CONDICIONES = "1. Precios en MXN.\n2. Anticipo del 50 %.\n\n3. Garantía de 1 año en equipo."

DATOS = {
    "nombre_comercial": "ACL Alarmas y Cámaras de León",
    "telefono": "4770000000",
    "correo": "contacto@ejemplo.com",
    "condiciones_default": CONDICIONES,
    "vigencia_dias_default": "15",
    "iva_tasa_default": "0.16",
    "utilidad_tasa_default": "0.20",
    "metodo_utilidad": "recargo",
}


@pytest.fixture
def conexion(tmp_path):
    con = ad.abrir_conexion(tmp_path / "prueba.db")
    ad.crear_esquema(con)
    yield con
    con.close()


def test_CA36_configuracion_se_guarda_una_vez_y_se_reutiliza(conexion):
    assert not settings.configuracion_completa(conexion)
    settings.guardar_configuracion(conexion, DATOS)

    for _ in range(2):  # dos lecturas posteriores sin volver a capturar
        config = settings.obtener_configuracion(conexion)
        assert config["telefono"] == "4770000000"
        assert config["vigencia_dias_default"] == 15
    assert settings.configuracion_completa(conexion)


def test_CA64_condiciones_de_varias_lineas_se_conservan_completas(conexion):
    settings.guardar_configuracion(conexion, {**DATOS, "condiciones_default": CONDICIONES.replace("\n", "\r\n")})
    assert settings.obtener_configuracion(conexion)["condiciones_default"] == CONDICIONES


def test_guardar_de_nuevo_reemplaza_el_unico_registro(conexion):
    settings.guardar_configuracion(conexion, DATOS)
    settings.guardar_configuracion(conexion, {**DATOS, "telefono": "4771111111"})
    assert conexion.execute("SELECT COUNT(*) FROM configuracion_acl").fetchone()[0] == 1
    assert settings.obtener_configuracion(conexion)["telefono"] == "4771111111"


def test_CA65_falla_al_guardar_informa_error_y_no_declara_exito(conexion, monkeypatch):
    settings.guardar_configuracion(conexion, DATOS)

    def falla(*_):
        raise ad.ErrorAlmacenamiento("disco lleno")

    monkeypatch.setattr(settings.almacenamiento_datos, "guardar_configuracion", falla)
    with pytest.raises(settings.ErrorConfiguracion) as error:
        settings.guardar_configuracion(conexion, {**DATOS, "telefono": "4779999999"})
    assert str(error.value) == settings.MENSAJE_FALLA
    assert settings.obtener_configuracion(conexion)["telefono"] == "4770000000"


def test_CA65_falla_real_de_bd_revierte(conexion):
    settings.guardar_configuracion(conexion, DATOS)
    conexion.execute("CREATE TRIGGER bloquear BEFORE UPDATE ON configuracion_acl BEGIN SELECT RAISE(ABORT, 'falla'); END")
    with pytest.raises(settings.ErrorConfiguracion):
        settings.guardar_configuracion(conexion, {**DATOS, "telefono": "4779999999"})
    assert settings.obtener_configuracion(conexion)["telefono"] == "4770000000"


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("telefono", " "), ("correo", "sin-arroba"), ("vigencia_dias_default", "0"),
        ("vigencia_dias_default", "abc"), ("iva_tasa_default", "16"), ("iva_tasa_default", "-0.1"),
        ("utilidad_tasa_default", "x"), ("metodo_utilidad", "otro"),
    ],
)
def test_datos_invalidos_no_se_guardan(conexion, campo, valor):
    with pytest.raises(settings.ErrorConfiguracion) as error:
        settings.guardar_configuracion(conexion, {**DATOS, campo: valor})
    assert campo in error.value.campos
    assert not settings.configuracion_completa(conexion)


def test_sin_configuracion_se_proponen_valores_iniciales(conexion):
    assert settings.obtener_configuracion(conexion)["iva_tasa_default"] == "0.16"


def test_guardar_logo_conserva_copias_y_valida_extension(tmp_path):
    ruta1 = settings.guardar_logo(b"png1", "logo.PNG", tmp_path)
    ruta2 = settings.guardar_logo(b"png2", "logo.png", tmp_path)
    assert ruta1 != ruta2 and len(list(tmp_path.iterdir())) == 2
    with pytest.raises(settings.ErrorConfiguracion):
        settings.guardar_logo(b"x", "logo.exe", tmp_path)


def test_D01_utilidad_por_defecto_es_margen():
    from proyecto.cotizaciones import calculadora_cotizacion as calc
    assert settings.VALORES_INICIALES["metodo_utilidad"] == "margen"
    r = calc.calcular([{"cantidad_milesimas": 1000, "precio_unitario_centavos": 80000}], "margen", "0.20", "0.16")
    assert (r["utilidad_centavos"], r["iva_centavos"], r["total_centavos"]) == (20000, 16000, 116000)
