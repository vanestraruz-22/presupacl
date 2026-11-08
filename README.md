# PresupACL

Sistema web local para elaborar cotizaciones de seguridad electrónica para **ACL Alarmas y Cámaras de León**.

Equipo **SofChi**: Sofía Quesada y Vanesa Estrada · Desarrollo de Aplicaciones y Servicios Virtuales · Universidad Iberoamericana León · Prof. Ing. Alejandro Montes Moreno.

Documentos vigentes en `docs/`:
- Especificación v2.5.
- Plan de implementación v1.2.
- Manual de uso (RNF-08).

## Estado

Los 21 requerimientos funcionales están implementados y probados. Cada incremento vive en su rama y se une a `main` en su fecha de entrega, con su tag.

| Incremento | Rama | Tag | Entrega | RF | Tareas |
|---|---|---|---|---|---|
| 1 | main | v0.1.0 | 5-nov-2026 | RF-02 | T-01 a T-06 |
| 2 | incremento-2 | v0.2.0 | 12-nov-2026 | RF-01, RF-03, RF-04, RF-21 (guardado) | T-07 a T-12 |
| 3 | incremento-3 | v0.3.0 | 17-nov-2026 | RF-05, RF-06, RF-07, RF-08, RF-20 | T-13 a T-19 |
| 4 | incremento-4 | v0.4.0 | 19-nov-2026 | RF-11 a RF-15, RF-21 (en el PDF) | T-20 a T-26 |
| 5 | incremento-5 | v1.0.0 | 24-nov-2026 | RF-09, RF-10, RF-16 a RF-19, RNF-08 | T-27 a T-33 |

### Trazabilidad RF → módulo → pruebas

| RF | Módulo | Archivo de pruebas | Criterios |
|---|---|---|---|
| RF-01 | auth, main | test_auth, test_web | CA-01, CA-37, CA-02 |
| RF-02 | clientes_registro | test_clientes_registro, test_integracion_rf02 | CA-04, CA-38, CA-05, CA-68 |
| RF-03 | clientes_registro | test_clientes_edicion | CA-07, CA-39, CA-08 |
| RF-04 | clientes_busqueda | test_clientes_busqueda | CA-09, CA-10, CA-40 |
| RF-05 | catalogo_syscom, cliente_api_syscom | test_catalogo_syscom | CA-11, CA-41, CA-12 |
| RF-06 | conceptos_manuales | test_conceptos_manuales | CA-13, CA-42, CA-43 |
| RF-07 | cotizaciones_creacion | test_cotizaciones_creacion | CA-14, CA-44, CA-16 |
| RF-08 | calculadora_cotizacion | test_calculadora_cotizacion | CA-17, CA-45, CA-46 |
| RF-09 | sincronizador_precios_syscom | test_sincronizador_precios_syscom | CA-18, CA-47, CA-48 |
| RF-10 | sincronizador_precios_syscom | test_sincronizador_precios_syscom | CA-19, CA-49, CA-50 |
| RF-11 | generador_pdf_cotizacion | test_generador_pdf_cotizacion | CA-20, CA-21, CA-51 |
| RF-12 | mensajeria_whatsapp | test_mensajeria_whatsapp, test_web_cotizaciones_cierre | CA-22, CA-23, CA-52 |
| RF-13 | cotizaciones_estado | test_cotizaciones_estado | CA-24, CA-53, CA-54 |
| RF-14 | cotizaciones_edicion | test_cotizaciones_edicion | CA-26, CA-55, CA-56 |
| RF-15 | cotizaciones_duplicado, cotizaciones_estado | test_cotizaciones_duplicado, test_cotizaciones_edicion | CA-27.1, CA-57, CA-67, CA-27, CA-66 |
| RF-16 | ordenes_servicio | test_ordenes_servicio | CA-28, CA-58, CA-29 |
| RF-17 | ordenes_servicio, mensajeria_whatsapp | test_ordenes_servicio, test_web_final | CA-30, CA-59, CA-31 |
| RF-18 | historial_cotizaciones | test_historial_cotizaciones | CA-32, CA-33, CA-60 |
| RF-19 | historial_cotizaciones | test_historial_cotizaciones | CA-34, CA-61, CA-35 |
| RF-20 | validador_cotizacion | test_cotizaciones_creacion, test_cotizaciones_edicion | CA-62, CA-63, CA-15 |
| RF-21 | config/settings, generador_pdf_cotizacion | test_settings, test_generador_pdf_cotizacion | CA-36, CA-64, CA-65 |

