"""Pantallas del incremento 4: PDF, WhatsApp, estatus, edición y duplicado."""

import pytest

from proyecto.cotizaciones import cotizaciones_creacion
from proyecto.infraestructura import almacenamiento_datos as ad
from proyecto.conceptos import conceptos_manuales
from proyecto.tests.test_web_cotizaciones import entorno, html  # noqa: F401  (fixture compartida)


@pytest.fixture
def cot(entorno, tmp_path):
    app = entorno["http"].application
    app.config["CARPETA_PDF"] = tmp_path / "pdf"
    con = ad.abrir_conexion(entorno["ruta"])
    id_mo = conceptos_manuales.registrar_concepto(con, "mano_obra", "Instalación", "servicio", "500")
    id_cot, folio = cotizaciones_creacion.crear_cotizacion(con, entorno["id_cliente"], [{"id_concepto": id_mo, "cantidad": "2"}])
    con.close()
    return {"id": id_cot, "folio": folio, "id_mo": id_mo, **entorno}


def test_pdf_se_genera_y_descarga(cot):
    r = cot["http"].get(f"/cotizaciones/{cot['id']}/pdf?descargar=1")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert f"{cot['folio']}.pdf" in r.headers["Content-Disposition"]


def test_CA52_pdf_fallido_no_entrega_archivo_vacio(cot, monkeypatch):
    from proyecto.documentos import generador_pdf_cotizacion as gen
    monkeypatch.setattr(gen, "construir_pdf", lambda _: (_ for _ in ()).throw(RuntimeError("falla")))
    r = cot["http"].get(f"/cotizaciones/{cot['id']}/pdf")
    assert r.status_code == 500 and "No se pudo generar el PDF" in html(r)
    assert not r.data.startswith(b"%PDF")


def test_whatsapp_redirige_a_wa_me(cot):
    r = cot["http"].get(f"/cotizaciones/{cot['id']}/whatsapp")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/524770000000?text=")


def test_editar_y_bloqueo_al_cerrar(cot):
    http, t, ruta = cot["http"], cot["token"], f"/cotizaciones/{cot['id']}"
    r = http.post(ruta + "/editar", data={"_token": t, "accion": "guardar", "id_concepto": [cot["id_mo"]],
                                           "cantidad": ["3"], "precio": ["500"]})
    assert r.status_code == 302
    assert "$1,500.00 MXN" in html(http.get(ruta))

    r = http.post(ruta + "/editar", data={"_token": t, "accion": "guardar", "id_concepto": [cot["id_mo"]],
                                           "cantidad": ["1"], "precio": [""], "quitar": ["0"]})
    assert r.status_code == 400 and "al menos un concepto" in html(r)

    http.post(ruta + "/estatus", data={"_token": t, "estatus": "rechazada"})
    pagina = html(http.get(ruta))
    assert "rechazada" in pagina and "Duplicar" in pagina and "Marcar aceptada" not in pagina
    r = http.get(ruta + "/editar")
    assert r.status_code == 302
    assert "duplíquela" in html(http.get(ruta))


def test_estatus_invalido_en_pantalla(cot):
    cot["http"].post(f"/cotizaciones/{cot['id']}/estatus", data={"_token": cot["token"], "estatus": "cancelada"})
    assert "no permitido" in html(cot["http"].get(f"/cotizaciones/{cot['id']}"))


def test_duplicar_desde_pantalla(cot):
    http, t = cot["http"], cot["token"]
    http.post(f"/cotizaciones/{cot['id']}/estatus", data={"_token": t, "estatus": "aceptada"})
    con = ad.abrir_conexion(cot["ruta"])
    direccion = ad.obtener_cliente(con, cot["id_cliente"])["direcciones"][1]["id_direccion"]
    con.close()
    assert "Duplicar para Calle 2" in html(http.get(f"/cotizaciones/{cot['id']}/duplicar"))
    r = http.post(f"/cotizaciones/{cot['id']}/duplicar", data={"_token": t, "id_cliente": cot["id_cliente"],
                                                                "id_direccion": direccion})
    assert r.status_code == 302
    nueva = html(http.get(r.headers["Location"]))
    assert "pendiente" in nueva and "Calle 2" in nueva and "Duplicada de" in nueva
