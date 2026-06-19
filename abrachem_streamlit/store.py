"""
abraChem · Streamlit — Almacenamiento persistente.

Usa Postgres (Supabase) si hay credenciales configuradas — esto persiste
PARA SIEMPRE, incluso si la app de Streamlit se reinicia o redeploya.
Si no hay credenciales (uso local rápido), cae a SQLite automáticamente.
"""
import sys
import unicodedata
from pathlib import Path
from datetime import datetime

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

CAMPOS = ["pais", "laboratorio", "rubro", "nombre", "apellido", "cargo",
          "email", "email_verificado", "fuente_email", "dominio",
          "apis_clave", "top_apis", "relevancia", "confianza",
          "mensaje", "notas", "creado"]


def norm_lab(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


# ═══════════════════════════════════════════════════════════════
# Backend: detecta Postgres (Supabase) o cae a SQLite
# ═══════════════════════════════════════════════════════════════

def _get_pg_url():
    """Busca la URL de Postgres en st.secrets o variables de entorno."""
    import os
    try:
        import streamlit as st
        for key in ("SUPABASE_DB_URL", "DATABASE_URL"):
            try:
                if key in st.secrets and st.secrets[key]:
                    return str(st.secrets[key])
            except Exception:
                pass
    except Exception:
        pass
    for key in ("SUPABASE_DB_URL", "DATABASE_URL"):
        v = os.environ.get(key)
        if v:
            return v
    return None


_PG_URL = _get_pg_url()
_BACKEND = None  # "postgres" | "sqlite"


def _pg_conn():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(_PG_URL, sslmode="require")
    return conn


def _sqlite_conn():
    import sqlite3
    db_path = _HERE / "data" / "abrachem_st.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Crea la tabla si no existe. Detecta y fija el backend a usar."""
    global _BACKEND
    if _PG_URL:
        try:
            conn = _pg_conn()
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS resultados (
                    id SERIAL PRIMARY KEY,
                    {", ".join(f'{x} TEXT' for x in CAMPOS)}
                )
            """)
            conn.commit()
            cur.close(); conn.close()
            _BACKEND = "postgres"
            return
        except Exception as e:
            import logging
            logging.warning(f"No se pudo conectar a Postgres, usando SQLite local: {e}")
    # Fallback: SQLite (no persiste entre redeploys en la nube, pero
    # funciona perfecto para uso local).
    with _sqlite_conn() as c:
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {", ".join(f'{x} TEXT' for x in CAMPOS)}
            )
        """)
    _BACKEND = "sqlite"


def backend_activo() -> str:
    """'postgres' (persistencia permanente) o 'sqlite' (local/temporal)."""
    return _BACKEND or "sqlite"


def add_resultado(d: dict):
    d = {**d, "creado": datetime.now().strftime("%d/%m/%Y %H:%M")}
    cols = [k for k in CAMPOS if k in d]
    if _BACKEND == "postgres":
        conn = _pg_conn(); cur = conn.cursor()
        placeholders = ", ".join(["%s"] * len(cols))
        cur.execute(
            f"INSERT INTO resultados ({', '.join(cols)}) VALUES ({placeholders})",
            [d.get(k, "") for k in cols],
        )
        conn.commit(); cur.close(); conn.close()
    else:
        with _sqlite_conn() as c:
            c.execute(
                f"INSERT INTO resultados ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                [d.get(k, "") for k in cols],
            )


def get_all() -> list:
    if _BACKEND == "postgres":
        import psycopg2.extras
        conn = _pg_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM resultados ORDER BY id DESC")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return rows
    with _sqlite_conn() as c:
        rows = c.execute("SELECT * FROM resultados ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def found_emails() -> set:
    if _BACKEND == "postgres":
        conn = _pg_conn(); cur = conn.cursor()
        cur.execute("SELECT email FROM resultados")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {(r[0] or "").lower().strip() for r in rows if r[0]}
    with _sqlite_conn() as c:
        rows = c.execute("SELECT email FROM resultados").fetchall()
    return {(r["email"] or "").lower().strip() for r in rows if r["email"]}


def found_labs() -> set:
    if _BACKEND == "postgres":
        conn = _pg_conn(); cur = conn.cursor()
        cur.execute("SELECT laboratorio FROM resultados")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {norm_lab(r[0]) for r in rows if r[0]}
    with _sqlite_conn() as c:
        rows = c.execute("SELECT laboratorio FROM resultados").fetchall()
    return {norm_lab(r["laboratorio"]) for r in rows}


def delete_all():
    if _BACKEND == "postgres":
        conn = _pg_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM resultados")
        conn.commit(); cur.close(); conn.close()
    else:
        with _sqlite_conn() as c:
            c.execute("DELETE FROM resultados")
