"""Datos ficticios compartidos por las pruebas a partir del incremento 3."""

import pytest

from proyecto.clientes import clientes_registro
from proyecto.config import settings
from proyecto.conceptos import conceptos_manuales
from proyecto.infraestructura import almacenamiento_datos as ad

CONFIG = {
    "nombre_comercial": "ACL Alarmas y Cámaras de León",
    "telefono": "4770000000",
    "correo": "contacto@ejemplo.com",
    "condiciones_default": "1. Anticipo del 50 %.\n2. Garantía de 1 año.",
    "vigencia_dias_default": "15",
    "iva_tasa_default": "0.16",
    "utilidad_tasa_default": "0.20",
    "metodo_utilidad": "recargo",
}


@pytest.fixture
def bd(tmp_path):
    """Conexión a una BD temporal con esquema completo."""
    con = ad.abrir_conexion(tmp_path / "prueba.db")
    ad.crear_esquema(con)
    yield con
    con.close()


@pytest.fixture
def bd_config(bd):
    settings.guardar_configuracion(bd, CONFIG)
    return bd


@pytest.fixture
def cliente(bd):
    id_cliente = clientes_registro.registrar_cliente(
        bd, "Cliente de prueba", "4770000000", ["Calle de Prueba 10, León", "Av. Ficticia 200, León"]
    )
    return ad.obtener_cliente(bd, id_cliente)


@pytest.fixture
def conceptos(bd):
    """Un concepto manual de cada tipo, más un producto SYSCOM ficticio."""
    ids = {}
    precios = {"manual": "150.00", "mano_obra": "500.00", "viaticos": "300.00", "insumos": "99.99",
               "programacion": "400.00", "equipo_seguridad": "250.00", "dia_festivo": "200.00"}
    for tipo, precio in precios.items():
        ids[tipo] = conceptos_manuales.registrar_concepto(bd, tipo, f"Concepto {tipo}", "servicio", precio)
    ids["SYSCOM"] = ad.guardar_productos_syscom(bd, [{
        "syscom_id": "DEMO-001", "descripcion": "Cámara de prueba", "unidad": "pieza", "marca": "MarcaDemo",
        "categoria": "Videovigilancia", "precio_unitario_centavos": 85000, "moneda": "MXN", "existencia": 5,
    }])["DEMO-001"]
    return ids


@pytest.fixture
def cotizacion(bd_config, cliente, conceptos):
    """Cotización pendiente con un producto SYSCOM y mano de obra, en la segunda dirección."""
    from proyecto.cotizaciones import cotizaciones_creacion
    id_cot, _ = cotizaciones_creacion.crear_cotizacion(
        bd_config, cliente["id_cliente"],
        [{"id_concepto": conceptos["SYSCOM"], "cantidad": "2"}, {"id_concepto": conceptos["mano_obra"], "cantidad": "1"}],
        cliente["direcciones"][1]["id_direccion"],
    )
    return ad.obtener_cotizacion(bd_config, id_cot)
