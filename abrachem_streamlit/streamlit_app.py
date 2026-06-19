"""
abraChem · Sourcing Intelligence — App Streamlit
Corré local:   streamlit run streamlit_app.py
"""
import os
import sys
from pathlib import Path
import streamlit as st
from supabase import create_client

# ── Asegurar que esta carpeta esté en sys.path ───────────────
# En Streamlit Cloud, si el repo tiene la app en una subcarpeta,
# a veces el cwd no coincide con la carpeta del script. Esto lo
# hace robusto sin importar desde dónde se ejecute.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

st.set_page_config(page_title="abraChem · Sourcing Intelligence",
                   page_icon="⚗️", layout="wide")

# ── Claves: secrets de Streamlit → variables de entorno (antes de importar
#    los módulos del pipeline, que leen config.py / entorno). Nunca se ven. ──
def _seed_keys():
    for k in ("HUNTER_API_KEY", "ROCKETREACH_API_KEY"):
        try:
            if k in st.secrets and st.secrets[k]:
                os.environ.setdefault(k, str(st.secrets[k]))
        except Exception:
            pass
_seed_keys()

# ── Cliente Supabase (API) ─────────────────────────────────────
# Las credenciales se cargan desde Streamlit Cloud → Settings → Secrets:
# SUPABASE_URL y SUPABASE_KEY. No se guardan en GitHub.
@st.cache_resource
def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        return None

    if not url or not key:
        return None

    return create_client(str(url), str(key))

supabase = get_supabase()

# ── Importar el motor con mensaje de error claro si algo falta ──
try:
    import store
    from engine import ejecutar_busqueda
except Exception as e:
    st.error(
        "No se pudo cargar el motor de búsqueda. Esto suele pasar si falta "
        "instalar una dependencia o un archivo no se subió al repo."
    )
    st.exception(e)
    st.stop()

try:
    import config
    _CFG_H = getattr(config, "HUNTER_API_KEY", "")
    _CFG_R = getattr(config, "ROCKETREACH_API_KEY", "")
except Exception:
    _CFG_H = _CFG_R = ""

store.init_db()

# ── Estilos ────────────────────────────────────────────────────
st.markdown("""
<style>
:root{--brand:#0e6e5d;--ink:#15202b;}
.block-container{padding-top:1.6rem;max-width:1200px}
h1,h2,h3{letter-spacing:-.3px}
.ac-brand{display:flex;align-items:center;gap:11px;margin-bottom:4px}
.ac-mark{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#13836f,#0a5446);
  display:flex;align-items:center;justify-content:center;font-size:18px}
.ac-brand b{font-size:18px;color:#15202b}
.ac-brand span{font-size:12px;color:#7e8f9d;display:block;margin-top:-2px}
.ptag{display:inline-block;background:#e4f1ee;color:#0a5446;border:1px solid #bfded6;
  border-radius:6px;padding:2px 9px;font-size:13px;font-weight:600;margin:2px 4px 2px 0}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px}
.c-Alta{background:#e3f4ec;color:#1f9d6b}.c-Media{background:#e5eef8;color:#2c6cb0}
.c-Media-Baja{background:#f7eed9;color:#bd7d12}.c-Baja{background:#eef2f6;color:#8593a0}
.relchip{background:#e4f1ee;color:#0a5446;border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600}
.apichip{display:inline-block;background:#e4f1ee;color:#0a5446;border:1px solid #cfe6e0;
  border-radius:6px;padding:3px 10px;font-size:12.5px;margin:2px 4px 2px 0}
.smallmuted{color:#8593a0;font-size:12.5px}
</style>
""", unsafe_allow_html=True)

# ── Estado ─────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault("paises", ["Argentina"])
ss.setdefault("running", False)

def _add_pais():
    val = (ss.get("pais_nuevo") or "").strip()
    if val and val.lower() not in [p.lower() for p in ss.paises]:
        ss.paises.append(val)
    ss.pais_nuevo = ""

def _resolver_claves():
    h = os.environ.get("HUNTER_API_KEY") or (_CFG_H if "PEGA" not in _CFG_H else "")
    r = os.environ.get("ROCKETREACH_API_KEY") or (_CFG_R if "PEGA" not in _CFG_R else "")
    return h, r

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    logo_path = _HERE / "logo_abrachem.png"
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
        st.caption("Sourcing Intelligence")
    else:
        st.markdown('<div class="ac-brand"><div class="ac-mark">⚗️</div>'
                    '<div><b>abraChem</b><span>Sourcing Intelligence</span></div></div>',
                    unsafe_allow_html=True)
    st.divider()

    st.markdown("**Mercados objetivo**")
    st.text_input("Escribí un país y Enter", key="pais_nuevo",
                  on_change=_add_pais, label_visibility="collapsed",
                  placeholder="Ej: Argentina, Japón, España…")
    if ss.paises:
        cols = st.columns(2)
        for idx, p in enumerate(list(ss.paises)):
            with cols[idx % 2]:
                if st.button(f"✕  {p}", key=f"rm_{p}", use_container_width=True):
                    ss.paises.remove(p)
                    st.rerun()
    st.caption("Cualquier país del mundo. Si no está en la base, se investiga en la web.")
    st.divider()

    st.markdown("**Parámetros**")
    objetivo = st.number_input("Prospectos objetivo", 1, 500, 10)
    min_prod = st.number_input("Mín. productos (solo base curada)", 0, 50, 2)
    st.divider()

    h_ok, r_ok = _resolver_claves()
    if h_ok and r_ok:
        st.success("Claves API cargadas ✓", icon="🔑")
    else:
        st.error("Faltan claves API. Cargalas en *Secrets* (nube) "
                 "o en config.py / variables de entorno.", icon="⚠️")


    if supabase is not None:
        st.success("Supabase API conectada ✓", icon="🟢")
    else:
        st.warning("Supabase API no configurada. Revisá SUPABASE_URL y SUPABASE_KEY en Secrets.", icon="🟡")

    iniciar = st.button("▶  Iniciar búsqueda", type="primary",
                        use_container_width=True,
                        disabled=ss.running or not ss.paises or not (h_ok and r_ok))

