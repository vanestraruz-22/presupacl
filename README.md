# PresupACL

Sistema web local para elaborar cotizaciones de seguridad electrónica para **ACL Alarmas y Cámaras de León**.

Equipo **SofChi**: Sofía Quesada y Vanesa Estrada · Desarrollo de Aplicaciones y Servicios Virtuales · Universidad Iberoamericana León · Prof. Ing. Alejandro Montes Moreno.

## Estado

**Incremento 4 en la rama `incremento-4` (v0.4.0, entrega 19-nov-2026):** RF-11 PDF, RF-12 WhatsApp, RF-13 estatus, RF-14 edición y RF-15 duplicado. También cierra CA-36 y CA-64 de RF-21 dentro del PDF.

| Tarea | RF | Módulo | Estado |
|---|---|---|---|
| T-20 PDF de la cotización | RF-11, RF-21 | generador_pdf_cotizacion | Terminada (CA-20, CA-21, CA-51, CA-36, CA-64) |
| T-21 Enlace de WhatsApp | RF-12 | mensajeria_whatsapp | Terminada (CA-22, CA-23, CA-52 en pantalla) |
| T-22 Cambio de estatus | RF-13 | cotizaciones_estado | Terminada (CA-24, CA-53, CA-54) |
| T-23 Edición solo en pendiente | RF-14 | cotizaciones_edicion | Terminada (CA-26, CA-55, CA-56, CA-27) |
| T-24 Duplicar cerrada | RF-15 | cotizaciones_duplicado | Terminada (CA-27.1, CA-57, CA-67, CA-66) |
| T-25 Pantallas | RF-11 a RF-15 | main.py, templates/ | Terminada |

SUPUESTOS del incremento 4: fpdf2 para el PDF (D09); una cotización aceptada o rechazada no se reabre (D04); cambio de precio "significativo" mayor al 10 % (D03); teléfonos de México con clave 52.

**Incremento 3 en la rama `incremento-3` (v0.3.0, entrega 17-nov-2026):** RF-05 catálogo SYSCOM, RF-06 conceptos manuales, RF-07 crear cotización, RF-08 cálculo y RF-20 validación.

| Tarea | RF | Módulo | Estado |
|---|---|---|---|
| T-13 Tablas de conceptos y cotizaciones | RF-07 | almacenamiento_datos | Terminada |
| T-14 Calculadora en enteros | RF-08 | calculadora_cotizacion | Terminada (CA-17, CA-45, CA-46) |
| T-15 Conceptos manuales | RF-06 | conceptos_manuales | Terminada (CA-13, CA-42, CA-43) |
| T-16 Catálogo SYSCOM (simulado) | RF-05 | cliente_api_syscom, catalogo_syscom | Terminada con SYSCOM simulado (CA-11, CA-41, CA-12) |
| T-17 Crear cotización y validar | RF-07, RF-20 | cotizaciones_creacion, validador_cotizacion | Terminada (CA-14, CA-44, CA-16, CA-62, CA-63, CA-15) |
| T-18 Pantallas | RF-05 a RF-08, RF-20 | main.py, templates/ | Terminada |

SUPUESTOS del incremento 3: utilidad como recargo sobre el subtotal, IVA sobre subtotal + utilidad, redondeo al centavo mitad hacia arriba (D01); moneda MXN (D02); folio COT-AAAA-NNNN (D08). **El cliente real de SYSCOM no se ha probado contra la API** porque no hay credenciales; para probar sin API: `PRESUPACL_SYSCOM=demo python -m proyecto.main`.

**Incremento 2 en la rama `incremento-2` (v0.2.0, entrega 12-nov-2026):** RF-01 inicio de sesión, RF-03 editar cliente, RF-04 buscar cliente, RF-21 configuración de ACL y las primeras pantallas web.

| Tarea | RF | Módulo | Estado |
|---|---|---|---|
| T-07 Usuarios y contraseñas con hash | RF-01 | auth, almacenamiento_datos | Terminada (CA-01, CA-02, RNF-03) |
| T-08 Editar teléfono y direcciones | RF-03 | clientes_registro, almacenamiento_datos | Terminada (CA-07, CA-39, CA-08) |
| T-09 Búsqueda por nombre o teléfono | RF-04 | clientes_busqueda, almacenamiento_datos | Terminada (CA-09, CA-10, CA-40) |
| T-10 Configuración de ACL | RF-21 | config/settings, almacenamiento_datos | Terminada (CA-65; CA-36 y CA-64 se cierran con el PDF en el incremento 4) |
| T-11 Aplicación web y pantallas | RF-01 a RF-04, RF-21 | main.py, templates/ | Terminada (CA-37) |

