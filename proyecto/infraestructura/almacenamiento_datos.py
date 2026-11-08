"""almacenamiento_datos: único módulo de PresupACL que accede a la base de datos.

Responsabilidad (sección 3.8 de la especificación v2.5): centralizar la conexión
a SQLite, las consultas parametrizadas, las transacciones y la integridad
referencial. Ningún otro módulo debe ejecutar SQL.

Cada tabla se agrega en el incremento que la usa:
- Incremento 1 (RF-02): clientes, direcciones_cliente.
- Incremento 2 (RF-01, RF-21): usuarios, configuracion_acl.
- Incremento 3 (RF-05 a RF-08, RF-20): conceptos, cotizaciones, detalle_cotizacion.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# data/presupacl.db en la raíz del repositorio. Las pruebas pasan su propia ruta.
RUTA_BD_PREDETERMINADA = Path(__file__).resolve().parents[2] / "data" / "presupacl.db"

# Esquema según el diccionario de datos (sección 3.4 de v2.5).
# Los CHECK evitan guardar textos vacíos aunque un módulo se salte la validación.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente      INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
    telefono        TEXT NOT NULL CHECK (length(trim(telefono)) > 0),
    creado_en       TEXT NOT NULL,
    actualizado_en  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS direcciones_cliente (
    id_direccion    INTEGER PRIMARY KEY,
    id_cliente      INTEGER NOT NULL REFERENCES clientes (id_cliente),
    direccion       TEXT NOT NULL CHECK (length(trim(direccion)) > 0)
);

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario      INTEGER PRIMARY KEY,
    usuario         TEXT NOT NULL UNIQUE CHECK (length(trim(usuario)) > 0),
    password_hash   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracion_acl (
    id_configuracion        INTEGER PRIMARY KEY CHECK (id_configuracion = 1),
    nombre_comercial        TEXT NOT NULL CHECK (length(trim(nombre_comercial)) > 0),
    telefono                TEXT NOT NULL CHECK (length(trim(telefono)) > 0),
    correo                  TEXT NOT NULL CHECK (length(trim(correo)) > 0),
    logo_ruta               TEXT,
    condiciones_default     TEXT NOT NULL,
    vigencia_dias_default   INTEGER NOT NULL CHECK (vigencia_dias_default > 0),
    iva_tasa_default        TEXT NOT NULL,
    utilidad_tasa_default   TEXT NOT NULL,
    metodo_utilidad         TEXT NOT NULL CHECK (metodo_utilidad IN ('margen', 'recargo'))
);

CREATE TABLE IF NOT EXISTS conceptos (
    id_concepto               INTEGER PRIMARY KEY,
    origen                    TEXT NOT NULL CHECK (origen IN ('syscom', 'manual')),
    syscom_id                 TEXT,
    tipo                      TEXT NOT NULL CHECK (tipo IN ('SYSCOM', 'manual', 'mano_obra', 'viaticos',
                                  'insumos', 'programacion', 'equipo_seguridad', 'dia_festivo')),
    descripcion               TEXT NOT NULL CHECK (length(trim(descripcion)) > 0),
    unidad                    TEXT NOT NULL CHECK (length(trim(unidad)) > 0),
    marca                     TEXT,
    categoria                 TEXT,
    precio_unitario_centavos  INTEGER NOT NULL CHECK (precio_unitario_centavos >= 0),
    moneda                    TEXT NOT NULL,
    existencia                INTEGER,
    creado_en                 TEXT NOT NULL,
    actualizado_en            TEXT NOT NULL,
    CHECK ((origen = 'syscom') = (syscom_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_conceptos_syscom_id ON conceptos (syscom_id) WHERE origen = 'syscom';
CREATE INDEX IF NOT EXISTS ix_conceptos_busqueda ON conceptos (origen, categoria, marca);

CREATE TABLE IF NOT EXISTS cotizaciones (
    id_cotizacion               INTEGER PRIMARY KEY,
    folio                       TEXT NOT NULL UNIQUE,
    id_cliente                  INTEGER NOT NULL REFERENCES clientes (id_cliente),
    id_direccion                INTEGER REFERENCES direcciones_cliente (id_direccion),
    id_origen                   INTEGER REFERENCES cotizaciones (id_cotizacion),
    creada_en                   TEXT NOT NULL,
    actualizada_en              TEXT NOT NULL,
    estatus                     TEXT NOT NULL CHECK (estatus IN ('pendiente', 'aceptada', 'rechazada')),
    moneda                      TEXT NOT NULL,
    cliente_nombre_snapshot     TEXT NOT NULL,
    cliente_telefono_snapshot   TEXT NOT NULL,
    direccion_snapshot          TEXT,
    acl_nombre_snapshot         TEXT NOT NULL,
    acl_telefono_snapshot       TEXT NOT NULL,
    acl_correo_snapshot         TEXT NOT NULL,
    acl_logo_ruta_snapshot      TEXT,
    condiciones                 TEXT NOT NULL,
    vigencia_hasta              TEXT NOT NULL,
    metodo_utilidad             TEXT NOT NULL CHECK (metodo_utilidad IN ('margen', 'recargo')),
    utilidad_tasa               TEXT NOT NULL,
    iva_tasa                    TEXT NOT NULL,
    subtotal_centavos           INTEGER NOT NULL CHECK (subtotal_centavos >= 0),
    utilidad_centavos           INTEGER NOT NULL CHECK (utilidad_centavos >= 0),
    iva_centavos                INTEGER NOT NULL CHECK (iva_centavos >= 0),
    total_centavos              INTEGER NOT NULL CHECK (total_centavos >= 0),
    pdf_ruta                    TEXT
);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_cliente ON cotizaciones (id_cliente, creada_en);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_estatus ON cotizaciones (estatus, creada_en);

CREATE TABLE IF NOT EXISTS detalle_cotizacion (
    id_detalle                INTEGER PRIMARY KEY,
    id_cotizacion             INTEGER NOT NULL REFERENCES cotizaciones (id_cotizacion),
    id_concepto               INTEGER NOT NULL REFERENCES conceptos (id_concepto),
    descripcion_snapshot      TEXT NOT NULL,
    tipo_snapshot             TEXT NOT NULL,
    unidad_snapshot           TEXT NOT NULL,
    cantidad_milesimas        INTEGER NOT NULL CHECK (cantidad_milesimas > 0),
    precio_unitario_centavos  INTEGER NOT NULL CHECK (precio_unitario_centavos >= 0),
    importe_centavos          INTEGER NOT NULL CHECK (importe_centavos >= 0)
);
CREATE INDEX IF NOT EXISTS ix_detalle_cotizacion ON detalle_cotizacion (id_cotizacion);
"""