# ── Encabezado ─────────────────────────────────────────────────
st.title("Panel de prospección")
tab_run, tab_res = st.tabs(["Búsqueda y progreso", "Resultados"])

# ── Ejecutar búsqueda (en vivo) ────────────────────────────────
with tab_run:
    if iniciar:
        ss.running = True
        h, r = _resolver_claves()
        prog_bar = st.progress(0.0)
        status   = st.empty()
        log_box  = st.empty()
        logs = []

        def on_log(tipo, msg):
            ic = {"success":"✅","warning":"⚠️","error":"❌","info":"•"}.get(tipo,"•")
            logs.append(f"{ic} {msg}")
            log_box.code("\n".join(logs[-180:]), language=None)

        def on_progress(c, obj, lab):
            frac = min(c/obj, 1.0) if obj else 0.0
            prog_bar.progress(frac)
            status.markdown(f"**{c}/{obj}** prospectos · procesando *{lab}*")

        try:
            n = ejecutar_busqueda(ss.paises, int(objetivo), int(min_prod), h, r,
                                  on_log=on_log, on_progress=on_progress)
            status.success(f"Búsqueda completada · {n}/{int(objetivo)} prospectos. "
                           f"Mirá la pestaña **Resultados**.")
        except Exception as e:
            status.error(f"Error en la búsqueda: {e}")
        finally:
            ss.running = False
    else:
        st.info("Configurá los mercados y parámetros en el panel izquierdo y "
                "tocá **Iniciar búsqueda**. El progreso aparece acá en vivo.")

# ── Resultados (all-time, persistentes + buscador) ─────────────
with tab_res:
    filas = store.get_all()
    c1, c2 = st.columns([3, 1])
    with c1:
        q = st.text_input("Buscar", placeholder="Buscar por empresa, cargo, nombre o email…",
                          label_visibility="collapsed")
    with c2:
        st.markdown(f"<div class='smallmuted' style='padding-top:8px'>"
                    f"{len(filas)} prospectos guardados</div>", unsafe_allow_html=True)

    def _norm(s):
        import unicodedata
        return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "").lower())
                       if not unicodedata.combining(ch))
    if q:
        qn = _norm(q)
        filas = [f for f in filas if all(
            tok in _norm(" ".join([f.get("laboratorio",""), f.get("cargo",""),
                                   f.get("nombre",""), f.get("apellido",""),
                                   f.get("email",""), f.get("pais",""),
                                   f.get("relevancia","")]))
            for tok in qn.split())]

    if not filas:
        st.info("Todavía no hay prospectos. Lanzá una búsqueda y van quedando "
                "guardados acá para siempre.")
    else:
        for f in filas:
            conf = f.get("confianza", "Baja") or "Baja"
            nombre = (f"{f.get('nombre','')} {f.get('apellido','')}").strip() or "—"
            cargo = f.get("cargo", "") or "—"
            laboratorio = f.get("laboratorio", "") or "—"
            relevancia = f.get("relevancia", "") or "—"
            pais = f.get("pais", "") or "—"
            dominio = f.get("dominio", "") or "—"
            email = f.get("email", "") or "—"
            busqueda = f.get("mensaje", "") or "—"

            head = (
                f"Empresa: {laboratorio}  |  "
                f"Nombre: {nombre}  |  "
                f"Cargo: {cargo}  |  "
                f"Confianza: {conf}"
            )

            with st.expander(head):
                c1, c2, c3 = st.columns([1.4, 1.6, 1])
                c1.markdown(f"**Nombre**\n\n{nombre}")
                c2.markdown(f"**Cargo**\n\n{cargo}")
                c3.markdown(
                    f"**Nivel de confianza**\n\n"
                    f"<span class='pill c-{conf.replace(' ','-')}'>{conf}</span>",
                    unsafe_allow_html=True,
                )

                e1, e2, e3 = st.columns([1.6, 1, 1])
                e1.markdown(f"**Empresa / laboratorio**\n\n{laboratorio}")
                e2.markdown(f"**País**\n\n{pais}")
                e3.markdown(f"**Relevancia**\n\n<span class='relchip'>{relevancia}</span>", unsafe_allow_html=True)

                st.markdown(f"**Dominio**  \n{dominio}")
                st.markdown("**Email**")
                st.code(email, language=None)

                apis = [a.strip() for a in (f.get("top_apis") or f.get("apis_clave") or "").split("|") if a.strip()]
                if apis:
                    st.markdown("**Insumos / APIs que probablemente compra**")
                    st.markdown("".join(f"<span class='apichip'>{a}</span>" for a in apis),
                                unsafe_allow_html=True)

                st.markdown("**Búsqueda / mensaje sugerido**")
                st.code(busqueda, language=None)

        st.divider()
        if st.button("🗑  Borrar todos los resultados", type="secondary"):
            store.delete_all()
            st.rerun()
