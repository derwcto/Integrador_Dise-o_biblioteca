"""Sistema de Biblioteca — aplicación Flask.

Pantallas:
  /            Panel principal (resumen)
  /libros      CRUD de Libros (registrar, editar, listar, eliminar)
  /prestamos   Gestión de préstamos y devoluciones
               - Registra un préstamo llamando a sp_RegistrarPrestamo
               - Registra la devolución calculando la multa con
                 fn_CalcularMultaPorRetraso
"""
from datetime import date

import pymysql
from flask import Flask, flash, redirect, render_template, request, url_for

from config import Config
from db import execute, get_connection, query, transaction

app = Flask(__name__)
app.config.from_object(Config)


# ---------------------------------------------------------------------------
# Utilidad: errores de base de datos convertidos en mensajes amigables
# ---------------------------------------------------------------------------
def db_error_message(exc):
    if isinstance(exc, pymysql.MySQLError):
        # SIGNAL SQLSTATE '45000' -> mensaje de negocio definido en el SP
        code, msg = exc.args[0], (exc.args[1] if len(exc.args) > 1 else str(exc))
        if code == 1062:  # duplicate entry
            return f"Registro duplicado: {msg}"
        if code == 1216 or code == 1217 or code == 1451:  # FK constraints
            return "No se puede eliminar: existen registros relacionados (préstamos)."
        return msg
    return str(exc)


# ---------------------------------------------------------------------------
# Ruta raíz — panel de resumen
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    resumen = {"libros": 0, "stock": 0, "lectores": 0, "activos": 0}
    db_error = None
    try:
        row = query(
            "SELECT COUNT(*) AS libros, COALESCE(SUM(stock_disponible), 0) AS stock "
            "FROM Libros", one=True)
        resumen.update(libros=row["libros"], stock=int(row["stock"]))
        row = query(
            "SELECT COUNT(*) AS lectores FROM Lectores WHERE estado = 'ACTIVO'", one=True)
        resumen.update(lectores=row["lectores"])
        row = query(
            "SELECT COUNT(*) AS activos FROM Detalle_Prestamos WHERE estado = 'ACTIVO'",
            one=True)
        resumen.update(activos=row["activos"])
    except pymysql.MySQLError as e:
        db_error = db_error_message(e)
    return render_template("index.html", resumen=resumen, db_error=db_error)


# ===========================================================================
# CRUD 1 — MANTENIMIENTO DE LIBROS
# ===========================================================================
@app.route("/libros")
def libros_lista():
    q = (request.args.get("q") or "").strip()
    try:
        if q:
            like = f"%{q}%"
            libros = query(
                "SELECT * FROM Libros WHERE titulo LIKE %s OR isbn LIKE %s "
                "ORDER BY titulo", (like, like))
        else:
            libros = query("SELECT * FROM Libros ORDER BY titulo")
        db_error = None
    except pymysql.MySQLError as e:
        libros, db_error = [], db_error_message(e)
    return render_template("libros.html", libros=libros, q=q, db_error=db_error)


@app.route("/libros/nuevo", methods=["GET", "POST"])
def libros_nuevo():
    if request.method == "POST":
        titulo = (request.form.get("titulo") or "").strip()
        isbn = (request.form.get("isbn") or "").strip()
        stock = request.form.get("stock_disponible") or "0"

        if not titulo or not isbn:
            flash("El título y el ISBN son obligatorios.", "error")
            return redirect(url_for("libros_nuevo"))
        try:
            stock = int(stock)
            if stock < 0:
                raise ValueError
        except ValueError:
            flash("El stock debe ser un número entero mayor o igual a 0.", "error")
            return redirect(url_for("libros_nuevo"))

        try:
            execute(
                "INSERT INTO Libros (titulo, isbn, stock_disponible) VALUES (%s, %s, %s)",
                (titulo, isbn, stock))
            flash(f"Libro «{titulo}» registrado correctamente.", "success")
            return redirect(url_for("libros_lista"))
        except pymysql.MySQLError as e:
            flash(db_error_message(e), "error")
            return redirect(url_for("libros_nuevo"))

    return render_template("libro_form.html", libro=None, accion="Registrar libro")


