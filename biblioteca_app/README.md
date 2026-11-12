# 📚 Sistema de Biblioteca (Flask + MySQL)

Aplicación web en **Python Flask** conectada a una base de datos **MySQL** llamada `biblioteca` en localhost.

## Pantallas

1. **Mantenimiento de Libros (CRUD 1)** — `/libros`
   - Listar libros con buscador (título/ISBN), registrar, editar y eliminar (con validación de préstamos activos).
2. **Gestión de Préstamos y Devoluciones (CRUD 2)** — `/prestamos`
   - Registrar préstamo: seleccionas lector y libro → llama al procedimiento `sp_RegistrarPrestamo(p_id_lector, p_id_libro, p_dias_prestamo)`.
   - Registrar devolución: calcula la multa con la función `fn_CalcularMultaPorRetraso(p_fecha_pactada, p_fecha_real)`, repone el stock y cierra el préstamo cuando no quedan líneas pendientes.
   - Muestra las últimas 5 devoluciones con su multa.

## Requisitos

- Python 3.10+
- MySQL Server 8.x (o MariaDB 10.6+)
- Base de datos `biblioteca`

## Puesta en marcha (paso a paso)

```bash
# 1) Entra a la carpeta del proyecto
cd biblioteca_app

# 2) Crea y activa un entorno virtual
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate     # Linux / macOS

# 3) Instala dependencias
pip install -r requirements.txt

# 4) Crea la base de datos, tablas, procedimiento y función
#    (usa tus credenciales por variable de entorno)
set DB_USER=root                # Windows (PowerShell: $env:DB_USER='root')
set DB_PASSWORD=tu_password
python apply_schema.py

# 5) Arranca la aplicación
python app.py
# → http://localhost:5000
```

### Variables de entorno soportadas

| Variable      | Valor por defecto | Descripción                    |
|---------------|-------------------|--------------------------------|
| `DB_HOST`     | `localhost`       | Servidor MySQL                 |
| `DB_PORT`     | `3306`            | Puerto                         |
| `DB_USER`     | `root`            | Usuario                        |
| `DB_PASSWORD` | *(vacío)*         | Contraseña                     |
| `DB_NAME`     | `biblioteca`      | Base de datos                  |
| `SECRET_KEY`  | *(dev)*           | Clave de sesión de Flask       |

## Contrato de datos (importante)

La aplicación espera estas columnas mínimas. Si tu base de datos **ya existe** con estas tablas (o similares), compara esta lista y adapta `app.py`/`schema.sql` si difiere:

- **Libros**: `id_libro`, `titulo`, `isbn` (único), `stock_disponible`
- **Lectores**: `id_lector`, `dni`, `nombres`, `estado` (`ACTIVO`/`INACTIVO`/`MOROSO`)
- **Prestamos**: `id_prestamo`, `id_lector`, `fecha_prestamo`, `fecha_devolucion_pactada`, `estado` (`ACTIVO`/`DEVUELTO`)
- **Detalle_Prestamos**: `id_detalle`, `id_prestamo`, `id_libro`, `cantidad`, `fecha_devolucion_pactada`, `fecha_devolucion_real`, `multa`, `estado`
- **Procedimiento**: `sp_RegistrarPrestamo(IN p_id_lector INT, IN p_id_libro INT, IN p_dias_prestamo INT)` — valida y registra el préstamo, descuenta 1 unidad de stock. Lanza errores con `SIGNAL SQLSTATE '45000'`, que la app muestra como mensaje amigable.
- **Función**: `fn_CalcularMultaPorRetraso(p_fecha_pactada DATE, p_fecha_real DATE) RETURNS DECIMAL(10,2)` — 1.00 por día de retraso, 0.00 si no hay retraso. Ajusta la tarifa dentro de la función si tu regla es distinta.

`schema.sql` crea todo esto desde cero (con datos de ejemplo) y es idempotente. Si tu instalación existente tiene otros nombres o columnas, edita `schema.sql` para que coincida o crea solo el procedimiento/función con los del mismo contrato.

## Estructura

```
biblioteca_app/
├── app.py             # Rutas Flask (las 2 pantallas + panel)
├── config.py          # Config por variables de entorno
├── db.py              # Acceso a datos (conexión, transacciones)
├── schema.sql         # DDL: biblioteca, tablas, SP, función, seed
├── apply_schema.py    # Aplica schema.sql (maneja DELIMITER)
├── requirements.txt
├── templates/         # layout, index, libros, libro_form, prestamos
└── static/            # style.css, app.js
```

## Notas

- Sin CSRF que cubrir porque las acciones son locales; en producción añade CSRF (p. ej. Flask-WTF) y HTTPS.
- El borrado de libros bloquea si hay `Detalle_Prestamos` con estado `ACTIVO`.
- La devolución de un detalle cierra el préstamo completo cuando no quedan líneas activas.
- Credenciales nunca en el código: usa variables de entorno.