### SUPUESTOS por validar con ACL o con el equipo (marcados en el código)

| Decisión | Supuesto usado |
|---|---|
| D01 | Utilidad como recargo sobre el subtotal (se puede cambiar a margen en Configuración); IVA sobre subtotal + utilidad; redondeo al centavo, mitad hacia arriba. |
| D02 | Moneda MXN. |
| D03 | Cambio de precio "significativo" al duplicar: más del 10 %. |
| D04 | Una cotización aceptada o rechazada no se reabre. |
| D05 | Son de instalación todos los tipos menos viáticos y día festivo. El teléfono del técnico se captura al enviar. |
| D06 | Sincronización cada 24 h con la app abierta y reintento a la hora. |
| D08 | Folio COT-AAAA-NNNN; filtro de fechas inclusivo. |
| D09 | Flask, werkzeug (hash pbkdf2) y fpdf2. |
| Vigencia | 15 días. |

**El cliente real de la API de SYSCOM no se ha probado** porque el equipo no tiene credenciales. Todas las pruebas usan SYSCOM simulado, y la app tiene un modo de demostración con productos ficticios.

## Instalar y probar

Se necesita Python 3.9 o superior. Desde la raíz del repositorio:

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -v
```

## Abrir la aplicación

```bash
python3 -m proyecto.auth.auth admin      # solo la primera vez: pide la contraseña y crea el usuario
python3 -m proyecto.main                 # abrir http://127.0.0.1:8000 en Chrome o Edge
```

Con productos SYSCOM ficticios (sin API real):

```bash
PRESUPACL_SYSCOM=demo python3 -m proyecto.main
```

Variables de entorno opcionales. Nunca se escriben en el código:

| Variable | Uso |
|---|---|
| `SYSCOM_CLIENT_ID`, `SYSCOM_CLIENT_SECRET` | Credenciales de la API de SYSCOM. |
| `PRESUPACL_SECRET_KEY` | Llave de sesiones, para que la sesión no se cierre al reiniciar. |
| `PRESUPACL_HOST=0.0.0.0` | Abrir la app desde otra computadora de la red local (RNF-06). |
| `PRESUPACL_PORT` | Puerto, 8000 por defecto. En macOS el 5000 lo ocupa AirPlay. |

## Estructura

```
proyecto/
  auth/              auth.py (inicio de sesión, hash de contraseñas)
  catalogo/          cliente_api_syscom.py (único acceso a SYSCOM), catalogo_syscom.py, sincronizador_precios_syscom.py
  clientes/          clientes_registro.py (registrar y editar), clientes_busqueda.py
  comunicacion/      mensajeria_whatsapp.py (enlaces para envío manual)
  conceptos/         conceptos_manuales.py
  config/            settings.py (configuración de ACL)
  cotizaciones/      calculadora, validador, creacion, estado, edicion y duplicado
  documentos/        generador_pdf_cotizacion.py
  historial/         historial_cotizaciones.py
  infraestructura/   almacenamiento_datos.py (único módulo que accede a la BD), registro_eventos.py
  ordenes/           ordenes_servicio.py
  templates/         pantallas HTML
  tests/             pruebas por módulo, integración y pantallas
  main.py            aplicación web (Flask)
  demo_rf02.py       demostración por consola del incremento 1
docs/                especificación, plan y manual de uso
data/                presupacl.db (no se sube al repositorio)
salidas/cotizaciones/ PDF generados (no se suben)
recursos/logo_acl/   logo de ACL (no se sube)
logs/                presupacl.log (no se sube)
```

## Reglas del repositorio

- Solo `almacenamiento_datos` ejecuta SQL: consultas parametrizadas, llaves foráneas activas y transacciones.
- Dinero en centavos y cantidades en milésimas, siempre en enteros.
- No se suben bases de datos, archivos `.env`, credenciales, PDF ni logs.
- Un commit por tarea con el formato `tipo(RF-XX): descripción`, cada uno con su push verificado.
- Las pruebas usan datos ficticios, una base temporal y SYSCOM simulado.