class ErrorAlmacenamiento(Exception):
    """Error al leer o escribir en la base de datos."""


class ErrorNoEncontrado(ErrorAlmacenamiento):
    """El registro que se quiere modificar no existe."""


def abrir_conexion(ruta_bd=None):
    """Abre la base de datos con las llaves foráneas activadas.

    SQLite trae las llaves foráneas apagadas por defecto, por eso se activan
    en cada conexión (prueba P11). Si la carpeta no existe, se crea.
    """
    ruta = Path(ruta_bd) if ruta_bd else RUTA_BD_PREDETERMINADA
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.row_factory = sqlite3.Row
    return conexion


def crear_esquema(conexion):
    """Crea las tablas si no existen. Se puede llamar varias veces sin perder datos."""
    conexion.executescript(ESQUEMA)


def _ahora_iso():
    """Fecha y hora local del servidor en ISO 8601 (supuesto de D08, por validar con ACL)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def crear_cliente_con_direcciones(conexion, nombre, telefono, direcciones):
    """Guarda un cliente y todas sus direcciones en una sola transacción (RF-02).

    Recibe datos ya validados por clientes_registro. Si cualquier INSERT falla,
    se revierte todo y no queda un cliente a medias (prueba P12). Todas las
    consultas son parametrizadas (prueba P13).

    Regresa el id_cliente creado o lanza ErrorAlmacenamiento.
    """
    if not direcciones:
        # Barrera de integridad: un cliente sin dirección no se guarda (CA-68).
        raise ErrorAlmacenamiento("El cliente debe tener al menos una dirección; no se guardó.")

    ahora = _ahora_iso()
    try:
        with conexion:  # confirma al terminar o revierte si hay excepción
            cursor = conexion.execute(
                "INSERT INTO clientes (nombre, telefono, creado_en, actualizado_en) VALUES (?, ?, ?, ?)",
                (nombre, telefono, ahora, ahora),
            )
            id_cliente = cursor.lastrowid
            for direccion in direcciones:
                conexion.execute(
                    "INSERT INTO direcciones_cliente (id_cliente, direccion) VALUES (?, ?)",
                    (id_cliente, direccion),
                )
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el cliente; no se guardó ningún dato.") from error
    return id_cliente


def obtener_cliente(conexion, id_cliente):
    """Consulta un cliente con sus direcciones. Regresa None si no existe."""
    fila = conexion.execute(
        "SELECT id_cliente, nombre, telefono, creado_en, actualizado_en FROM clientes WHERE id_cliente = ?",
        (id_cliente,),
    ).fetchone()
    if fila is None:
        return None

    direcciones = conexion.execute(
        "SELECT id_direccion, direccion FROM direcciones_cliente WHERE id_cliente = ? ORDER BY id_direccion",
        (id_cliente,),
    ).fetchall()

    cliente = dict(fila)
    cliente["direcciones"] = [dict(d) for d in direcciones]
    return cliente


def actualizar_cliente(conexion, id_cliente, nombre, telefono, direcciones_editadas, direcciones_nuevas):
    """Edita un cliente existente en una sola transacción (RF-03).

    direcciones_editadas: {id_direccion: texto nuevo}; cada id debe pertenecer
    al cliente. direcciones_nuevas: lista de textos a agregar. No se borran
    direcciones, así el cliente siempre conserva al menos una (CA-39) y las
    cotizaciones que ya las usan no pierden la referencia.

    Si el cliente no existe lanza ErrorNoEncontrado y no crea nada (CA-08).
    """
    try:
        with conexion:
            cursor = conexion.execute(
                "UPDATE clientes SET nombre = ?, telefono = ?, actualizado_en = ? WHERE id_cliente = ?",
                (nombre, telefono, _ahora_iso(), id_cliente),
            )
            if cursor.rowcount == 0:
                raise ErrorNoEncontrado(f"No existe el cliente {id_cliente}; no se guardaron cambios.")
            for id_direccion, direccion in direcciones_editadas.items():
                cursor = conexion.execute(
                    "UPDATE direcciones_cliente SET direccion = ? WHERE id_direccion = ? AND id_cliente = ?",
                    (direccion, id_direccion, id_cliente),
                )
                if cursor.rowcount == 0:
                    raise ErrorNoEncontrado(
                        f"La dirección {id_direccion} no pertenece al cliente {id_cliente}; no se guardaron cambios."
                    )
            for direccion in direcciones_nuevas:
                conexion.execute(
                    "INSERT INTO direcciones_cliente (id_cliente, direccion) VALUES (?, ?)",
                    (id_cliente, direccion),
                )
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudieron guardar los cambios del cliente.") from error


def _patron_like(texto):
    """Convierte el texto buscado en un patrón LIKE escapando % y _."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def buscar_clientes(conexion, texto, limite=50):
    """Busca clientes cuyo nombre o teléfono contenga el texto (RF-04).

    Sin distinguir mayúsculas (LIKE de SQLite, letras sin acento). Regresa una
    lista de {id_cliente, nombre, telefono, num_direcciones} ordenada por nombre.
    Si la BD falla lanza ErrorAlmacenamiento; nunca regresa resultados parciales.
    """
    patron = _patron_like(texto)
    try:
        filas = conexion.execute(
            """
            SELECT c.id_cliente, c.nombre, c.telefono, COUNT(d.id_direccion) AS num_direcciones
            FROM clientes c LEFT JOIN direcciones_cliente d ON d.id_cliente = c.id_cliente
            WHERE c.nombre LIKE ? ESCAPE '\\' OR c.telefono LIKE ? ESCAPE '\\'
            GROUP BY c.id_cliente
            ORDER BY c.nombre, c.id_cliente
            LIMIT ?
            """,
            (patron, patron, limite),
        ).fetchall()
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo consultar el repositorio de clientes.") from error
    return [dict(f) for f in filas]


