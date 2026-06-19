# abraChem · Sourcing Intelligence (Streamlit)

App web para encontrar contactos de compras de laboratorios farmacéuticos,
nutracéuticos y veterinarios en cualquier país. Los resultados se guardan
**para siempre** (ver sección de base de datos).

## Probar en tu compu (local)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```
Se abre en http://localhost:8501. Las claves ya están en
`.streamlit/secrets.toml` para uso local (sin Postgres configurado, usa
SQLite local — funciona igual, solo que esa base vive en tu compu).

## Publicar como página web (gratis) — Streamlit Community Cloud

1. **Subí el proyecto a GitHub** (repo nuevo). El archivo
   `.streamlit/secrets.toml` NO se sube (está en `.gitignore`): tus claves
   quedan privadas.
2. **Importante:** si tu repo tiene esta carpeta DENTRO de otra (por ejemplo
   `abrachemsourcing/abrachem_streamlit/`), en el deploy tenés que indicar
   esa ruta completa en *Main file path* (paso 4). Si preferís simplificar,
   subí el CONTENIDO de esta carpeta directo a la raíz del repo.
3. Entrá a **https://share.streamlit.io** e iniciá sesión con GitHub.
4. **New app** → elegí tu repositorio → *Main file path*:
   `streamlit_app.py` (o `abrachem_streamlit/streamlit_app.py` si lo dejaste
   en subcarpeta).
5. En **Advanced settings → Secrets**, pegá tus claves (ver abajo el bloque
   completo recomendado, con Postgres incluido).
6. **Deploy**. En un par de minutos tenés una URL pública.

## Base de datos PERMANENTE (recomendado) — Supabase, gratis

Por defecto, sin configurar nada, la app guarda en SQLite **dentro del
servidor de Streamlit**. Eso funciona perfecto en tu compu, pero en
Streamlit Cloud el disco se reinicia cuando la app se redeploya o duerme
por inactividad — y ahí se perdería el historial.

Para que **todo lo que se va encontrando quede guardado para siempre**,
conectá una base Postgres gratuita de Supabase (5 minutos):

1. Entrá a **https://supabase.com** → creá una cuenta gratis → **New project**.
2. Cuando esté listo, andá a **Project Settings → Database**.
3. Copiá la **Connection string** modo *URI* (algo como
   `postgresql://postgres:[TU-PASSWORD]@db.xxxx.supabase.co:5432/postgres`).
   Reemplazá `[TU-PASSWORD]` por la contraseña que pusiste al crear el proyecto.
4. En Streamlit Cloud, andá a tu app → **Manage app → Settings → Secrets** y
   pegá, junto con las claves de Hunter/RocketReach:
   ```toml
   HUNTER_API_KEY = "tu_clave_hunter"
   ROCKETREACH_API_KEY = "tu_clave_rocketreach"
   SUPABASE_DB_URL = "postgresql://postgres:TU-PASSWORD@db.xxxx.supabase.co:5432/postgres"
   ```
5. Guardá y reiniciá la app (Streamlit lo hace solo). La app detecta
   `SUPABASE_DB_URL` automáticamente y a partir de ahí **todos los
   resultados se guardan en Postgres, para siempre**, sin importar cuántas
   veces se reinicie o redeployes.

En el panel izquierdo de la app vas a ver un indicador: **"Base de datos:
Postgres (persistencia permanente)"** cuando está bien conectada, o
**"Base de datos: SQLite local"** si todavía no configuraste Supabase.

## Notas importantes

- **Las claves nunca se ven en la página.** Se cargan desde *Secrets* (nube)
  o `.streamlit/secrets.toml` (local).
- Si RocketReach devuelve 429 (límite por hora), la app sigue con Hunter sola.
- Si ves `ModuleNotFoundError` al desplegar, casi siempre es porque el *Main
  file path* configurado en Streamlit Cloud no apunta a la carpeta correcta,
  o porque falta algo en `requirements.txt`. Los imports de este proyecto ya
  son robustos a la ubicación (se autoarreglan el `sys.path`), así que lo
  primero a revisar es el *Main file path* del paso 4 de arriba.

## Estructura
```
streamlit_app.py   interfaz (sidebar, progreso en vivo, resultados + buscador)
engine.py          motor de búsqueda (pasos 1–5) con eventos en vivo
store.py           guardado persistente (Postgres si está configurado, si no SQLite)
config.py          parámetros (claves por entorno/secrets)
paso1/2_3/4_5...   lógica del pipeline (laboratorios, APIs, dominio, contacto)
```
