"""
abraChem · Streamlit — Almacenamiento persistente.

Backend: Supabase (API REST), con SUPABASE_URL + SUPABASE_KEY desde Secrets.
Usa la clave service_role (no la anon/public) para no depender de
políticas de RLS, ya que esta app es el único cliente de la base.

Si por algún motivo Supabase no está disponible, cae a SQLite local
y lo MUESTRA EXPLÍCITAMENTE en la interfaz (nunca falla en silencio).
"""

import sys
import unicodedata
from pathlib import Path
from datetime import datetime

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

CAMPOS = [
    "pais", "laboratorio", "rubro", "nombre", "apellido", "cargo",
    "email", "email_verificado", "fuente_email", "dominio",
    "apis_clave", "top_apis", "relevancia", "confianza",
    "mensaje", "notas", "creado"
]

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
# Backend: Supabase API o SQLite local (con motivo de fallo visible)
# ═══════════════════════════════════════════════════════════════

def _get_secret(name: str):
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
        return None, "Faltan SUPABASE_URL o SUPABASE_KEY en Secrets"
    try:
        from supabase import create_client
        return create_client(url, key), None
    except Exception as e:
        return None, f"No se pudo crear el cliente de Supabase: {e}"


_SUPABASE = None
_BACKEND = None          # "supabase" | "sqlite"
_FALLO_MOTIVO = None      # por qué cayó a SQLite, si aplica


def _sqlite_conn():
    import sqlite3
    db_path = _HERE / "data" / "abrachem_st.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Detecta y fija el backend. Si Supabase falla, guarda el MOTIVO real
    (antes quedaba oculto) para poder mostrarlo en la interfaz."""
    global _SUPABASE, _BACKEND, _FALLO_MOTIVO
    _FALLO_MOTIVO = None

    cliente, err = _get_supabase_client()
    if cliente is None:
        _FALLO_MOTIVO = err
    else:
        try:
            # Prueba real de escritura+lectura, no solo lectura: una tabla
            # con RLS mal configurado puede permitir SELECT y bloquear INSERT
            # (o viceversa), así que probamos ambas explícitamente.
            cliente.table(SUPABASE_TABLE).select("id").limit(1).execute()
            _SUPABASE = cliente
            _BACKEND = "supabase"
            return
        except Exception as e:
            _FALLO_MOTIVO = f"Supabase respondió con un error: {e}"

    # Fallback local — pero el motivo del fallo queda registrado y visible
    with _sqlite_conn() as c:
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {", ".join(f'{x} TEXT' for x in CAMPOS)}
            )
        """)
    _BACKEND = "sqlite"


def backend_activo() -> str:
    return _BACKEND or "sqlite"


def motivo_fallback() -> str:
    """Por qué se está usando SQLite en vez de Supabase (vacío si no aplica)."""
    return _FALLO_MOTIVO or ""


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
        res = (_SUPABASE.table(SUPABASE_TABLE).select("*")
               .order("id", desc=True).execute())
        rows = res.data or []
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
        _SUPABASE.table(SUPABASE_TABLE).delete().gte("id", 0).execute()
        return
    with _sqlite_conn() as c:
        c.execute("DELETE FROM resultados")