# ---------- Usuarios (RF-01) ----------

def crear_usuario(conexion, usuario, password_hash):
    """Guarda un usuario con su contraseña ya convertida en hash por auth.

    Este módulo nunca recibe la contraseña en texto plano (RNF-03).
    Regresa el id_usuario o lanza ErrorAlmacenamiento si el usuario ya existe.
    """
    try:
        with conexion:
            cursor = conexion.execute(
                "INSERT INTO usuarios (usuario, password_hash) VALUES (?, ?)",
                (usuario, password_hash),
            )
    except sqlite3.IntegrityError as error:
        raise ErrorAlmacenamiento(f"El usuario «{usuario}» ya existe o no es válido.") from error
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el usuario.") from error
    return cursor.lastrowid


def obtener_usuario(conexion, usuario):
    """Regresa {id_usuario, usuario, password_hash} o None si no existe."""
    fila = conexion.execute(
        "SELECT id_usuario, usuario, password_hash FROM usuarios WHERE usuario = ?",
        (usuario,),
    ).fetchone()
    return dict(fila) if fila else None


# ---------- Configuración de ACL (RF-21) ----------

CAMPOS_CONFIGURACION = (
    "nombre_comercial", "telefono", "correo", "logo_ruta", "condiciones_default",
    "vigencia_dias_default", "iva_tasa_default", "utilidad_tasa_default", "metodo_utilidad",
)


