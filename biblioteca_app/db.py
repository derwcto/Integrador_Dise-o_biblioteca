"""Capa de acceso a datos.

Centraliza la creación de conexiones y ofrece helpers pequeños
para consultas, escrituras y transacciones.
"""
import contextlib

import pymysql
from pymysql.cursors import DictCursor

from config import Config


def get_connection():
    """Abre una nueva conexión a MySQL configurada desde variables de entorno."""
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def query(sql, params=(), one=False):
    """Ejecuta un SELECT y devuelve filas (dict). `one=True` devuelve solo la primera."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def execute(sql, params=()):
    """Ejecuta un INSERT/UPDATE/DELETE y confirma. Devuelve el lastrowid."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextlib.contextmanager
def transaction():
    """Bloque transaccional: confirma al final o revierte si ocurre un error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
