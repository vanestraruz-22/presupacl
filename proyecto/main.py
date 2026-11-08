"""main: aplicación web local de PresupACL (Flask).

SUPUESTO — validar con el equipo (D09): Flask como framework web.

Ejecutar desde la raíz del repositorio:
    python -m proyecto.auth.auth admin      # solo la primera vez: crea el usuario
    python -m proyecto.main                 # abre http://127.0.0.1:8000

Variables de entorno (opcionales, nunca en el código):
    PRESUPACL_SECRET_KEY  llave de las sesiones; si falta se genera una al
                          arrancar y las sesiones se cierran al reiniciar.
    PRESUPACL_HOST        127.0.0.1 por defecto; 0.0.0.0 para la red local (RNF-06).
    PRESUPACL_SYSCOM      "demo" usa productos ficticios en lugar de la API.
    SYSCOM_CLIENT_ID / SYSCOM_CLIENT_SECRET  credenciales de la API de SYSCOM.
    PRESUPACL_PORT        8000 por defecto. No se usa 5000 porque en macOS lo
                          ocupa el Receptor AirPlay y el navegador da error 403.
"""

import functools
import os
import secrets

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for

from proyecto.auth import auth
from proyecto.catalogo import catalogo_syscom, cliente_api_syscom
from proyecto.clientes import clientes_busqueda, clientes_registro
from proyecto.conceptos import conceptos_manuales
from proyecto.config import settings
from proyecto.comunicacion import mensajeria_whatsapp
from proyecto.cotizaciones import (calculadora_cotizacion, cotizaciones_creacion, cotizaciones_duplicado,
                                   cotizaciones_edicion, cotizaciones_estado)
from proyecto.documentos import generador_pdf_cotizacion
from proyecto.cotizaciones.validador_cotizacion import ErrorCotizacion
from proyecto.infraestructura import almacenamiento_datos


def login_requerido(vista):
    """Protege una ruta: sin sesión se manda a iniciar sesión (CA-37)."""

    @functools.wraps(vista)
    def envoltura(*args, **kwargs):
        if "id_usuario" not in session:
            return redirect(url_for("login", siguiente=request.path))
        return vista(*args, **kwargs)

    return envoltura


