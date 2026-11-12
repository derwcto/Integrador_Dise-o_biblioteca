"""Aplica schema.sql a la base de datos indicada en la configuración.

Uso:
    python apply_schema.py

Soporta la directiva DELIMITER de los clientes MySQL para crear el
procedimiento y la función (los cuerpos contienen punto y coma).
"""
import re
import sys

import pymysql

from config import Config


def split_statements(sql_text):
    """Divide el script respetando las directivas DELIMITER."""
    statements = []
    delimiter = ";"
    buffer = []

    for raw_line in sql_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        delim_match = re.match(r"^DELIMITER\s+(\S+)", stripped, re.IGNORECASE)
        if delim_match:
            if buffer and "".join(buffer).strip():
                statements.append("".join(buffer))
            buffer = []
            delimiter = delim_match.group(1)
            continue

        if stripped.startswith("--") or not stripped:
            continue  # comentarios y líneas vacías

        buffer.append(raw_line + "\n")

        if delimiter == ";":
            # Punto y coma fin de sentencia (el propio delimiter por omisión)
            while buffer and buffer[-1].rstrip().endswith(";"):
                statement = "".join(buffer)
                statements.append(statement)
                buffer = []
                break
        elif stripped.endswith(delimiter):
            statement = "".join(buffer).rstrip()
            statement = statement[: -len(delimiter)].rstrip()
            statements.append(statement)
            buffer = []

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return [s.strip() for s in statements if s.strip()]


def main():
    print(f"Conectando a MySQL en {Config.DB_HOST}:{Config.DB_PORT} como '{Config.DB_USER}'...")
    conn = pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with open("schema.sql", "r", encoding="utf-8") as f:
            sql_text = f.read()

        statements = split_statements(sql_text)
        print(f"Ejecutando {len(statements)} sentencias...")
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, start=1):
                preview = stmt.replace("\n", " ")[:80]
                print(f"  [{i:>2}] {preview}...")
                cur.execute(stmt)
        print("\nOK: base de datos 'biblioteca' creada/actualizada.")
    except pymysql.MySQLError as e:
        print(f"\nERROR de MySQL ({e.args[0]}): {e.args[1] if len(e.args) > 1 else e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
