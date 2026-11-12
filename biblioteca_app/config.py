"""Configuración de la aplicación.

Los valores se pueden sobreescribir con variables de entorno para no
guardar credenciales dentro del código fuente.
"""
import os


class Config:
    # Clave para los mensajes flash (cambiar en producción)
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")

    # Conexión a MySQL (base de datos indicada: biblioteca, en localhost)
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "biblioteca")
