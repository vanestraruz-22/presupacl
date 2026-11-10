"""Pruebas de catalogo_syscom y cliente_api_syscom (RF-05) con SYSCOM simulado."""

import pytest

from proyecto.catalogo import catalogo_syscom as cat
from proyecto.catalogo import cliente_api_syscom as api
from proyecto.infraestructura import almacenamiento_datos as ad

PRODUCTOS = [
    {"producto_id": "1", "titulo": "Cámara bala 2MP", "marca": "MarcaA", "categoria": "Videovigilancia",
     "precio": "850.00", "total_existencia": 10},
    {"producto_id": "2", "titulo": "DVR 8 canales", "marca": "MarcaB", "categoria": "Videovigilancia",
     "precio": "2450.00", "total_existencia": 0},
    {"producto_id": "3", "titulo": "Sensor PIR", "marca": "MarcaA", "categoria": "Alarmas",
     "precio": "320.50", "total_existencia": 60},
]


@pytest.fixture
def simulado():
    return api.ClienteSyscomSimulado(PRODUCTOS)


@pytest.mark.parametrize(
    "filtros, esperados",
    [({"texto": "cámara"}, ["Cámara bala 2MP"]), ({"categoria": "alarmas"}, ["Sensor PIR"]),
     ({"marca": "MarcaA"}, ["Cámara bala 2MP", "Sensor PIR"])],
)
def test_CA11_buscar_por_palabra_categoria_o_marca_con_precio_y_existencia(bd, simulado, filtros, esperados):
    r = cat.buscar_productos(bd, simulado, **filtros)
    assert r["fuente"] == "syscom" and r["aviso"] is None
    assert [p["descripcion"] for p in r["resultados"]] == esperados
    assert all(p["precio_unitario_centavos"] > 0 and p["existencia"] is not None for p in r["resultados"])


def test_CA41_existencia_cero_se_muestra_como_cero(bd, simulado):
    producto = cat.buscar_productos(bd, simulado, texto="DVR")["resultados"][0]
    assert producto["existencia"] == 0


def test_busqueda_guarda_en_catalogo_sin_duplicar(bd, simulado):
    cat.buscar_productos(bd, simulado, texto="Cámara")
    simulado.productos["1"]["precio"] = "900.00"
    cat.buscar_productos(bd, simulado, texto="Cámara")
    filas = ad.buscar_conceptos(bd, origen="syscom")
    assert len(filas) == 1 and filas[0]["precio_unitario_centavos"] == 90000


@pytest.mark.parametrize("falla", ["no_disponible", "limite"])
def test_CA12_api_caida_avisa_y_usa_datos_previos(bd, simulado, falla):
    cat.buscar_productos(bd, simulado, texto="Sensor")
    simulado.falla = falla
    r = cat.buscar_productos(bd, simulado, texto="Sensor")
    assert r["fuente"] == "local"
    assert "no está disponible" in r["aviso"] and "conceptos manuales" in r["aviso"]
    assert [p["descripcion"] for p in r["resultados"]] == ["Sensor PIR"]


def test_CA12_sin_credenciales_avisa(bd):
    r = cat.buscar_productos(bd, None, texto="Sensor")
    assert r["resultados"] == [] and "credenciales" in r["aviso"]


def test_productos_invalidos_se_omiten(bd):
    sim = api.ClienteSyscomSimulado(PRODUCTOS + [{"producto_id": "9", "titulo": "Sin precio", "precio": "N/D"}])
    r = cat.buscar_productos(bd, sim, texto="i")
    assert "omitieron 1" in r["aviso"]


def test_busqueda_sin_filtros_se_rechaza(bd, simulado):
    with pytest.raises(cat.ErrorCatalogo):
        cat.buscar_productos(bd, simulado)


@pytest.mark.parametrize("crudo", [
    {"producto_id": "", "titulo": "X", "precio": "1"}, {"producto_id": "1", "titulo": "", "precio": "1"},
    {"producto_id": "1", "titulo": "X", "precio": "-1"}, {"producto_id": "1", "titulo": "X", "precio": None},
    {"producto_id": "1", "titulo": "X", "precio": "1", "total_existencia": "muchos"}, "no-es-dict",
])
def test_normalizar_rechaza_datos_corruptos(crudo):
    with pytest.raises(api.ErrorApiSyscom) as error:
        api.normalizar_producto(crudo)
    assert error.value.tipo == "respuesta_invalida"


def test_normalizar_formato_documentado():
    p = api.normalizar_producto({"producto_id": 77, "titulo": "Cámara", "precios": {"precio_descuento": "1,234.5"},
                                 "categorias": [{"nombre": "CCTV"}], "total_existencia": "3"})
    assert (p["syscom_id"], p["precio_unitario_centavos"], p["categoria"], p["existencia"]) == ("77", 123450, "CCTV", 3)


def test_cliente_configurado_por_entorno(monkeypatch):
    monkeypatch.delenv("SYSCOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("PRESUPACL_SYSCOM", raising=False)
    assert api.obtener_cliente_configurado() is None
    monkeypatch.setenv("PRESUPACL_SYSCOM", "demo")
    assert isinstance(api.obtener_cliente_configurado(), api.ClienteSyscomSimulado)
    monkeypatch.delenv("PRESUPACL_SYSCOM")
    monkeypatch.setenv("SYSCOM_CLIENT_ID", "id-ficticio")
    monkeypatch.setenv("SYSCOM_CLIENT_SECRET", "secreto-ficticio")
    assert isinstance(api.obtener_cliente_configurado(), api.ClienteApiSyscom)
