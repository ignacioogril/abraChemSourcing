"""
abraChem · Streamlit — Almacenamiento persistente.

Versión Supabase API:
- En Streamlit Cloud usa SUPABASE_URL + SUPABASE_KEY desde Secrets.
- Guarda/lee los prospectos en la tabla Supabase: prospectos.
- Si no hay credenciales, cae a SQLite para uso local.
"""

import sys
import unicodedata
from pathlib import Path
from datetime import datetime

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Campos que maneja la app internamente
CAMPOS = [
    "pais", "laboratorio", "rubro", "nombre", "apellido", "cargo",
    "email", "email_verificado", "fuente_email", "dominio",
    "apis_clave", "top_apis", "relevancia", "confianza",
    "mensaje", "notas", "creado"
]

# Campos que existen en la tabla Supabase que creaste
SUPABASE_TABLE = "prospectos"
SUPABASE_CAMPOS = [
    "pais", "laboratorio", "nombre", "apellido", "cargo",
    "email", "dominio", "apis_clave", "top_apis",
    "relevancia", "confianza", "mensaje"
]


def norm_lab(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


# ═══════════════════════════════════════════════════════════════
# Backend: Supabase API o SQLite local
# ═══════════════════════════════════════════════════════════════

def _get_secret(name: str) -> str | None:
    import os

    try:
        import streamlit as st
        try:
            if name in st.secrets and st.secrets[name]:
                return str(st.secrets[name])
        except Exception:
            pass
    except Exception:
        pass

    return os.environ.get(name)


def _get_supabase_client():
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")

    if not url or not key:
        return None

    from supabase import create_client
    return create_client(url, key)


_SUPABASE = None
_BACKEND = None  # "supabase" | "sqlite"


def _sqlite_conn():
    import sqlite3
    db_path = _HERE / "data" / "abrachem_st.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """
    Detecta y fija el backend a usar.

    IMPORTANTE:
    La tabla de Supabase debe existir. Ya la creaste como 'prospectos'.
    """
    global _SUPABASE, _BACKEND

    try:
        _SUPABASE = _get_supabase_client()
        if _SUPABASE is not None:
            # Prueba mínima de lectura. Si falla, cae a SQLite.
            _SUPABASE.table(SUPABASE_TABLE).select("id").limit(1).execute()
            _BACKEND = "supabase"
            return
    except Exception as e:
        import logging
        logging.warning(f"No se pudo conectar a Supabase API, usando SQLite local: {e}")

    # Fallback local
    with _sqlite_conn() as c:
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {", ".join(f'{x} TEXT' for x in CAMPOS)}
            )
        """)
    _BACKEND = "sqlite"


def backend_activo() -> str:
    """'supabase' si está conectado a la base compartida, o 'sqlite' local."""
    return _BACKEND or "sqlite"


def add_resultado(d: dict):
    creado = datetime.now().strftime("%d/%m/%Y %H:%M")
    d = {**d, "creado": creado}

    if _BACKEND == "supabase":
        payload = {k: str(d.get(k, "") or "") for k in SUPABASE_CAMPOS}
        _SUPABASE.table(SUPABASE_TABLE).insert(payload).execute()
        return

    with _sqlite_conn() as c:
        cols = [k for k in CAMPOS if k in d]
        c.execute(
            f"INSERT INTO resultados ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [d.get(k, "") for k in cols],
        )


def get_all() -> list:
    if _BACKEND == "supabase":
        res = (
            _SUPABASE
            .table(SUPABASE_TABLE)
            .select("*")
            .order("id", desc=True)
            .execute()
        )
        rows = res.data or []

        # Para que streamlit_app.py pueda usar f.get("creado") aunque Supabase use created_at
        for r in rows:
            if "creado" not in r:
                r["creado"] = r.get("created_at", "")
        return rows

    with _sqlite_conn() as c:
        rows = c.execute("SELECT * FROM resultados ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def found_emails() -> set:
    if _BACKEND == "supabase":
        res = _SUPABASE.table(SUPABASE_TABLE).select("email").execute()
        rows = res.data or []
        return {(r.get("email") or "").lower().strip() for r in rows if r.get("email")}

    with _sqlite_conn() as c:
        rows = c.execute("SELECT email FROM resultados").fetchall()
    return {(r["email"] or "").lower().strip() for r in rows if r["email"]}


def found_labs() -> set:
    if _BACKEND == "supabase":
        res = _SUPABASE.table(SUPABASE_TABLE).select("laboratorio").execute()
        rows = res.data or []
        return {norm_lab(r.get("laboratorio")) for r in rows if r.get("laboratorio")}

    with _sqlite_conn() as c:
        rows = c.execute("SELECT laboratorio FROM resultados").fetchall()
    return {norm_lab(r["laboratorio"]) for r in rows if r["laboratorio"]}


def delete_all():
    if _BACKEND == "supabase":
        # Supabase requiere un filtro para delete.
        _SUPABASE.table(SUPABASE_TABLE).delete().gte("id", 0).execute()
        return

    with _sqlite_conn() as c:
        c.execute("DELETE FROM resultados")
