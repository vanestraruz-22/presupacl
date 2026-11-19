"""T-34: catálogo local en CSV en lugar de la API de SYSCOM (RF-05, RF-09, RF-10)."""

import io

import pytest

from proyecto.auth import auth
from proyecto.catalogo import catalogo_syscom, cliente_api_syscom as api, sincronizador_precios_syscom as sinc
from proyecto.config import settings
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.main import crear_app
from proyecto.tests.conftest import CONFIG
from proyecto.tests.test_web_cotizaciones import html, token

CSV = (
    "clave,descripcion,marca,categoria,unidad,precio,existencia\n"
    "CAM-1,Cámara bala 2 MP,Hikvision,Videovigilancia,pieza,389.00,40\n"
    "DVR-1,Grabador DVR 8 canales,Hikvision,Videovigilancia,pieza,\"$1,390.00\",0\n"
    "ALA-1,Sensor PIR,DSC,Alarmas,pieza,215,\n"
)


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "catalogo.csv"
    ruta.write_text(CSV, encoding="utf-8")
    return ruta


def test_csv_incluido_en_el_proyecto_es_valido():
    productos = api.ClienteCatalogoLocal().buscar_productos()
    assert len(productos) >= 30
    assert all(api.normalizar_producto(p)["precio_unitario_centavos"] > 0 for p in productos)


def test_busqueda_local_guarda_productos_y_precio(bd, archivo):
    cliente = api.ClienteCatalogoLocal(str(archivo))
    r = catalogo_syscom.buscar_productos(bd, cliente, texto="grabador")
    assert r["fuente"] == "syscom" and r["aviso"] is None
    (dvr,) = r["resultados"]
    assert (dvr["syscom_id"], dvr["precio_unitario_centavos"], dvr["existencia"]) == ("DVR-1", 139000, 0)
    todos = catalogo_syscom.buscar_productos(bd, cliente, todos=True)["resultados"]
    assert sorted(p["syscom_id"] for p in todos) == ["ALA-1", "CAM-1", "DVR-1"]
    assert next(p for p in todos if p["syscom_id"] == "ALA-1")["existencia"] is None


def test_sin_filtros_ni_todos_es_error(bd, archivo):
    with pytest.raises(catalogo_syscom.ErrorCatalogo):
        catalogo_syscom.buscar_productos(bd, api.ClienteCatalogoLocal(str(archivo)))


def test_sincronizar_toma_precio_nuevo_del_csv(bd, archivo):
    cliente = api.ClienteCatalogoLocal(str(archivo))
    catalogo_syscom.buscar_productos(bd, cliente, todos=True)
    archivo.write_text(CSV.replace("389.00", "420.00").replace("ALA-1,", "ALA-9,"), encoding="utf-8")
    r = sinc.sincronizar(bd, cliente)
    assert r["resultado"] == "exitosa" and "ALA-1" in r["detalle"]
    (cam,) = ad.buscar_conceptos(bd, origen="syscom", texto="bala")
    assert cam["precio_unitario_centavos"] == 42000


def test_archivo_faltante_conserva_datos_y_avisa(bd, archivo):
    cliente = api.ClienteCatalogoLocal(str(archivo))
    catalogo_syscom.buscar_productos(bd, cliente, todos=True)
    archivo.unlink()
    r = catalogo_syscom.buscar_productos(bd, cliente, texto="cámara")
    assert r["fuente"] == "local" and "no está disponible" in r["aviso"] and len(r["resultados"]) == 1
    assert sinc.sincronizar(bd, cliente)["resultado"] == "fallida"


def test_punto_y_coma_de_excel():
    texto = "﻿clave;descripcion;precio\nX-1;Cable UTP;2290,00\n".replace("2290,00", "2290.00")
    (p,) = api.leer_csv_catalogo(texto)
    assert api.normalizar_producto(p)["precio_unitario_centavos"] == 229000