@app.route("/libros/<int:id_libro>/editar", methods=["GET", "POST"])
def libros_editar(id_libro):
    try:
        libro = query("SELECT * FROM Libros WHERE id_libro = %s", (id_libro,), one=True)
    except pymysql.MySQLError as e:
        flash(db_error_message(e), "error")
        return redirect(url_for("libros_lista"))

    if not libro:
        flash("El libro indicado no existe.", "error")
        return redirect(url_for("libros_lista"))

    if request.method == "POST":
        titulo = (request.form.get("titulo") or "").strip()
        isbn = (request.form.get("isbn") or "").strip()
        stock = request.form.get("stock_disponible") or "0"

        if not titulo or not isbn:
            flash("El título y el ISBN son obligatorios.", "error")
            return redirect(url_for("libros_editar", id_libro=id_libro))
        try:
            stock = int(stock)
            if stock < 0:
                raise ValueError
        except ValueError:
            flash("El stock debe ser un número entero mayor o igual a 0.", "error")
            return redirect(url_for("libros_editar", id_libro=id_libro))

        try:
            execute(
                "UPDATE Libros SET titulo = %s, isbn = %s, stock_disponible = %s "
                "WHERE id_libro = %s",
                (titulo, isbn, stock, id_libro))
            flash(f"Libro «{titulo}» actualizado.", "success")
            return redirect(url_for("libros_lista"))
        except pymysql.MySQLError as e:
            flash(db_error_message(e), "error")
            return redirect(url_for("libros_editar", id_libro=id_libro))

    return render_template("libro_form.html", libro=libro, accion="Editar libro")


@app.route("/libros/<int:id_libro>/eliminar", methods=["POST"])
def libros_eliminar(id_libro):
    try:
        prestamos_activos = query(
            "SELECT COUNT(*) AS n FROM Detalle_Prestamos "
            "WHERE id_libro = %s AND estado = 'ACTIVO'", (id_libro,), one=True)["n"]
        if prestamos_activos:
            flash("No se puede eliminar: el libro tiene préstamos activos.", "error")
            return redirect(url_for("libros_lista"))

        execute("DELETE FROM Libros WHERE id_libro = %s", (id_libro,))
        flash("Libro eliminado correctamente.", "success")
    except pymysql.MySQLError as e:
        flash(db_error_message(e), "error")
    return redirect(url_for("libros_lista"))


# ===========================================================================
# CRUD 2 — GESTIÓN DE PRÉSTAMOS Y DEVOLUCIONES
# ===========================================================================
@app.route("/prestamos")
def prestamos():
    db_error = None
    try:
        lectores = query(
            "SELECT id_lector, dni, nombres FROM Lectores "
            "WHERE estado = 'ACTIVO' ORDER BY nombres")
        libros = query(
            "SELECT id_libro, titulo, isbn, stock_disponible FROM Libros "
            "WHERE stock_disponible > 0 ORDER BY titulo")
        prestamos_activos = query(
            """SELECT d.id_detalle,
                      p.id_prestamo,
                      l.dni,
                      l.nombres,
                      lib.titulo,
                      p.fecha_prestamo,
                      d.fecha_devolucion_pactada,
                      GREATEST(DATEDIFF(CURDATE(), d.fecha_devolucion_pactada), 0) AS dias_retraso
                 FROM Detalle_Prestamos d
                 JOIN Prestamos p ON p.id_prestamo = d.id_prestamo
                 JOIN Lectores  l  ON l.id_lector   = p.id_lector
                 JOIN Libros    lib ON lib.id_libro  = d.id_libro
                WHERE d.estado = 'ACTIVO'
                ORDER BY d.fecha_devolucion_pactada ASC""")
        ultimas_devoluciones = query(
            """SELECT d.id_detalle, l.nombres, lib.titulo,
                      d.fecha_devolucion_pactada, d.fecha_devolucion_real, d.multa
                 FROM Detalle_Prestamos d
                 JOIN Prestamos p ON p.id_prestamo = d.id_prestamo
                 JOIN Lectores  l  ON l.id_lector   = p.id_lector
                 JOIN Libros    lib ON lib.id_libro  = d.id_libro
                WHERE d.estado = 'DEVUELTO'
                ORDER BY d.fecha_devolucion_real DESC, d.id_detalle DESC
                LIMIT 5""")
    except pymysql.MySQLError as e:
        lectores, libros, prestamos_activos, ultimas_devoluciones = [], [], [], []
        db_error = db_error_message(e)

    return render_template(
        "prestamos.html",
        lectores=lectores,
        libros=libros,
        prestamos_activos=prestamos_activos,
        ultimas_devoluciones=ultimas_devoluciones,
        hoy=date.today().isoformat(),
        db_error=db_error,
    )