def guardar_configuracion(conexion, datos):
    """Crea o reemplaza el único registro de configuración (id 1).

    Si falla, revierte y lanza ErrorAlmacenamiento; el registro anterior queda igual (CA-65).
    """
    columnas = ", ".join(CAMPOS_CONFIGURACION)
    marcas = ", ".join("?" for _ in CAMPOS_CONFIGURACION)
    actualizacion = ", ".join(f"{c} = excluded.{c}" for c in CAMPOS_CONFIGURACION)
    try:
        with conexion:
            conexion.execute(
                f"INSERT INTO configuracion_acl (id_configuracion, {columnas}) VALUES (1, {marcas}) "
                f"ON CONFLICT (id_configuracion) DO UPDATE SET {actualizacion}",
                tuple(datos[c] for c in CAMPOS_CONFIGURACION),
            )
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar la configuración de ACL.") from error


def obtener_configuracion(conexion):
    """Regresa la configuración de ACL como dict, o None si aún no se captura."""
    fila = conexion.execute(
        f"SELECT {', '.join(CAMPOS_CONFIGURACION)} FROM configuracion_acl WHERE id_configuracion = 1"
    ).fetchone()
    return dict(fila) if fila else None


# ---------- Conceptos: catálogo SYSCOM y manuales (RF-05, RF-06) ----------

COLUMNAS_CONCEPTO = (
    "id_concepto, origen, syscom_id, tipo, descripcion, unidad, marca, categoria, "
    "precio_unitario_centavos, moneda, existencia, creado_en, actualizado_en"
)