@pytest.mark.parametrize("texto, mensaje", [
    ("clave,descripcion\nA,Algo\n", "columnas obligatorias: precio"),
    ("clave,descripcion,precio\nA,Algo,abc\n", "Fila 2"),
    ("clave,descripcion,precio\nA,Algo,-5\n", "Fila 2"),
    ("clave,descripcion,precio\nA,Algo,5\nA,Otro,6\n", "Fila 3: la clave A está repetida"),
    ("clave,descripcion,precio\n,Sin clave,5\n", "Fila 2"),
    ("clave,descripcion,precio,existencia\nA,Algo,5,-1\n", "existencia negativa"),
    ("clave,descripcion,precio\n", "no tiene productos"),
])
def test_csv_invalido_se_rechaza_con_la_fila(texto, mensaje):
    with pytest.raises(api.ErrorApiSyscom, match=mensaje):
        api.leer_csv_catalogo(texto)


def test_reemplazar_invalido_no_toca_el_archivo(archivo):
    cliente = api.ClienteCatalogoLocal(str(archivo))
    with pytest.raises(api.ErrorApiSyscom):
        cliente.reemplazar_archivo("clave,descripcion,precio\nA,Algo,xx\n")
    assert archivo.read_text(encoding="utf-8") == CSV
    assert cliente.reemplazar_archivo("clave,descripcion,precio\nN-1,Nuevo,10\n") == 1
    assert cliente.obtener_producto("N-1")["titulo"] == "Nuevo"
    with pytest.raises(api.ErrorApiSyscom) as error:
        cliente.obtener_producto("CAM-1")
    assert error.value.tipo == "no_encontrado"


# ---------- Página web ----------
@pytest.fixture
def web(tmp_path, archivo):
    ruta = tmp_path / "web.db"
    app = crear_app(ruta, secret_key="llave-solo-para-pruebas", cliente_syscom=api.ClienteCatalogoLocal(str(archivo)))
    con = ad.abrir_conexion(ruta)
    auth.crear_usuario(con, "admin", "clave-de-prueba")
    settings.guardar_configuracion(con, CONFIG)
    con.close()
    http = app.test_client()
    t = token(http, "/login")
    http.post("/login", data={"_token": t, "usuario": "admin", "password": "clave-de-prueba"})
    return {"http": http, "token": t, "archivo": archivo}


def test_pagina_catalogo_local_ver_todo_y_descargar(web):
    http = web["http"]
    pagina = html(http.get("/catalogo?todos=1"))
    assert "catalogo_local.csv" in pagina and "Sensor PIR" in pagina and "Grabador DVR" in pagina
    r = http.get("/catalogo/archivo")
    assert r.status_code == 200 and "CAM-1" in r.get_data(as_text=True)


def test_importar_csv_valido_actualiza_precios(web):
    http, t = web["http"], web["token"]
    http.get("/catalogo?todos=1")
    nuevo = CSV.replace("389.00", "450.00").encode("utf-8")
    r = http.post("/catalogo/importar", data={"_token": t, "archivo": (io.BytesIO(nuevo), "nuevo.csv")},
                  content_type="multipart/form-data", follow_redirects=True)
    pagina = html(r)
    assert "Catálogo importado con 3 producto(s)" in pagina and "$450.00" in pagina


def test_importar_csv_invalido_no_cambia_nada(web):
    http, t = web["http"], web["token"]
    malo = b"clave,descripcion,precio\nA,Algo,abc\n"
    r = http.post("/catalogo/importar", data={"_token": t, "archivo": (io.BytesIO(malo), "malo.csv")},
                  content_type="multipart/form-data", follow_redirects=True)
    assert "No se importó el catálogo: Fila 2" in html(r)
    assert web["archivo"].read_text(encoding="utf-8") == CSV
    r = http.post("/catalogo/importar", data={"_token": t}, content_type="multipart/form-data",
                  follow_redirects=True)
    assert "Seleccione un archivo CSV" in html(r)


def test_importar_sin_token_ni_catalogo_local(web, tmp_path):
    http = web["http"]
    r = http.post("/catalogo/importar", data={"archivo": (io.BytesIO(b"x"), "x.csv")},
                  content_type="multipart/form-data")
    assert r.status_code == 400
    otra = crear_app(tmp_path / "otra.db", secret_key="x", cliente_syscom=None).test_client()
    assert otra.get("/catalogo/archivo").status_code == 302  # pide sesión antes que nada
