"""
abraChem · Streamlit — Almacenamiento persistente.

Backend: Supabase (API REST), con SUPABASE_URL + SUPABASE_KEY desde Secrets.
Si Supabase no está disponible, cae a SQLite local.

Migración automática: si en algún momento anterior los datos quedaron
guardados en SQLite local (por ejemplo, mientras Supabase no conectaba)
y ahora Supabase sí funciona, las filas de SQLite se suben solas a
Supabase la primera vez, sin perder nada.
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
_BACKEND = None
_FALLO_MOTIVO = None


def _sqlite_conn():
    import sqlite3
    db_path = _HERE / "data" / "abrachem_st.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def _sqlite_has_table() -> bool:
    try:
        with _sqlite_conn() as c:
            r = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='resultados'"
            ).fetchone()
        return r is not None
    except Exception:
        return False


def _migrar_sqlite_a_supabase():
    """Si hay filas en SQLite local que no están en Supabase, las sube.
    Se ejecuta solo una vez por arranque, de forma segura (no duplica)."""
    if not _sqlite_has_table():
        return
    try:
        with _sqlite_conn() as c:
            filas_local = c.execute("SELECT * FROM resultados").fetchall()
        if not filas_local:
            return

        ya_en_supabase = set(found_emails())  # usa el backend ya fijado en supabase
        subidas = 0
        for r in filas_local:
            d = dict(r)
            email = (d.get("email") or "").lower().strip()
            if email and email in ya_en_supabase:
                continue  # ya está, no duplicar
            payload = {k: str(d.get(k, "") or "") for k in SUPABASE_CAMPOS}
            try:
                _SUPABASE.table(SUPABASE_TABLE).insert(payload).execute()
                subidas += 1
                if email:
                    ya_en_supabase.add(email)
            except Exception:
                pass  # si una fila puntual falla, seguimos con el resto

        if subidas:
            import logging
            logging.warning(f"Migración automática: {subidas} prospecto(s) "
                            f"subido(s) de SQLite local a Supabase.")
    except Exception as e:
        import logging
        logging.warning(f"Migración SQLite→Supabase no se pudo completar: {e}")


def init_db():
    """Detecta el backend probando una operación REAL (insert+delete de
    prueba), no solo lectura — así no se confunde con falsos positivos de
    RLS que permiten SELECT pero bloquean INSERT. Si Supabase queda activo,
    migra automáticamente cualquier dato que haya quedado en SQLite."""
    global _SUPABASE, _BACKEND, _FALLO_MOTIVO
    _FALLO_MOTIVO = None

    cliente, err = _get_supabase_client()
    if cliente is None:
        _FALLO_MOTIVO = err
    else:
        try:
            # Prueba real: insertar una fila de diagnóstico y borrarla.
            # Esto confirma permisos de INSERT, no solo de SELECT.
            probe = {k: "" for k in SUPABASE_CAMPOS}
            probe["laboratorio"] = "__diagnostico_conexion__"
            ins = cliente.table(SUPABASE_TABLE).insert(probe).execute()
            probe_id = ins.data[0]["id"] if ins.data else None
            if probe_id is not None:
                cliente.table(SUPABASE_TABLE).delete().eq("id", probe_id).execute()

            _SUPABASE = cliente
            _BACKEND = "supabase"
            _migrar_sqlite_a_supabase()
            return
        except Exception as e:
            _FALLO_MOTIVO = f"Supabase respondió con un error: {e}"

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
               .neq("laboratorio", "__diagnostico_conexion__")
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
