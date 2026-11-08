"""Pruebas del sincronizador (RF-09, RF-10) con SYSCOM simulado y reloj controlado."""

from datetime import datetime, timedelta

import pytest

from proyecto.catalogo import cliente_api_syscom as api
from proyecto.catalogo import sincronizador_precios_syscom as sinc
from proyecto.infraestructura import almacenamiento_datos as ad

PRODUCTOS = [{"producto_id": "1", "titulo": "Cámara", "precio": "850.00", "total_existencia": 10},
             {"producto_id": "2", "titulo": "DVR", "precio": "2450.00", "total_existencia": 3}]


@pytest.fixture
def catalogo(bd):
    simulado = api.ClienteSyscomSimulado(PRODUCTOS)
    ad.guardar_productos_syscom(bd, [api.normalizar_producto(p) for p in PRODUCTOS])
    return simulado


def precios(bd):
    return {c["syscom_id"]: (c["precio_unitario_centavos"], c["existencia"]) for c in ad.buscar_conceptos(bd, "syscom")}


def test_CA18_actualiza_precio_existencia_y_fecha_de_exito(bd, catalogo):
    catalogo.productos["1"].update(precio="900.00", total_existencia=0)
    r = sinc.sincronizar(bd, catalogo)
    assert r["resultado"] == "exitosa"
    assert precios(bd) == {"1": (90000, 0), "2": (245000, 3)}
    assert sinc.estado(bd)["ultima_exitosa"] is not None and sinc.estado(bd)["aviso"] is None


def test_CA47_en_24_horas_ocurre_al_menos_una_sincronizacion(tmp_path, catalogo, bd):
    ruta = tmp_path / "prueba.db"
    programador = sinc.ProgramadorSincronizacion(lambda: ad.abrir_conexion(ruta), lambda: catalogo)
    inicio = datetime.now().astimezone()
    resultados = [programador.revisar(inicio + timedelta(hours=h)) for h in range(0, 25)]  # revisión cada hora
    exitosas = [r for r in resultados if r and r["resultado"] == "exitosa"]
    assert len(exitosas) >= 1
    assert resultados[1] is None  # no repite antes de 24 horas


def test_debe_sincronizar_respeta_intervalos(bd, catalogo):
    ahora = datetime.now().astimezone()
    assert sinc.debe_sincronizar(bd, ahora)
    sinc.sincronizar(bd, catalogo)
    assert not sinc.debe_sincronizar(bd, ahora + timedelta(hours=23))
    assert sinc.debe_sincronizar(bd, ahora + timedelta(hours=25))


@pytest.mark.parametrize("corrupto", [{"precio": "N/D"}, {"precio": "-5"}, {"titulo": ""}])
def test_CA48_respuesta_invalida_no_sobrescribe(bd, catalogo, corrupto):
    antes = precios(bd)
    catalogo.productos["1"]["precio"] = "999.00"   # este sí vendría bien…
    catalogo.productos["2"].update(corrupto)       # …pero otro viene corrupto
    r = sinc.sincronizar(bd, catalogo)
    assert r["resultado"] == "fallida" and precios(bd) == antes


def test_CA19_api_caida_conserva_datos_y_avisa(bd, catalogo):
    antes = precios(bd)
    catalogo.falla = "no_disponible"
    assert sinc.sincronizar(bd, catalogo)["resultado"] == "fallida"
    assert precios(bd) == antes
    assert "no se completó" in sinc.estado(bd)["aviso"]


def test_CA49_primera_ejecucion_sin_datos_y_api_caida(bd):
    r = sinc.sincronizar(bd, api.ClienteSyscomSimulado(falla="no_disponible"))
    assert r["resultado"] == "fallida"
    assert "conceptos manuales" in sinc.estado(bd)["aviso"]
    assert sinc.estado(bd)["ultima_exitosa"] is None
    assert sinc.sincronizar(bd, None)["resultado"] == "fallida"  # sin credenciales


def test_CA49_aun_sin_api_se_cotizan_conceptos_manuales(bd_config, cliente):
    from proyecto.conceptos import conceptos_manuales
    from proyecto.cotizaciones import cotizaciones_creacion
    sinc.sincronizar(bd_config, api.ClienteSyscomSimulado(falla="no_disponible"))
    id_mo = conceptos_manuales.registrar_concepto(bd_config, "mano_obra", "Instalación", "servicio", "500")
    id_cot, _ = cotizaciones_creacion.crear_cotizacion(bd_config, cliente["id_cliente"], [{"id_concepto": id_mo, "cantidad": "1"}])
    assert id_cot


def test_CA50_limite_de_peticiones_avisa_y_conserva(bd, catalogo):
    antes = precios(bd)
    catalogo.falla = "limite"
    r = sinc.sincronizar(bd, catalogo)
    assert r["resultado"] == "fallida" and "límite de peticiones" in r["detalle"]
    assert precios(bd) == antes


def test_reintento_una_hora_despues_de_falla(bd, catalogo):
    catalogo.falla = "no_disponible"
    ahora = datetime.now().astimezone()
    sinc.sincronizar(bd, catalogo)
    assert not sinc.debe_sincronizar(bd, ahora + timedelta(minutes=30))
    assert sinc.debe_sincronizar(bd, ahora + timedelta(minutes=61))


def test_producto_que_ya_no_existe_se_conserva(bd, catalogo):
    del catalogo.productos["2"]
    r = sinc.sincronizar(bd, catalogo)
    assert r["resultado"] == "exitosa" and "ya no aparecen" in r["detalle"]
    assert precios(bd)["2"] == (245000, 3)


def test_programador_no_se_cae_si_hay_error(tmp_path):
    def rota():
        raise RuntimeError("bd no disponible")
    programador = sinc.ProgramadorSincronizacion(rota, lambda: None)
    assert programador.revisar() is None