@app.route("/prestamos/registrar", methods=["POST"])
def prestamos_registrar():
    id_lector = request.form.get("id_lector") or ""
    id_libro = request.form.get("id_libro") or ""
    dias = request.form.get("dias_prestamo") or "7"

    try:
        id_lector, id_libro, dias = int(id_lector), int(id_libro), int(dias)
        if dias <= 0:
            raise ValueError
    except ValueError:
        flash("Datos del préstamo inválidos.", "error")
        return redirect(url_for("prestamos"))

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Llamada al procedimiento almacenado indicado
            cur.execute("CALL sp_RegistrarPrestamo(%s, %s, %s)", (id_lector, id_libro, dias))
            resultado = cur.fetchone()  # SELECT final del SP (dict)
            # Consumir los result sets restantes que genera CALL
            while cur.nextset():
                pass
        conn.commit()
        mensaje = resultado.get("mensaje") if resultado else "Préstamo registrado."
        flash(mensaje, "success")
    except pymysql.MySQLError as e:
        if conn:
            conn.rollback()
        # Los SIGNAL del SP llegan como error 1644 con el mensaje en claro
        flash(f"No se pudo registrar el préstamo: {db_error_message(e)}", "error")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("prestamos"))


@app.route("/prestamos/<int:id_detalle>/devolver", methods=["POST"])
def prestamos_devolver(id_detalle):
    fecha_real_txt = (request.form.get("fecha_devolucion_real") or "").strip()
    try:
        fecha_real = date.fromisoformat(fecha_real_txt) if fecha_real_txt else date.today()
    except ValueError:
        flash("La fecha de devolución no es válida.", "error")
        return redirect(url_for("prestamos"))

    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                # 1) Recuperar el detalle activo (con datos del préstamo)
                cur.execute(
                    """SELECT d.id_detalle, d.id_prestamo, d.id_libro, d.estado,
                              d.fecha_devolucion_pactada, p.id_lector
                         FROM Detalle_Prestamos d
                         JOIN Prestamos p ON p.id_prestamo = d.id_prestamo
                        WHERE d.id_detalle = %s
                        FOR UPDATE""",
                    (id_detalle,))
                detalle = cur.fetchone()

                if not detalle:
                    flash("El detalle de préstamo no existe.", "error")
                    return redirect(url_for("prestamos"))
                if detalle["estado"] != "ACTIVO":
                    flash("Este libro ya fue devuelto.", "warning")
                    return redirect(url_for("prestamos"))

                # 2) Multa calculada con la función almacenada
                cur.execute(
                    "SELECT fn_CalcularMultaPorRetraso(%s, %s) AS multa",
                    (detalle["fecha_devolucion_pactada"], fecha_real))
                multa = cur.fetchone()["multa"]

                # 3) Actualizar el detalle
                cur.execute(
                    """UPDATE Detalle_Prestamos
                          SET estado = 'DEVUELTO',
                              fecha_devolucion_real = %s,
                              multa = %s
                        WHERE id_detalle = %s""",
                    (fecha_real, multa, id_detalle))

                # 4) Reponer stock del libro
                cur.execute(
                    "UPDATE Libros SET stock_disponible = stock_disponible + 1 "
                    "WHERE id_libro = %s",
                    (detalle["id_libro"],))

                # 5) Si no quedan líneas activas en el préstamo, cerrarlo
                cur.execute(
                    "SELECT COUNT(*) AS pendientes FROM Detalle_Prestamos "
                    "WHERE id_prestamo = %s AND estado = 'ACTIVO'",
                    (detalle["id_prestamo"],))
                pendientes = cur.fetchone()["pendientes"]
                if pendientes == 0:
                    cur.execute(
                        "UPDATE Prestamos SET estado = 'DEVUELTO' WHERE id_prestamo = %s",
                        (detalle["id_prestamo"],))

        if multa and float(multa) > 0:
            flash(
                f"Devolución registrada. Multa por retraso: "
                f"S/ {float(multa):,.2f} (según fn_CalcularMultaPorRetraso).",
                "warning")
        else:
            flash("Devolución registrada a tiempo. Multa: S/ 0.00.", "success")
    except pymysql.MySQLError as e:
        flash(f"No se pudo registrar la devolución: {db_error_message(e)}", "error")
    return redirect(url_for("prestamos"))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
