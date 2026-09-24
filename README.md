# Townhall — convocatorias de empleo público

Vigila a diario los tablones de anuncios / seu electrònica de 8 ayuntamientos del Baix Empordà y La Selva en busca de convocatorias de empleo público, y las guarda en Supabase para poder triarlas (Nueva / Me interesa / Descartada / Aplicada) desde un dashboard estático.

## Arquitectura

```
scraper/    Script Python que revisa cada web y guarda lo nuevo en Supabase
docs/       Dashboard estático (HTML/JS), pensado para GitHub Pages
supabase/   schema.sql para crear la tabla y las políticas de RLS
.github/    Workflow que ejecuta el scraper cada día
```

### Fuentes y cómo se leen

No se filtra por texto/palabras clave en ningún sitio: cada plataforma clasifica sus anuncios con metadatos propios, y el scraper usa esos campos estructurados en vez de adivinar por título.

**Fuente principal — dataset CKAN de la AOC.** Una sola API cubre los 8 entes: el [dataset "Convocatòries de personal"](https://dadesobertes.seu-e.cat) (recurso `0e11c4f5-ce15-401f-b86f-f9d2604b94f6`), que es justo el que alimenta las páginas "Convocatòries de personal" de `seu-e.cat` y enlaza a la ficha de CIDO (Diputació de Barcelona). Se filtra por `CODI_ENS`, da **una fila por convocatoria** (no por trámite) y no depende de qué plataforma de tablón use cada ayuntamiento. Los organismos dependientes comparten el `CODI_ENS` de su ayuntamiento, así que entran solos (Residència Josep Baulida, Escola de Música de Sant Feliu…); el Centre Ocupacional Tramuntana va con `CODI_ENS` vacío y se pide aparte por `NOM_ENS`.

**Fuentes complementarias**, por si CIDO tarda en indexar algo:

| Municipio | Plataforma | Filtro estructurado usado |
|---|---|---|
| Sant Feliu de Guíxols | e-Tauler (Consorci AOC) | categoría `Recursos Humans` / `Contractació personal` |
| Castell-Platja d'Aro | e-Tauler (Consorci AOC) | idem |
| Calonge i Sant Antoni | e-Tauler (Consorci AOC) | idem |
| Llagostera | e-Tauler (Consorci AOC) | idem |
| Vidreres | e-Tauler (Consorci AOC) | idem |
| Consell Comarcal del Baix Empordà | Convoca.online (Savia) | endpoints dedicados `calls` / `bags` / `postProvisions` |
| Palamós | espublico / eAdministracio.cat | columna "Procediment" de RRHH |
| Santa Cristina d'Aro | espublico / eAdministracio.cat | idem |

La URL que diste de Sant Feliu de Guíxols (`ciutadania.guixols.cat/tauler-edictes`) y la del Baix Empordà (`baixemporda.convoca.online`) son webs "envoltorio": la primera embebe un iframe del e-Tauler oficial, la segunda es un SPA que llama a una API JSON. El scraper llama directamente a esas APIs/fuente real, que son públicas y no requieren autenticación.

### Por qué la fuente principal ya no es e-Tauler

Santa Cristina d'Aro **dejó de publicar en e-Tauler el 25/06/2025** y se pasó a espublico (`santacristina.eadministracio.cat`). El scraper siguió preguntando a e-Tauler, que respondía `0 anuncios` correctamente, y eso era indistinguible de "hoy no hay convocatorias": estuvo 15 meses con un punto ciego sin que fallara nada. En ese tiempo el ayuntamiento publicó al menos plazas de Policia Local, Interventor, Tècnic en comunicació, Dinamitzador Juvenil y una borsa de TEI.

De ahí las dos medidas: el dataset CKAN como fuente principal (no se rompe si un ayuntamiento cambia de plataforma) y el panel **"Cobertura por ente"** del dashboard, que marca en rojo cualquier ente que lleve más de 60 días sin una convocatoria nueva. Ese umbral no significa necesariamente avería —en municipios pequeños 60 días sin nada es normal— pero es la única señal que convierte un punto ciego en algo visible.

## 1. Crear el proyecto en Supabase

1. Ve a [supabase.com](https://supabase.com) y crea un proyecto nuevo (plan gratuito de sobra).
2. Abre **SQL Editor** y pega el contenido de [`supabase/schema.sql`](supabase/schema.sql). Ejecútalo. Esto crea la tabla `convocatorias` con la restricción `unique (municipio, url)` (evita duplicados en días sucesivos) y las políticas de RLS.
3. Ve a **Project Settings → API** y copia:
   - **Project URL** (`SUPABASE_URL`)
   - **anon / public key** (`SUPABASE_ANON_KEY`) — para el dashboard
   - **service_role key** (`SUPABASE_SERVICE_KEY`) — para el scraper. **No la publiques nunca**, solo va en GitHub Secrets.

## 2. Configurar el dashboard

Esto se hace **en tu ordenador, dentro de esta misma carpeta del proyecto** (`/Users/anna/townhall`), antes de subir nada a GitHub — es solo crear un archivo de configuración local que luego viajará con el resto del código.

```bash
cd /Users/anna/townhall
cp docs/config.example.js docs/config.js
```

Abre el archivo `docs/config.js` que se acaba de crear (está en la carpeta `docs/`, junto a `index.html`) y sustituye los valores de ejemplo por tu `SUPABASE_URL` y tu `SUPABASE_ANON_KEY` del paso 1.

Este archivo **sí se sube al repo** (no está en `.gitignore` a propósito) y queda público en GitHub Pages — la anon key está pensada para exponerse en el navegador; la seguridad real la dan las políticas RLS de `schema.sql` (solo permiten `select` y `update`, no `insert`/`delete`). Sin este archivo committeado, el dashboard publicado mostrará el aviso "Falta configurar docs/config.js".

## 3. Crear el repo en GitHub y subir el código

Este directorio ya tiene todos los archivos (incluido el `docs/config.js` que acabas de crear), pero **no es un repo git todavía**. Desde `/Users/anna/townhall`:

```bash
git init
git add .
git commit -m "Set up townhall job-listing tracker"
```

Crea un repo vacío en GitHub (github.com/new, sin README/licencia) y luego:

```bash
git remote add origin git@github.com:<tu-usuario>/<tu-repo>.git
git branch -M main
git push -u origin main
```

## 4. Añadir los secrets del scraper en GitHub

En el repo de GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Añade:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY` (la service_role, no la anon)

El workflow [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) los usa para ejecutar `scraper/scrape.py` cada día a las 06:00 UTC, y también se puede lanzar a mano desde la pestaña **Actions → Scrape convocatorias de empleo público → Run workflow**.

## 5. Publicar el dashboard en GitHub Pages

**Settings → Pages** → en "Build and deployment", elige:
- Source: `Deploy from a branch`
- Branch: `main`, carpeta `/docs`

Guarda. En un par de minutos el dashboard estará en `https://<tu-usuario>.github.io/<tu-repo>/`.

## Probar en local

```bash
cd scraper
pip install -r requirements.txt
cp .env.example .env   # rellena SUPABASE_URL y SUPABASE_SERVICE_KEY
python scrape.py
```

Imprime cuántos anuncios de RRHH revisó por municipio y cuántos eran nuevos.

## Restringir el acceso con login

El dashboard ahora exige iniciar sesión (Supabase Auth) antes de mostrar ninguna fila, y las políticas de `supabase/schema.sql` ya no aceptan al rol `anon`: solo a `authenticated`. Para activarlo en tu proyecto:

1. **Vuelve a ejecutar `supabase/schema.sql`** en el SQL Editor de tu proyecto (sustituye las políticas antiguas por las nuevas basadas en `auth.role() = 'authenticated'`).
2. **Desactiva el registro público**: en el panel de Supabase ve a **Authentication → Sign In / Providers → Email** y desactiva "Allow new users to sign up" (o "Enable email signups", según la versión del panel). Así nadie puede crearse una cuenta por su cuenta.
3. **Crea a mano las cuentas de las personas que quieres que entren**: **Authentication → Users → Add user**, indicando email y contraseña (o "Invite" para que la persona la ponga ella misma). Repite por cada persona autorizada.
4. Publica los cambios de `docs/` (commit + push a `main`); GitHub Pages los recogerá automáticamente.

Con esto, aunque la URL del dashboard y la clave `anon` sigan siendo públicas (es inevitable en una app 100% estática sin backend), nadie puede leer ni modificar datos sin iniciar sesión con una cuenta que tú hayas creado explícitamente.

**Limitación a tener en cuenta**: GitHub Pages sirve el HTML/CSS/JS a cualquiera que visite la URL — lo que queda protegido es el *acceso a los datos* (Supabase), no la carga de la página de login en sí, que cualquiera puede ver. Esto es aceptable para un panel personal; si en el futuro necesitas que ni siquiera se pueda ver el formulario de login, la alternativa sería mover el hosting a un servicio con autenticación a nivel de servidor (p. ej. Cloudflare Access delante de GitHub Pages, o Netlify/Vercel con protección de contraseña), lo cual añade infraestructura adicional.

## Notas y limitaciones conocidas

- **Filtro por fecha de publicación**: el dashboard (`docs/app.js`, constante `FECHA_MINIMA_PUBLICACION`) solo muestra convocatorias con `fecha_publicacion >= 2026-09-01`. Las que no tengan `fecha_publicacion` (campo nulo) quedan fuera de ese filtro. Para cambiar la fecha de corte, edita esa constante.
- **`LOOKBACK_DAYS`** (por defecto 60): en cada ejecución el scraper solo pagina hacia atrás hasta esa antigüedad en los taulers e-Tauler. Es suficiente para el uso diario normal; si quieres hacer un backfill inicial más profundo la primera vez, ejecuta manualmente con `LOOKBACK_DAYS=365` (o más) antes de dejar el cron con el valor por defecto.
- **Santa Cristina d'Aro**: a fecha de esta investigación, su e-Tauler no tenía anuncios de RRHH publicados desde mediados de 2025 — no es un fallo del scraper, es el estado real de esa fuente. Si detectas que llevan tiempo sin novedades, vale la pena revisar a mano si han cambiado de plataforma.
- **RLS abierta para `update`**: cualquiera con la URL del dashboard (y por tanto la anon key) puede cambiar el `estado` de cualquier fila, porque es una app personal sin login. No puede insertar ni borrar filas. Si más adelante quieres cerrarlo del todo, añade Supabase Auth y cambia las políticas de `schema.sql`.
- El scraper es **idempotente**: se puede ejecutar tantas veces como quieras, solo inserta lo que no exista ya (por `municipio` + `url`).
