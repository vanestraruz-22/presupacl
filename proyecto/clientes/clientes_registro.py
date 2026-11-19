"""clientes_registro: registrar y editar clientes con sus direcciones (RF-02, RF-03).

Responsabilidad (sección 2.5 de la especificación v2.5): validar los datos que
captura el usuario y pedir el guardado a almacenamiento_datos. Este módulo no
ejecuta SQL.

Contrato acordado en T-02 (plan de implementación v1.2):
    registrar_cliente(conexion, nombre, telefono, direcciones) -> id_cliente
    Si faltan datos, lanza ErrorValidacion con la lista de campos faltantes y
    no llama al almacenamiento.
    editar_cliente(conexion, id_cliente, nombre, telefono,
                   direcciones_editadas, direcciones_nuevas)   (incremento 2)

D07 (decidido por el equipo el 19-nov-2026): NO se permiten teléfonos
repetidos entre clientes. Se comparan solo los dígitos, así "477 123 4567" y
"477-123-4567" cuentan como el mismo; con 12 dígitos que empiezan con 52 (lada
de México) se comparan los últimos 10.
SUPUESTO: nombre, teléfono y direcciones se recortan de espacios; un valor
vacío o solo con espacios cuenta como faltante. Los límites de textos siguen
por validar.
"""

from proyecto.infraestructura import almacenamiento_datos

# Nombres que se muestran al usuario en el mensaje de error.
ETIQUETAS = {"nombre": "nombre", "telefono": "teléfono", "direcciones": "al menos una dirección"}


class ErrorValidacion(Exception):
    """Faltan datos obligatorios; no se guardó nada (CA-05, CA-68)."""

    def __init__(self, campos_faltantes, mensaje=None):
        self.campos_faltantes = campos_faltantes
        etiquetas = ", ".join(ETIQUETAS[c] for c in campos_faltantes)
        super().__init__(mensaje or f"Faltan datos obligatorios: {etiquetas}. No se guardó el cliente.")


def _limpiar(texto):
    """Quita espacios al inicio y al final; None se trata como vacío."""
    return (texto or "").strip()


def validar_cliente(nombre, telefono, direcciones):
    """Regresa la lista de campos faltantes (vacía si todo está completo)."""
    faltantes = []
    if not _limpiar(nombre):
        faltantes.append("nombre")
    if not _limpiar(telefono):
        faltantes.append("telefono")
    # CA-68: se necesita al menos una dirección y ninguna puede venir en blanco.
    if not direcciones or any(not _limpiar(d) for d in direcciones):
        faltantes.append("direcciones")
    return faltantes


def _digitos(telefono):
    digitos = "".join(c for c in str(telefono or "") if c.isdigit())
    return digitos[2:] if len(digitos) == 12 and digitos.startswith("52") else digitos


def revisar_telefono_unico(conexion, telefono, id_cliente=None):
    """Lanza ErrorValidacion si otro cliente ya tiene ese teléfono (D07)."""
    buscado = _digitos(telefono)
    if not buscado:
        return
    for otro_id, otro_telefono in almacenamiento_datos.listar_telefonos_clientes(conexion):
        if otro_id != id_cliente and _digitos(otro_telefono) == buscado:
            otro = almacenamiento_datos.obtener_cliente(conexion, otro_id)
            raise ErrorValidacion(["telefono"], f"El teléfono {_limpiar(telefono)} ya está registrado con el "
                                  f"cliente {otro['nombre']}. No se guardó; búsquelo en Clientes.")


def registrar_cliente(conexion, nombre, telefono, direcciones):
    """Valida los datos y guarda el cliente con sus direcciones (RF-02).

    Regresa el id_cliente creado. Si falta algún dato lanza ErrorValidacion
    con todos los campos faltantes juntos (CA-05, CA-68).
    """
    faltantes = validar_cliente(nombre, telefono, direcciones)
    if faltantes:
        raise ErrorValidacion(faltantes)
    revisar_telefono_unico(conexion, telefono)

    return almacenamiento_datos.crear_cliente_con_direcciones(
        conexion,
        _limpiar(nombre),
        _limpiar(telefono),
        [_limpiar(d) for d in direcciones],
    )


def editar_cliente(conexion, id_cliente, nombre, telefono, direcciones_editadas=None, direcciones_nuevas=None):
    """Valida y guarda los cambios de un cliente existente (RF-03).

    direcciones_editadas: {id_direccion: texto}. Ninguna puede quedar en blanco,
    así el cliente conserva siempre direcciones válidas (CA-39).
    direcciones_nuevas: textos a agregar; los renglones vacíos se ignoran
    porque el formulario siempre muestra un campo extra (CA-07).

    Si el cliente no existe, almacenamiento_datos lanza ErrorNoEncontrado y
    no se crea otro cliente (CA-08).
    """
    direcciones_editadas = direcciones_editadas or {}
    faltantes = []
    if not _limpiar(nombre):
        faltantes.append("nombre")
    if not _limpiar(telefono):
        faltantes.append("telefono")
    if faltantes:
        raise ErrorValidacion(faltantes, "Faltan datos obligatorios: "
                              + ", ".join(ETIQUETAS[c] for c in faltantes)
                              + ". No se guardaron los cambios.")
    if any(not _limpiar(d) for d in direcciones_editadas.values()):
        raise ErrorValidacion(["direcciones"], "Una dirección no puede quedar en blanco. No se guardaron los cambios.")
    if almacenamiento_datos.obtener_cliente(conexion, int(id_cliente)) is not None:  # si no existe: CA-08
        revisar_telefono_unico(conexion, telefono, int(id_cliente))

    almacenamiento_datos.actualizar_cliente(
        conexion,
        id_cliente,
        _limpiar(nombre),
        _limpiar(telefono),
        {int(i): _limpiar(d) for i, d in direcciones_editadas.items()},
        [_limpiar(d) for d in (direcciones_nuevas or []) if _limpiar(d)],
    )