def guardar_productos_syscom(conexion, productos):
    """Inserta o actualiza productos SYSCOM ya validados, todos o ninguno.

    productos: dicts con syscom_id, descripcion, unidad, marca, categoria,
    precio_unitario_centavos, moneda, existencia. Regresa {syscom_id: id_concepto}.
    El índice único parcial evita duplicados si se reintenta (sección 3.5).
    """
    ahora = _ahora_iso()
    ids = {}
    try:
        with conexion:
            for p in productos:
                conexion.execute(
                    """
                    INSERT INTO conceptos (origen, syscom_id, tipo, descripcion, unidad, marca, categoria,
                                           precio_unitario_centavos, moneda, existencia, creado_en, actualizado_en)
                    VALUES ('syscom', ?, 'SYSCOM', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (syscom_id) WHERE origen = 'syscom' DO UPDATE SET
                        descripcion = excluded.descripcion, unidad = excluded.unidad,
                        marca = excluded.marca, categoria = excluded.categoria,
                        precio_unitario_centavos = excluded.precio_unitario_centavos,
                        moneda = excluded.moneda, existencia = excluded.existencia,
                        actualizado_en = excluded.actualizado_en
                    """,
                    (p["syscom_id"], p["descripcion"], p["unidad"], p.get("marca"), p.get("categoria"),
                     p["precio_unitario_centavos"], p["moneda"], p.get("existencia"), ahora, ahora),
                )
                ids[p["syscom_id"]] = conexion.execute(
                    "SELECT id_concepto FROM conceptos WHERE origen = 'syscom' AND syscom_id = ?",
                    (p["syscom_id"],),
                ).fetchone()[0]
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el catálogo de SYSCOM; se conservaron los datos anteriores.") from error
    return ids


def buscar_conceptos(conexion, origen=None, texto="", categoria="", marca="", limite=100):
    """Busca conceptos por origen, palabra clave, categoría y marca (filtros opcionales)."""
    condiciones, parametros = [], []
    if origen:
        condiciones.append("origen = ?")
        parametros.append(origen)
    for columna, valor in (("descripcion", texto), ("categoria", categoria), ("marca", marca)):
        if valor and valor.strip():
            condiciones.append(f"{columna} LIKE ? ESCAPE '\\'")
            parametros.append(_patron_like(valor.strip()))
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    try:
        filas = conexion.execute(
            f"SELECT {COLUMNAS_CONCEPTO} FROM conceptos {donde} ORDER BY descripcion, id_concepto LIMIT ?",
            (*parametros, limite),
        ).fetchall()
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo consultar el catálogo.") from error
    return [dict(f) for f in filas]


def obtener_concepto(conexion, id_concepto):
    fila = conexion.execute(f"SELECT {COLUMNAS_CONCEPTO} FROM conceptos WHERE id_concepto = ?", (id_concepto,)).fetchone()
    return dict(fila) if fila else None


