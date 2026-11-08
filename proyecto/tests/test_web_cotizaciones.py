"""Pantallas del incremento 3: conceptos, catálogo SYSCOM y cotización nueva."""

import re

import pytest

from proyecto.auth import auth
from proyecto.catalogo.cliente_api_syscom import ClienteSyscomSimulado
from proyecto.clientes import clientes_registro
from proyecto.config import settings
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.main import crear_app
from proyecto.tests.conftest import CONFIG

PRODUCTOS = [{"producto_id": "1", "titulo": "Cámara bala 2MP", "marca": "MarcaA", "categoria": "CCTV",
              "precio": "850.00", "total_existencia": 0}]


@pytest.fixture
def entorno(tmp_path):
    ruta = tmp_path / "web.db"
    simulado = ClienteSyscomSimulado(PRODUCTOS)
    app = crear_app(ruta, secret_key="llave-solo-para-pruebas", cliente_syscom=simulado)
    con = ad.abrir_conexion(ruta)
    auth.crear_usuario(con, "admin", "clave-de-prueba")
    settings.guardar_configuracion(con, CONFIG)
    id_cliente = clientes_registro.registrar_cliente(con, "Cliente de prueba", "4770000000", ["Calle 1", "Calle 2"])
    con.close()
    http = app.test_client()
    t = token(http, "/login")
    assert http.post("/login", data={"_token": t, "usuario": "admin", "password": "clave-de-prueba"}).status_code == 302
    return {"http": http, "ruta": ruta, "id_cliente": id_cliente, "simulado": simulado, "token": t}


def token(http, ruta):
    return re.search(r'name="_token" value="([0-9a-f]+)"', http.get(ruta).get_data(as_text=True)).group(1)


def html(respuesta):
    return respuesta.get_data(as_text=True)


def test_registrar_concepto_manual_y_error(entorno):
    http, t = entorno["http"], entorno["token"]
    r = http.post("/conceptos", data={"_token": t, "tipo": "mano_obra", "descripcion": "Instalación de cámara",
                                      "unidad": "servicio", "precio": "500"})
    assert r.status_code == 302
    assert "Instalación de cámara" in html(http.get("/conceptos"))
    r = http.post("/conceptos", data={"_token": t, "tipo": "mano_obra", "descripcion": "", "unidad": "x", "precio": "a"})
    assert r.status_code == 400 and "No se guardó el concepto" in html(r)


def test_catalogo_muestra_precio_y_existencia_cero(entorno):
    pagina = html(entorno["http"].get("/catalogo?texto=cámara"))
    assert "Cámara bala 2MP" in pagina and "$850.00 MXN" in pagina and ">0<" in pagina


def test_catalogo_con_api_caida_avisa(entorno):
    entorno["simulado"].falla = "no_disponible"
    assert "no está disponible" in html(entorno["http"].get("/catalogo?texto=cámara"))


def test_flujo_completo_de_cotizacion(entorno):
    http, t = entorno["http"], entorno["token"]
    http.post("/conceptos", data={"_token": t, "tipo": "mano_obra", "descripcion": "Instalación",
                                  "unidad": "servicio", "precio": "500"})
    http.get("/catalogo?texto=cámara")  # guarda el producto en el catálogo local
    con = ad.abrir_conexion(entorno["ruta"])
    ids = [c["id_concepto"] for c in ad.buscar_conceptos(con)]
    direccion2 = ad.obtener_cliente(con, entorno["id_cliente"])["direcciones"][1]["id_direccion"]
    con.close()

    assert http.post("/cotizaciones/nueva", data={"_token": t, "id_cliente": entorno["id_cliente"]}).status_code == 302
    # Guardar vacía: RF-20
    r = http.post("/borrador", data={"_token": t, "accion": "guardar", "id_direccion": direccion2})
    assert r.status_code == 400 and "al menos un concepto" in html(r)

    for id_concepto in ids:
        http.post("/borrador/agregar", data={"_token": t, "id_concepto": id_concepto, "cantidad": "2"})
    pagina = html(http.get("/borrador"))
    assert "Total" in pagina and "$2,700.00 MXN" in pagina  # subtotal 2×850 + 2×500

    r = http.post("/borrador", data={"_token": t, "accion": "guardar", "id_direccion": direccion2,
                                     "cantidad": ["2", "0"], "precio": ["", ""]})
    assert r.status_code == 400 and "mayor que cero" in html(r)

    r = http.post("/borrador", data={"_token": t, "accion": "guardar", "id_direccion": direccion2,
                                     "cantidad": ["2", "1"], "precio": ["", "450"]})
    assert r.status_code == 302
    detalle = html(http.get(r.headers["Location"]))
    assert "COT-" in detalle and "pendiente" in detalle and "Calle 2" in detalle
    assert "$2,150.00 MXN" in detalle  # 1700 + 450
    assert "Cliente de prueba" in html(http.get("/cotizaciones"))
    assert "Cotización en captura" not in html(http.get("/"))


def test_quitar_y_descartar(entorno):
    http, t = entorno["http"], entorno["token"]
    http.post("/conceptos", data={"_token": t, "tipo": "insumos", "descripcion": "Cinta", "unidad": "pieza", "precio": "10"})
    http.post("/cotizaciones/nueva", data={"_token": t, "id_cliente": entorno["id_cliente"]})
    http.post("/borrador/agregar", data={"_token": t, "id_concepto": 1})
    http.post("/borrador", data={"_token": t, "quitar": "0", "cantidad": ["1"], "precio": [""]})
    assert "todavía no tiene conceptos" in html(http.get("/borrador"))
    r = http.post("/borrador", data={"_token": t, "accion": "cancelar"})
    assert r.status_code == 302 and http.get("/borrador").status_code == 302


def test_cotizacion_inexistente_404(entorno):
    assert entorno["http"].get("/cotizaciones/999").status_code == 404
