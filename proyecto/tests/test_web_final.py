"""Pantallas del incremento 5: sincronización, orden de servicio e historial."""

import pytest

from proyecto.cotizaciones import cotizaciones_creacion
from proyecto.conceptos import conceptos_manuales
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.tests.test_web_cotizaciones import entorno, html  # noqa: F401  (fixture compartida)


@pytest.fixture
def cot(entorno, tmp_path):
    entorno["http"].application.config["CARPETA_PDF"] = tmp_path / "pdf"
    con = ad.abrir_conexion(entorno["ruta"])
    id_mo = conceptos_manuales.registrar_concepto(con, "mano_obra", "Instalación de cámara", "servicio", "500")
    direccion = ad.obtener_cliente(con, entorno["id_cliente"])["direcciones"][1]["id_direccion"]
    id_cot, folio = cotizaciones_creacion.crear_cotizacion(con, entorno["id_cliente"], [{"id_concepto": id_mo, "cantidad": "2"}], direccion)
    sin_dir, _ = cotizaciones_creacion.crear_cotizacion(con, entorno["id_cliente"], [{"id_concepto": id_mo, "cantidad": "1"}])
    con.close()
    return {"id": id_cot, "sin_dir": sin_dir, "folio": folio, **entorno}


def test_aceptar_muestra_orden_y_envia_a_tecnico(cot):
    http, t, ruta = cot["http"], cot["token"], f"/cotizaciones/{cot['id']}"
    http.post(ruta + "/estatus", data={"_token": t, "estatus": "aceptada"})
    pagina = html(http.get(ruta))
    assert "Orden de servicio" in pagina and "Calle 2" in pagina and "2 servicio: Instalación de cámara" in pagina
    r = http.get(ruta + "/orden/whatsapp?telefono=4779998888")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/524779998888?text=")
    r = http.get(ruta + "/orden/whatsapp?telefono=")
    assert r.status_code == 302 and "wa.me" not in r.headers["Location"]
    assert "Falta el número" in html(http.get(ruta))


def test_aceptar_sin_direccion_avisa(cot):
    http, t, ruta = cot["http"], cot["token"], f"/cotizaciones/{cot['sin_dir']}"
    http.post(ruta + "/estatus", data={"_token": t, "estatus": "aceptada"})
    pagina = html(http.get(ruta))
    assert "no tiene dirección" in pagina and "Orden de servicio" not in pagina


def test_historial_y_filtros(cot):
    http = cot["http"]
    assert cot["folio"] in html(http.get(f"/clientes/{cot['id_cliente']}/historial"))
    assert http.get("/clientes/999/historial").status_code == 404
    assert "No hay cotizaciones con esos filtros" in html(http.get("/cotizaciones?estatus=rechazada"))
    r = http.get("/cotizaciones?desde=2026-12-31&hasta=2026-01-01")
    assert r.status_code == 400 and "Rango inválido" in html(r) and cot["folio"] in html(r)


def test_sincronizar_desde_panel(cot):
    http, t = cot["http"], cot["token"]
    http.get("/catalogo?texto=cámara")
    http.post("/sincronizar", data={"_token": t})
    assert "Precios de SYSCOM actualizados" in html(http.get("/"))
    cot["simulado"].falla = "limite"
    http.post("/sincronizar", data={"_token": t})
    pagina = html(http.get("/"))
    assert "no se completó" in pagina and "límite de peticiones" in pagina
