"""
abraChem · Streamlit — Almacenamiento persistente en Supabase.

IMPORTANTE:
- Este archivo NO usa SQLite.
- Si Supabase no está bien configurado, falla mostrando el motivo real.
- Usa la Data API REST de Supabase con SUPABASE_URL + SUPABASE_KEY desde Streamlit Secrets.
"""

import os
import sys
import unicodedata
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SUPABASE_TABLE = "prospectos"

# Columnas que realmente insertamos en la tabla prospectos.
# Coinciden con la tabla creada en Supabase.
SUPABASE_CAMPOS = [
    "pais",
    "laboratorio",
    "nombre",
    "apellido",
    "cargo",
    "email",
    "dominio",
    "apis_clave",
    "top_apis",
    "relevancia",
    "confianza",
    "mensaje",
]

_BACKEND = None
_FALLO_MOTIVO = ""


def norm_lab(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _get_secret(name: str) -> str:
    """Lee primero Streamlit Secrets y si no variables de entorno."""
    try:
        import streamlit as st
        try:
            if name in st.secrets and st.secrets[name]:
                return str(st.secrets[name]).strip()
        except Exception:
            pass
    except Exception:
        pass
    return str(os.environ.get(name, "") or "").strip()


def _project_url() -> str:
    """
    Acepta cualquiera de estas formas:
    - https://xxxx.supabase.co
    - https://xxxx.supabase.co/
    - https://xxxx.supabase.co/rest/v1/
    y normaliza a:
    - https://xxxx.supabase.co
    """
    url = _get_secret("SUPABASE_URL")
    if not url:
        return ""

    url = url.strip().rstrip("/")
    url = url.replace("/rest/v1", "")
    return url.rstrip("/")


def _rest_base() -> str:
    url = _project_url()
    if not url:
        return ""
    return f"{url}/rest/v1"


def _key() -> str:
    return _get_secret("SUPABASE_KEY")


def _headers(prefer: str | None = None) -> dict:
    key = _key()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _request(method: str, path: str, **kwargs):
    base = _rest_base()
    if not base:
        raise RuntimeError("Falta SUPABASE_URL en Streamlit Secrets.")
    if not _key():
        raise RuntimeError("Falta SUPABASE_KEY en Streamlit Secrets.")

    url = f"{base}/{path.lstrip('/')}"
    resp = requests.request(method, url, headers=_headers(kwargs.pop("prefer", None)), timeout=30, **kwargs)

    if not (200 <= resp.status_code < 300):
        detalle = resp.text
        raise RuntimeError(f"Supabase respondió HTTP {resp.status_code}: {detalle}")

    if resp.text:
        try:
            return resp.json()
        except Exception:
            return resp.text
    return None


def init_db():
    """
    Verifica conexión REAL con Supabase.
    No cae a SQLite. Si falla, la app lo muestra para corregirlo.
    """
    global _BACKEND, _FALLO_MOTIVO
    _BACKEND = None
    _FALLO_MOTIVO = ""

    try:
        # 1) Confirmar lectura.
        _request("GET", f"{SUPABASE_TABLE}?select=id&limit=1")

        # 2) Confirmar insert real.
        probe = {k: "" for k in SUPABASE_CAMPOS}
        probe["laboratorio"] = "__diagnostico_conexion__"
        inserted = _request(
            "POST",
            SUPABASE_TABLE,
            json=probe,
            prefer="return=representation",
        )

        # 3) Borrar la fila de prueba si la API devolvió id.
        if isinstance(inserted, list) and inserted and inserted[0].get("id") is not None:
            probe_id = inserted[0]["id"]
            try:
                _request("DELETE", f"{SUPABASE_TABLE}?id=eq.{probe_id}")
            except Exception:
                # No rompemos la conexión si sólo falta permiso de delete.
                pass

        _BACKEND = "supabase"
    except Exception as e:
        _FALLO_MOTIVO = str(e)
        _BACKEND = "error"


def backend_activo() -> str:
    return _BACKEND or "error"


def motivo_fallback() -> str:
    return _FALLO_MOTIVO or ""


def _check_ready():
    if _BACKEND != "supabase":
        motivo = _FALLO_MOTIVO or "Supabase no inicializado."
        raise RuntimeError(f"Supabase no está conectado: {motivo}")


def add_resultado(d: dict):
    """
    Guarda un prospecto en Supabase.
    Si falla, levanta el error para que Streamlit lo muestre en logs.
    """
    _check_ready()

    payload = {k: str(d.get(k, "") or "") for k in SUPABASE_CAMPOS}
    _request(
        "POST",
        SUPABASE_TABLE,
        json=payload,
        prefer="return=minimal",
    )


def get_all() -> list:
    _check_ready()

    rows = _request(
        "GET",
        f"{SUPABASE_TABLE}?select=*&laboratorio=neq.__diagnostico_conexion__&order=id.desc"
    )
    if not isinstance(rows, list):
        return []

    for r in rows:
        if "creado" not in r:
            r["creado"] = r.get("created_at", "")
    return rows


def found_emails() -> set:
    _check_ready()

    rows = _request("GET", f"{SUPABASE_TABLE}?select=email")
    if not isinstance(rows, list):
        return set()
    return {(r.get("email") or "").lower().strip() for r in rows if r.get("email")}


def found_labs() -> set:
    _check_ready()

    rows = _request("GET", f"{SUPABASE_TABLE}?select=laboratorio")
    if not isinstance(rows, list):
        return set()
    return {norm_lab(r.get("laboratorio")) for r in rows if r.get("laboratorio")}


def delete_all():
    _check_ready()

    # Borra todas las filas con id >= 0.
    # Requiere policy DELETE para anon/publishable.
    _request("DELETE", f"{SUPABASE_TABLE}?id=gte.0")