def crear_app(ruta_bd=None, secret_key=None, cliente_syscom="entorno", carpeta_pdf=None):
    app = Flask(__name__)
    app.config["CARPETA_PDF"] = carpeta_pdf
    app.config["CLIENTE_SYSCOM"] = (
        cliente_api_syscom.obtener_cliente_configurado() if cliente_syscom == "entorno" else cliente_syscom
    )
    app.jinja_env.filters["moneda"] = calculadora_cotizacion.formato_moneda
    app.jinja_env.filters["cantidad"] = calculadora_cotizacion.formato_cantidad
    app.jinja_env.globals["TIPOS"] = cotizaciones_creacion.TIPOS
    app.config["SECRET_KEY"] = secret_key or os.environ.get("PRESUPACL_SECRET_KEY") or secrets.token_hex(32)
    app.config["RUTA_BD"] = ruta_bd
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # logo de hasta 5 MB

    conexion = almacenamiento_datos.abrir_conexion(ruta_bd)
    almacenamiento_datos.crear_esquema(conexion)
    conexion.close()

    def bd():
        if "bd" not in g:
            g.bd = almacenamiento_datos.abrir_conexion(app.config["RUTA_BD"])
        return g.bd

    @app.teardown_appcontext
    def cerrar_bd(_error):
        conexion = g.pop("bd", None)
        if conexion is not None:
            conexion.close()

    # ---------- Protección CSRF sencilla para formularios ----------
    @app.before_request
    def revisar_token():
        if request.method == "POST":
            if not request.form.get("_token") or request.form.get("_token") != session.get("_token"):
                abort(400, "Formulario vencido; vuelva a cargar la página.")

    @app.context_processor
    def token_formulario():
        if "_token" not in session:
            session["_token"] = secrets.token_hex(16)
        return {"token": session["_token"], "usuario_actual": session.get("usuario")}

    # ---------- RF-01 Inicio de sesión ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        siguiente = request.args.get("siguiente", "")
        if request.method == "POST":
            try:
                datos = auth.verificar_credenciales(bd(), request.form.get("usuario"), request.form.get("password"))
            except auth.ErrorAutenticacion as error:
                return render_template("login.html", error=str(error), siguiente=siguiente), 401
            token = session.get("_token")
            session.clear()
            session.update(id_usuario=datos["id_usuario"], usuario=datos["usuario"], _token=token)
            # Solo se aceptan rutas internas para no redirigir a otro sitio.
            destino = siguiente if siguiente.startswith("/") and not siguiente.startswith("//") else url_for("panel")
            return redirect(destino)
        return render_template("login.html", siguiente=siguiente)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_requerido
    def panel():
        return render_template("panel.html", config_completa=settings.configuracion_completa(bd()))

    # ---------- RF-04 Búsqueda / RF-02 Registro / RF-03 Edición ----------
    @app.route("/clientes")
    @login_requerido
    def clientes():
        texto = request.args.get("q", "")
        respuesta, error = {"resultados": [], "mensaje": None}, None
        if texto.strip():
            try:
                respuesta = clientes_busqueda.buscar_clientes(bd(), texto)
            except clientes_busqueda.ErrorBusqueda as falla:
                error = str(falla)
        return render_template("clientes.html", q=texto, error=error, **respuesta)

    @app.route("/clientes/nuevo", methods=["GET", "POST"])
    @login_requerido
    def cliente_nuevo():
        datos = {"nombre": "", "telefono": "", "direcciones": [""]}
        if request.method == "POST":
            datos = {
                "nombre": request.form.get("nombre", ""),
                "telefono": request.form.get("telefono", ""),
                "direcciones": [d for d in request.form.getlist("direccion") if d.strip()],
            }
            try:
                id_cliente = clientes_registro.registrar_cliente(bd(), datos["nombre"], datos["telefono"], datos["direcciones"])
            except clientes_registro.ErrorValidacion as error:
                datos["direcciones"] = datos["direcciones"] or [""]
                return render_template("cliente_nuevo.html", datos=datos, error=str(error), faltantes=error.campos_faltantes), 400
            except almacenamiento_datos.ErrorAlmacenamiento as error:
                return render_template("cliente_nuevo.html", datos=datos, error=str(error), faltantes=[]), 500
            flash("Cliente registrado.")
            return redirect(url_for("cliente_detalle", id_cliente=id_cliente))
        return render_template("cliente_nuevo.html", datos=datos, error=None, faltantes=[])

    @app.route("/clientes/<int:id_cliente>", methods=["GET", "POST"])
    @login_requerido
    def cliente_detalle(id_cliente):
        if request.method == "POST":
            editadas = {
                int(clave.removeprefix("direccion_")): valor
                for clave, valor in request.form.items()
                if clave.startswith("direccion_") and clave.removeprefix("direccion_").isdigit()
            }
            try:
                clientes_registro.editar_cliente(
                    bd(), id_cliente, request.form.get("nombre"), request.form.get("telefono"),
                    editadas, request.form.getlist("nueva_direccion"),
                )
            except almacenamiento_datos.ErrorNoEncontrado as error:
                abort(404, str(error))
            except (clientes_registro.ErrorValidacion, almacenamiento_datos.ErrorAlmacenamiento) as error:
                cliente = almacenamiento_datos.obtener_cliente(bd(), id_cliente)
                return render_template("cliente_detalle.html", cliente=cliente, error=str(error)), 400
            flash("Cambios guardados.")
            return redirect(url_for("cliente_detalle", id_cliente=id_cliente))

        cliente = almacenamiento_datos.obtener_cliente(bd(), id_cliente)
        if cliente is None:
            abort(404, f"No existe el cliente {id_cliente}.")
        return render_template("cliente_detalle.html", cliente=cliente, error=None)

    # ---------- RF-21 Configuración de ACL ----------
    @app.route("/configuracion", methods=["GET", "POST"])
    @login_requerido
    def configuracion():
        config = settings.obtener_configuracion(bd())
        if request.method == "POST":
            datos = {campo: request.form.get(campo) for campo in almacenamiento_datos.CAMPOS_CONFIGURACION}
            datos["logo_ruta"] = config.get("logo_ruta")
            try:
                logo = request.files.get("logo")
                if logo and logo.filename:
                    datos["logo_ruta"] = settings.guardar_logo(logo.read(), logo.filename)
                settings.guardar_configuracion(bd(), datos)
            except settings.ErrorConfiguracion as error:
                return render_template("configuracion.html", config=datos, error=str(error), campos=error.campos), 400
            flash("Configuración guardada.")
            return redirect(url_for("configuracion"))
        return render_template("configuracion.html", config=config, error=None, campos=[])

    # ---------- RF-06 Conceptos manuales ----------
    @app.route("/conceptos", methods=["GET", "POST"])
    @login_requerido
    def conceptos():
        datos, errores = {"tipo": "mano_obra", "descripcion": "", "unidad": "servicio", "precio": ""}, {}
        if request.method == "POST":
            datos = {c: request.form.get(c, "") for c in ("tipo", "descripcion", "unidad", "precio")}
            try:
                conceptos_manuales.registrar_concepto(bd(), **datos)
            except conceptos_manuales.ErrorConcepto as error:
                errores = error.errores
            else:
                flash("Concepto registrado.")
                return redirect(url_for("conceptos"))
        texto = request.args.get("q", "")
        return render_template("conceptos.html", lista=conceptos_manuales.listar(bd(), texto), q=texto,
                               datos=datos, errores=errores, tipos=conceptos_manuales.TIPOS_MANUALES), \
            (400 if errores else 200)

    @app.route("/conceptos/<int:id_concepto>", methods=["GET", "POST"])
    @login_requerido
    def concepto_editar(id_concepto):
        concepto = almacenamiento_datos.obtener_concepto(bd(), id_concepto)
        if concepto is None or concepto["origen"] != "manual":
            abort(404, "No existe ese concepto manual.")
        datos = {"tipo": concepto["tipo"], "descripcion": concepto["descripcion"], "unidad": concepto["unidad"],
                 "precio": f"{concepto['precio_unitario_centavos'] / 100:.2f}"}
        errores = {}
        if request.method == "POST":
            datos = {c: request.form.get(c, "") for c in ("tipo", "descripcion", "unidad", "precio")}
            try:
                conceptos_manuales.modificar_concepto(bd(), id_concepto, **datos)
            except conceptos_manuales.ErrorConcepto as error:
                errores = error.errores
            else:
                flash("Concepto actualizado. Las cotizaciones ya guardadas no cambian.")
                return redirect(url_for("conceptos"))
        return render_template("concepto_editar.html", concepto=concepto, datos=datos, errores=errores,
                               tipos=conceptos_manuales.TIPOS_MANUALES), (400 if errores else 200)

    # ---------- RF-05 Catálogo SYSCOM ----------
    @app.route("/catalogo")
    @login_requerido
    def catalogo():
        filtros = {c: request.args.get(c, "") for c in ("texto", "categoria", "marca")}
        respuesta, error = None, None
        if any(v.strip() for v in filtros.values()):
            try:
                respuesta = catalogo_syscom.buscar_productos(bd(), app.config["CLIENTE_SYSCOM"], **filtros)
            except (catalogo_syscom.ErrorCatalogo, almacenamiento_datos.ErrorAlmacenamiento) as falla:
                error = str(falla)
        return render_template("catalogo.html", filtros=filtros, respuesta=respuesta, error=error,
                               borrador=session.get("borrador"))

    # ---------- RF-07, RF-08, RF-20 Cotización nueva (borrador en la sesión) ----------
    def borrador_actual():
        borrador = session.get("borrador")
        if not borrador:
            return None
        cliente = almacenamiento_datos.obtener_cliente(bd(), borrador["id_cliente"])
        if cliente is None:
            session.pop("borrador", None)
            return None
        return borrador, cliente

    def vista_previa(borrador):
        """Partidas y totales del borrador, o el error que impide calcularlos."""
        if not borrador["renglones"]:
            return [], None, None
        try:
            partidas = cotizaciones_creacion.preparar_partidas(bd(), borrador["renglones"])
            config = settings.obtener_configuracion(bd())
            resultado = cotizaciones_creacion.totales(partidas, config["metodo_utilidad"],
                                                      config["utilidad_tasa_default"], config["iva_tasa_default"])
            return partidas, resultado, None
        except ErrorCotizacion as error:
            return [], None, str(error)

    @app.route("/cotizaciones/nueva", methods=["POST"])
    @login_requerido
    def cotizacion_nueva():
        cliente = almacenamiento_datos.obtener_cliente(bd(), request.form.get("id_cliente", type=int))
        if cliente is None:
            abort(404, "No existe el cliente.")
        session["borrador"] = {"id_cliente": cliente["id_cliente"],
                               "id_direccion": cliente["direcciones"][0]["id_direccion"], "renglones": []}
        return redirect(url_for("borrador"))

    @app.route("/borrador/agregar", methods=["POST"])
    @login_requerido
    def borrador_agregar():
        actual = borrador_actual()
        if actual is None:
            flash("Primero elija un cliente y presione «Nueva cotización».")
            return redirect(url_for("clientes"))
        borrador, _ = actual
        borrador["renglones"].append({"id_concepto": request.form.get("id_concepto", type=int),
                                      "cantidad": request.form.get("cantidad") or "1", "precio": None})
        session["borrador"] = borrador
        flash("Concepto agregado a la cotización.")
        return redirect(request.form.get("volver") or url_for("borrador"))

    @app.route("/borrador", methods=["GET", "POST"])
    @login_requerido
    def borrador():
        actual = borrador_actual()
        if actual is None:
            flash("No hay una cotización en captura. Busque un cliente y presione «Nueva cotización».")
            return redirect(url_for("clientes"))
        borrador, cliente = actual
        error = None
        if request.method == "POST":
            borrador["id_direccion"] = request.form.get("id_direccion", type=int)
            cantidades = request.form.getlist("cantidad")
            precios = request.form.getlist("precio")
            for i, renglon in enumerate(borrador["renglones"]):
                if i < len(cantidades):
                    renglon["cantidad"] = cantidades[i]
                if i < len(precios):
                    renglon["precio"] = precios[i] or None
            quitar = request.form.get("quitar", type=int)
            if quitar is not None and 0 <= quitar < len(borrador["renglones"]):
                borrador["renglones"].pop(quitar)
            session["borrador"] = borrador
            if request.form.get("accion") == "guardar":
                try:
                    id_cotizacion, folio = cotizaciones_creacion.crear_cotizacion(
                        bd(), cliente["id_cliente"], borrador["renglones"], borrador["id_direccion"])
                except ErrorCotizacion as falla:
                    error = str(falla)
                else:
                    session.pop("borrador", None)
                    flash(f"Cotización {folio} guardada como pendiente.")
                    generar_pdf_con_aviso(id_cotizacion)
                    return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))
            elif request.form.get("accion") == "cancelar":
                session.pop("borrador", None)
                flash("Se descartó la cotización en captura.")
                return redirect(url_for("cliente_detalle", id_cliente=cliente["id_cliente"]))
        partidas, resultado, error_previa = vista_previa(borrador)
        conceptos_lista = almacenamiento_datos.buscar_conceptos(bd(), origen="manual") + \
            almacenamiento_datos.buscar_conceptos(bd(), origen="syscom")
        return render_template(
            "borrador.html", borrador=borrador, cliente=cliente, partidas=partidas, resultado=resultado,
            error=error or error_previa, conceptos=conceptos_lista,
            config=settings.obtener_configuracion(bd()), config_completa=settings.configuracion_completa(bd()),
        ), (400 if error else 200)

    @app.route("/cotizaciones")
    @login_requerido
    def cotizaciones():
        lista = almacenamiento_datos.listar_cotizaciones(bd())
        return render_template("cotizaciones.html", lista=lista)

    def cotizacion_o_404(id_cotizacion):
        cotizacion = almacenamiento_datos.obtener_cotizacion(bd(), id_cotizacion)
        if cotizacion is None:
            abort(404, f"No existe la cotización {id_cotizacion}.")
        return cotizacion

    def generar_pdf_con_aviso(id_cotizacion):
        try:
            return generador_pdf_cotizacion.generar_pdf(bd(), id_cotizacion, app.config["CARPETA_PDF"])
        except generador_pdf_cotizacion.ErrorPdf as error:
            flash(str(error))
            return None

    @app.route("/cotizaciones/<int:id_cotizacion>")
    @login_requerido
    def cotizacion_detalle(id_cotizacion):
        cotizacion = cotizacion_o_404(id_cotizacion)
        return render_template(
            "cotizacion_detalle.html", c=cotizacion, editable=cotizaciones_estado.puede_editarse(cotizacion),
            alertas=cotizaciones_duplicado.conceptos_por_revisar(bd(), cotizacion),
            pdf_listo=generador_pdf_cotizacion.ruta_pdf_vigente(cotizacion) is not None,
        )

    # ---------- RF-11 / RF-12 PDF y WhatsApp ----------
    @app.route("/cotizaciones/<int:id_cotizacion>/pdf")
    @login_requerido
    def cotizacion_pdf(id_cotizacion):
        cotizacion = cotizacion_o_404(id_cotizacion)
        ruta = generador_pdf_cotizacion.ruta_pdf_vigente(cotizacion)
        if ruta is None:
            try:
                ruta = generador_pdf_cotizacion.generar_pdf(bd(), id_cotizacion, app.config["CARPETA_PDF"])
            except generador_pdf_cotizacion.ErrorPdf as error:
                # CA-52: se informa el error y no se entrega un archivo vacío.
                return render_template("error.html", mensaje=str(error)), 500
        return send_file(ruta, mimetype="application/pdf", as_attachment=request.args.get("descargar") == "1",
                         download_name=f"{cotizacion['folio']}.pdf")

    @app.route("/cotizaciones/<int:id_cotizacion>/whatsapp")
    @login_requerido
    def cotizacion_whatsapp(id_cotizacion):
        cotizacion = cotizacion_o_404(id_cotizacion)
        try:
            enlace = mensajeria_whatsapp.enlace_cotizacion(cotizacion)
        except mensajeria_whatsapp.ErrorTelefono as error:
            flash(f"{error} Descargue el PDF y envíelo por otro medio.")
            return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))
        return redirect(enlace)

    # ---------- RF-13 Estatus ----------
    @app.route("/cotizaciones/<int:id_cotizacion>/estatus", methods=["POST"])
    @login_requerido
    def cotizacion_estatus(id_cotizacion):
        cotizacion_o_404(id_cotizacion)
        nuevo = request.form.get("estatus")
        try:
            cambio = cotizaciones_estado.cambiar_estatus(bd(), id_cotizacion, nuevo)
        except ErrorCotizacion as error:
            flash(str(error))
        else:
            flash(f"Estatus guardado: {nuevo}." if cambio else "La cotización ya tenía ese estatus; no cambió nada.")
        return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))

    # ---------- RF-14 Edición (solo pendiente) ----------
    @app.route("/cotizaciones/<int:id_cotizacion>/editar", methods=["GET", "POST"])
    @login_requerido
    def cotizacion_editar(id_cotizacion):
        cotizacion = cotizacion_o_404(id_cotizacion)
        if not cotizaciones_estado.puede_editarse(cotizacion):
            flash(cotizaciones_estado.AVISO_CERRADA.format(estatus=cotizacion["estatus"]))
            return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))
        cliente = almacenamiento_datos.obtener_cliente(bd(), cotizacion["id_cliente"])
        renglones = [{"id_concepto": r["id_concepto"],
                      "cantidad": calculadora_cotizacion.formato_cantidad(r["cantidad"]).replace(",", ""),
                      "precio": f"{r['precio'] / 100:.2f}"} for r in cotizaciones_edicion.renglones_de(cotizacion)]
        error = None
        if request.method == "POST":
            ids = request.form.getlist("id_concepto", type=int)
            cantidades = request.form.getlist("cantidad")
            precios = request.form.getlist("precio")
            quitar = set(request.form.getlist("quitar", type=int))
            renglones = [{"id_concepto": i, "cantidad": c, "precio": p or None}
                         for n, (i, c, p) in enumerate(zip(ids, cantidades, precios)) if n not in quitar]
            nuevo = request.form.get("nuevo_concepto", type=int)
            if nuevo:
                renglones.append({"id_concepto": nuevo, "cantidad": request.form.get("nueva_cantidad") or "1",
                                  "precio": None})
            if request.form.get("accion") == "guardar":
                try:
                    resultado = cotizaciones_edicion.editar_cotizacion(
                        bd(), id_cotizacion, renglones, request.form.get("id_direccion"), app.config["CARPETA_PDF"])
                except ErrorCotizacion as falla:
                    error = str(falla)
                else:
                    flash(resultado["aviso"] or "Cambios guardados; se recalculó el total y se regeneró el PDF.")
                    return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))
        descripciones = almacenamiento_datos.obtener_conceptos(bd(), [r["id_concepto"] for r in renglones])
        conceptos_lista = almacenamiento_datos.buscar_conceptos(bd(), origen="manual") + \
            almacenamiento_datos.buscar_conceptos(bd(), origen="syscom")
        return render_template("cotizacion_editar.html", c=cotizacion, cliente=cliente, renglones=renglones,
                               descripciones=descripciones, conceptos=conceptos_lista, error=error), \
            (400 if error else 200)

    # ---------- RF-15 Duplicar cerrada ----------
    @app.route("/cotizaciones/<int:id_cotizacion>/duplicar", methods=["GET", "POST"])
    @login_requerido
    def cotizacion_duplicar(id_cotizacion):
        cotizacion = cotizacion_o_404(id_cotizacion)
        if request.method == "POST":
            try:
                id_nueva, folio = cotizaciones_duplicado.duplicar(
                    bd(), id_cotizacion, request.form.get("id_cliente"), request.form.get("id_direccion"))
            except ErrorCotizacion as error:
                flash(str(error))
                return redirect(url_for("cotizacion_detalle", id_cotizacion=id_cotizacion))
            flash(f"Se creó la cotización {folio} (pendiente) con precios vigentes. Revise los conceptos señalados.")
            generar_pdf_con_aviso(id_nueva)
            return redirect(url_for("cotizacion_detalle", id_cotizacion=id_nueva))
        texto = request.args.get("q", "")
        clientes = []
        if texto.strip():
            try:
                encontrados = clientes_busqueda.buscar_clientes(bd(), texto)["resultados"]
            except clientes_busqueda.ErrorBusqueda as error:
                flash(str(error))
                encontrados = []
            clientes = [almacenamiento_datos.obtener_cliente(bd(), c["id_cliente"]) for c in encontrados]
        actual = almacenamiento_datos.obtener_cliente(bd(), cotizacion["id_cliente"])
        return render_template("cotizacion_duplicar.html", c=cotizacion, actual=actual, clientes=clientes, q=texto)

    @app.errorhandler(404)
    def no_encontrado(error):
        return render_template("error.html", mensaje=error.description), 404

    @app.errorhandler(400)
    def solicitud_invalida(error):
        return render_template("error.html", mensaje=error.description), 400

    return app


if __name__ == "__main__":
    crear_app().run(
        host=os.environ.get("PRESUPACL_HOST", "127.0.0.1"),
        port=int(os.environ.get("PRESUPACL_PORT", "8000")),
        debug=False,
    )