SUPUESTOS por validar (marcados en el código): Flask/werkzeug para web, hash y sesiones (D09); IVA 0.16, utilidad 0.20 como recargo y vigencia 15 días como valores iniciales editables.

**Incremento 1 terminado (v0.1.0):** RF-02 · registrar cliente con nombre, teléfono y una o varias direcciones, según el plan de implementación v1.2.

| Tarea | Módulo | Estado |
|---|---|---|
| T-01 Estructura base y repositorio | proyecto | Terminada |
| T-02 Contrato de entradas, salidas y errores | clientes_registro | Terminada |
| T-03 Esquema SQLite con FK | almacenamiento_datos | Terminada (P11) |
| T-04 Guardado transaccional y consulta | almacenamiento_datos | Terminada (CA-04, CA-38, P01, P12, P13) |
| T-05 Validación de campos obligatorios | clientes_registro | Terminada (CA-05, CA-68) |
| T-06 Integración, P01 y demostración | ambos | Terminada (PT-02-N/L/E/E2, P01) |

Documentos vigentes en `docs/`: especificación v2.5 y plan de implementación v1.2. El plan de los siguientes incrementos vivirá en `docs/plan_incrementos.md`.

## Requisitos

- Python 3.10 o superior (se usa `sqlite3` de la biblioteca estándar).
- Flask (aplicación web), fpdf2 (PDF, a partir del incremento 4) y pytest.

```bash
python -m pip install -r requirements.txt
```

## Ejecutar pruebas

Desde la raíz del repositorio:

```bash
python -m pytest -v
```

## Abrir la aplicación web (incremento 2)

```bash
python -m proyecto.auth.auth admin      # solo la primera vez: pide la contraseña y crea el usuario
python -m proyecto.main                 # luego abrir http://127.0.0.1:8000 en Chrome o Edge
```

La contraseña nunca se escribe en el código. Opcional: definir `PRESUPACL_SECRET_KEY` para que la sesión no se cierre al reiniciar, y `PRESUPACL_HOST=0.0.0.0` para abrirla desde otra computadora de la red local. El puerto es 8000 (en macOS el 5000 lo ocupa AirPlay); se cambia con `PRESUPACL_PORT`.

## Demostración del incremento 1

```bash
python -m proyecto.demo_rf02
```

Crea `data/presupacl.db`, registra un cliente ficticio con dos direcciones, lo vuelve a leer y muestra un registro rechazado por datos faltantes. Para ver la BD en VS Code se puede usar la extensión "SQLite Viewer".

## Estructura

```
proyecto/
  auth/              auth.py (inicio de sesión y hash de contraseñas)
  catalogo/          cliente_api_syscom.py (único acceso a SYSCOM), catalogo_syscom.py
  clientes/          clientes_registro.py (registrar y editar), clientes_busqueda.py
  conceptos/         conceptos_manuales.py
  comunicacion/      mensajeria_whatsapp.py (enlaces para envío manual)
  cotizaciones/      calculadora, validador, creacion, estado, edicion y duplicado
  documentos/        generador_pdf_cotizacion.py
  config/            settings.py (configuración de ACL)
  infraestructura/   almacenamiento_datos.py (único módulo que accede a la BD)
  templates/         pantallas HTML de la aplicación web
  tests/             test_<modulo>.py por módulo, integración y pantallas web
  main.py            aplicación web (Flask)
  demo_rf02.py       demostración por consola del incremento 1
docs/                especificación y planes aprobados
data/                presupacl.db (se crea al ejecutar; no se sube al repositorio)
salidas/cotizaciones/ PDF generados (no se suben al repositorio)
recursos/logo_acl/   logo de ACL subido desde Configuración (no se sube al repositorio)
```

Las demás carpetas de la arquitectura (auth, catalogo, cotizaciones, etc.) se agregan cuando su incremento tenga código.

## Reglas del repositorio

- No se suben bases de datos, archivos `.env`, credenciales ni logs.
- Cada commit de código lleva su push y se verifica en GitHub.
- Las pruebas usan datos ficticios y una base temporal.