def obtener_conceptos(conexion, ids):
    """Regresa {id_concepto: concepto} para los ids pedidos."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    marcas = ", ".join("?" for _ in ids)
    filas = conexion.execute(f"SELECT {COLUMNAS_CONCEPTO} FROM conceptos WHERE id_concepto IN ({marcas})", ids).fetchall()
    return {f["id_concepto"]: dict(f) for f in filas}


def crear_concepto_manual(conexion, tipo, descripcion, unidad, precio_unitario_centavos, moneda):
    ahora = _ahora_iso()
    try:
        with conexion:
            cursor = conexion.execute(
                """INSERT INTO conceptos (origen, tipo, descripcion, unidad, precio_unitario_centavos, moneda,
                                          creado_en, actualizado_en)
                   VALUES ('manual', ?, ?, ?, ?, ?, ?, ?)""",
                (tipo, descripcion, unidad, precio_unitario_centavos, moneda, ahora, ahora),
            )
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el concepto.") from error
    return cursor.lastrowid


def actualizar_concepto_manual(conexion, id_concepto, tipo, descripcion, unidad, precio_unitario_centavos):
    try:
        with conexion:
            cursor = conexion.execute(
                """UPDATE conceptos SET tipo = ?, descripcion = ?, unidad = ?, precio_unitario_centavos = ?,
                          actualizado_en = ?
                   WHERE id_concepto = ? AND origen = 'manual'""",
                (tipo, descripcion, unidad, precio_unitario_centavos, _ahora_iso(), id_concepto),
            )
            if cursor.rowcount == 0:
                raise ErrorNoEncontrado(f"No existe el concepto manual {id_concepto}.")
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el concepto.") from error


# ---------- Cotizaciones (RF-07, RF-08, RF-20) ----------

COLUMNAS_COTIZACION = (
    "id_cotizacion, folio, id_cliente, id_direccion, id_origen, creada_en, actualizada_en, estatus, moneda, "
    "cliente_nombre_snapshot, cliente_telefono_snapshot, direccion_snapshot, acl_nombre_snapshot, "
    "acl_telefono_snapshot, acl_correo_snapshot, acl_logo_ruta_snapshot, condiciones, vigencia_hasta, "
    "metodo_utilidad, utilidad_tasa, iva_tasa, subtotal_centavos, utilidad_centavos, iva_centavos, "
    "total_centavos, pdf_ruta"
)
CAMPOS_PARTIDA = (
    "id_concepto", "descripcion_snapshot", "tipo_snapshot", "unidad_snapshot",
    "cantidad_milesimas", "precio_unitario_centavos", "importe_centavos",
)


def _siguiente_folio(conexion, anio):
    """COT-AAAA-NNNN consecutivo por año (SUPUESTO D08). Se calcula dentro de la transacción."""
    prefijo = f"COT-{anio}-"
    ultimo = conexion.execute(
        "SELECT folio FROM cotizaciones WHERE folio LIKE ? ORDER BY folio DESC LIMIT 1", (prefijo + "%",)
    ).fetchone()
    numero = int(ultimo[0].rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefijo}{numero:04d}"


def _insertar_partidas(conexion, id_cotizacion, partidas):
    for partida in partidas:
        conexion.execute(
            f"INSERT INTO detalle_cotizacion (id_cotizacion, {', '.join(CAMPOS_PARTIDA)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id_cotizacion, *(partida[c] for c in CAMPOS_PARTIDA)),
        )


def crear_cotizacion(conexion, cabecera, partidas):
    """Guarda cabecera y partidas en una sola transacción (sección 3.8).

    cabecera: dict con las columnas de cotizaciones excepto id, folio y fechas.
    Regresa (id_cotizacion, folio). Si algo falla no queda nada guardado.
    """
    if not partidas:
        raise ErrorAlmacenamiento("Una cotización necesita al menos una partida; no se guardó.")
    ahora = _ahora_iso()
    columnas = [c for c in cabecera]
    try:
        with conexion:
            folio = _siguiente_folio(conexion, ahora[:4])
            cursor = conexion.execute(
                f"INSERT INTO cotizaciones (folio, creada_en, actualizada_en, {', '.join(columnas)}) "
                f"VALUES (?, ?, ?, {', '.join('?' for _ in columnas)})",
                (folio, ahora, ahora, *(cabecera[c] for c in columnas)),
            )
            id_cotizacion = cursor.lastrowid
            _insertar_partidas(conexion, id_cotizacion, partidas)
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar la cotización; no se guardó ningún dato.") from error
    return id_cotizacion, folio


def obtener_cotizacion(conexion, id_cotizacion):
    """Cotización con sus partidas en "partidas", o None si no existe."""
    fila = conexion.execute(
        f"SELECT {COLUMNAS_COTIZACION} FROM cotizaciones WHERE id_cotizacion = ?", (id_cotizacion,)
    ).fetchone()
    if fila is None:
        return None
    cotizacion = dict(fila)
    cotizacion["partidas"] = [
        dict(p) for p in conexion.execute(
            f"SELECT id_detalle, {', '.join(CAMPOS_PARTIDA)} FROM detalle_cotizacion "
            "WHERE id_cotizacion = ? ORDER BY id_detalle",
            (id_cotizacion,),
        )
    ]
    return cotizacion


def listar_cotizaciones(conexion, id_cliente=None, estatus=None, desde=None, hasta=None, limite=200):
    """Cotizaciones más recientes primero, con filtros opcionales (RF-18, RF-19).

    desde/hasta: fechas AAAA-MM-DD inclusivas sobre la fecha local de creada_en.
    """
    condiciones, parametros = [], []
    if id_cliente is not None:
        condiciones.append("id_cliente = ?")
        parametros.append(id_cliente)
    if estatus:
        condiciones.append("estatus = ?")
        parametros.append(estatus)
    if desde:
        condiciones.append("substr(creada_en, 1, 10) >= ?")
        parametros.append(desde)
    if hasta:
        condiciones.append("substr(creada_en, 1, 10) <= ?")
        parametros.append(hasta)
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    try:
        filas = conexion.execute(
            "SELECT id_cotizacion, folio, id_cliente, cliente_nombre_snapshot, creada_en, estatus, total_centavos, "
            f"moneda, id_origen FROM cotizaciones {donde} ORDER BY creada_en DESC, id_cotizacion DESC LIMIT ?",
            (*parametros, limite),
        ).fetchall()
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo consultar el historial de cotizaciones.") from error
    return [dict(f) for f in filas]



class ErrorEstadoCotizacion(ErrorAlmacenamiento):
    """La cotización ya no está en el estatus esperado (por ejemplo, ya se cerró)."""


def actualizar_estatus(conexion, id_cotizacion, nuevo, esperado):
    """Cambia el estatus solo si sigue siendo `esperado` (evita carreras entre pestañas)."""
    try:
        with conexion:
            cursor = conexion.execute(
                "UPDATE cotizaciones SET estatus = ?, actualizada_en = ? WHERE id_cotizacion = ? AND estatus = ?",
                (nuevo, _ahora_iso(), id_cotizacion, esperado),
            )
            if cursor.rowcount == 0:
                raise ErrorEstadoCotizacion("La cotización ya no está pendiente; no se cambió el estatus.")
    except ErrorAlmacenamiento:
        raise
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo guardar el estatus.") from error


def reemplazar_partidas(conexion, id_cotizacion, partidas, totales, id_direccion, direccion_snapshot):
    """Sustituye partidas y totales de una cotización PENDIENTE en una transacción (RF-14).

    Si la cotización ya no está pendiente lanza ErrorEstadoCotizacion y no cambia nada.
    El PDF anterior deja de ser válido: pdf_ruta se limpia hasta regenerarlo.
    """
    if not partidas:
        raise ErrorAlmacenamiento("Una cotización necesita al menos una partida; no se guardó.")
    try:
        with conexion:
            cursor = conexion.execute(
                """UPDATE cotizaciones SET subtotal_centavos = ?, utilidad_centavos = ?, iva_centavos = ?,
                          total_centavos = ?, id_direccion = ?, direccion_snapshot = ?, actualizada_en = ?,
                          pdf_ruta = NULL
                   WHERE id_cotizacion = ? AND estatus = 'pendiente'""",
                (totales["subtotal_centavos"], totales["utilidad_centavos"], totales["iva_centavos"],
                 totales["total_centavos"], id_direccion, direccion_snapshot, _ahora_iso(), id_cotizacion),
            )
            if cursor.rowcount == 0:
                raise ErrorEstadoCotizacion("Solo se pueden modificar cotizaciones pendientes; no se guardaron cambios.")
            conexion.execute("DELETE FROM detalle_cotizacion WHERE id_cotizacion = ?", (id_cotizacion,))
            _insertar_partidas(conexion, id_cotizacion, partidas)
    except ErrorAlmacenamiento:
        raise
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudieron guardar los cambios; la cotización quedó como estaba.") from error


def guardar_pdf_ruta(conexion, id_cotizacion, ruta):
    try:
        with conexion:
            conexion.execute("UPDATE cotizaciones SET pdf_ruta = ? WHERE id_cotizacion = ?", (ruta, id_cotizacion))
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento("No se pudo registrar la ruta del PDF.") from error
