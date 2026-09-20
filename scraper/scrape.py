"""
Revisa diariamente los tablones de anuncios (tauler d'edictes / seu electronica)
de varios ayuntamientos del Baix Emporda y La Selva en busca de convocatorias de
empleo publico, y guarda las que sean nuevas en Supabase.

No se filtra por palabras clave en el titulo: cada plataforma clasifica sus
propios anuncios con metadatos estructurados (categoria "Recursos Humans" en
e-Tauler, el "Procediment" en la seu de Palamos, o los propios endpoints de
"calls/bags/postProvisions" en Convoca.online), y usamos esos campos oficiales
en vez de adivinar por texto. Todo lo que entra se guarda con estado "Nueva"
para que la persona lo triage a mano en el dashboard.

Fuentes y plataforma detectada (investigado en septiembre 2026):
  - e-Tauler (Consorci AOC, https://tauler.seu-e.cat): Sant Feliu de Guixols,
    Santa Cristina d'Aro, Castell-Platja d'Aro, Calonge i Sant Antoni,
    Llagostera, Vidreres. API JSON publica sin autenticacion.
  - Convoca.online (Savia): Consell Comarcal del Baix Emporda. API JSON publica
    sin autenticacion, identifica el ayuntamiento por el header Origin/Referer.
  - espublico / eAdministracio.cat: Palamos. Tabla HTML server-rendered en la
    seu electronica, sin JS.
"""

import os
import sys
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "60"))

HEADERS_HTTP = {"User-Agent": "townhall-scraper/1.0 (+seguimiento convocatorias empleo publico)"}

# ---------------------------------------------------------------------------
# Fuente 1: e-Tauler (Consorci AOC) - https://tauler.seu-e.cat
# ---------------------------------------------------------------------------

ETAULER_API = "https://tauler.seu-e.cat/api/edictes"
ETAULER_DETAIL_URL = "https://tauler.seu-e.cat/detall?idEns={id_ens}&idEdicte={id_edicte}"

ETAULER_SOURCES = {
    "Sant Feliu de Guíxols": "1716090004",
    "Santa Cristina d'Aro": "1718120002",
    "Castell-Platja d'Aro": "1704860009",
    "Calonge i Sant Antoni": "1703400000",
    "Llagostera": "1708900000",
    "Vidreres": "1721370005",
}

HR_CATEGORY_NAMES = {"recursos humans", "contractació personal", "contractacio personal"}


def _is_personnel_notice(edicte: dict) -> bool:
    for classificacio in edicte.get("classificacions", []) or []:
        categoria = (classificacio.get("categoria") or "").strip().lower()
        if categoria in HR_CATEGORY_NAMES:
            return True
    return False


def fetch_etauler(municipio: str, id_ens: str, cutoff_date: str, max_pages: int = 60) -> list:
    items = []
    page = 1
    while page <= max_pages:
        resp = requests.get(
            ETAULER_API,
            params={"page": page, "ens": id_ens, "locale": "ca"},
            headers=HEADERS_HTTP,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        edictes = data.get("edictes", [])
        if not edictes:
            break

        reached_cutoff = False
        for edicte in edictes:
            fecha_pub = edicte.get("data_publicacio")
            if fecha_pub and fecha_pub < cutoff_date:
                reached_cutoff = True
                break
            if not _is_personnel_notice(edicte):
                continue
            items.append(
                {
                    "municipio": municipio,
                    "titulo": (edicte.get("titol") or "").strip(),
                    "url": ETAULER_DETAIL_URL.format(id_ens=id_ens, id_edicte=edicte["id_edicte"]),
                    "fecha_publicacion": fecha_pub,
                }
            )

        if reached_cutoff:
            break
        if page >= data.get("totalPages", page):
            break
        page += 1

    return items


# ---------------------------------------------------------------------------
# Fuente 2: Convoca.online (Savia) - Consell Comarcal del Baix Emporda
# ---------------------------------------------------------------------------

CONVOCA_API = "https://apigw.convoca.online/api/{endpoint}"
# type= es el parametro que usa el frontend (index.html?type=N) para cada pestaña.
CONVOCA_ENDPOINTS = {"calls": 0, "bags": 1, "postProvisions": 2}


def fetch_convoca(municipio: str, subdomain: str) -> list:
    origin = f"https://{subdomain}.convoca.online"
    items = []
    for endpoint, type_id in CONVOCA_ENDPOINTS.items():
        resp = requests.get(
            CONVOCA_API.format(endpoint=endpoint),
            headers={**HEADERS_HTTP, "Origin": origin, "Referer": origin + "/"},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[WARN] Convoca.online {municipio}/{endpoint}: HTTP {resp.status_code}")
            continue
        for process in resp.json():
            title = process.get("title") or {}
            titulo = title.get("ca-ES") or title.get("es-ES") or next(iter(title.values()), None)
            if not titulo or not process.get("id"):
                continue
            fecha = process.get("startDate") or process.get("bopDate")
            items.append(
                {
                    "municipio": municipio,
                    "titulo": titulo.strip(),
                    "url": f"{origin}/processDetail.html?id={process['id']}&type={type_id}",
                    "fecha_publicacion": fecha[:10] if fecha else None,
                }
            )
    return items


# ---------------------------------------------------------------------------
# Fuente 3: espublico / eAdministracio.cat - Palamos
# ---------------------------------------------------------------------------

PALAMOS_BOARD_URL = "https://palamos.eadministracio.cat/board"
PALAMOS_HR_PROCEDIMENT = "Seleccions de Personal i Provisions de Llocs de treball"


def fetch_palamos() -> list:
    resp = requests.get(PALAMOS_BOARD_URL, headers=HEADERS_HTTP, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table.AdvertisementBoardListPanel tbody tr"):
        procediment_cell = row.select_one("td.class_folderName span")
        if not procediment_cell:
            continue
        if procediment_cell.get_text(strip=True) != PALAMOS_HR_PROCEDIMENT:
            continue

        link = row.select_one("td.class_name a[href]")
        if not link:
            continue

        fecha = None
        date_cell = row.select_one("td.class_dateFrom span span")
        if date_cell:
            try:
                fecha = datetime.strptime(date_cell.get_text(strip=True), "%d/%m/%Y").date().isoformat()
            except ValueError:
                pass

        items.append(
            {
                "municipio": "Palamós",
                "titulo": link.get_text(strip=True),
                "url": link["href"],
                "fecha_publicacion": fecha,
            }
        )
    return items


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------


def upsert_convocatorias(rows: list) -> list:
    if not rows:
        return []
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("[ERROR] Faltan SUPABASE_URL / SUPABASE_SERVICE_KEY en el entorno.", file=sys.stderr)
        sys.exit(1)

    endpoint = f"{SUPABASE_URL}/rest/v1/convocatorias"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        # ignore-duplicates hace un INSERT ... ON CONFLICT DO NOTHING sobre la
        # unique key (municipio, url); return=representation devuelve solo las
        # filas realmente insertadas (las nuevas), no las que ya existian.
        "Prefer": "resolution=ignore-duplicates,return=representation",
    }
    resp = requests.post(
        endpoint,
        headers=headers,
        params={"on_conflict": "municipio,url"},
        json=rows,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    cutoff_date = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    all_items = []

    for municipio, id_ens in ETAULER_SOURCES.items():
        try:
            found = fetch_etauler(municipio, id_ens, cutoff_date)
            print(f"[INFO] e-Tauler {municipio}: {len(found)} anuncios de RRHH revisados")
            all_items.extend(found)
        except requests.RequestException as exc:
            print(f"[WARN] e-Tauler {municipio}: {exc}")

    try:
        found = fetch_convoca("Consell Comarcal del Baix Empordà", "baixemporda")
        print(f"[INFO] Convoca.online Baix Empordà: {len(found)} procesos revisados")
        all_items.extend(found)
    except requests.RequestException as exc:
        print(f"[WARN] Convoca.online Baix Empordà: {exc}")

    try:
        found = fetch_palamos()
        print(f"[INFO] Palamós: {len(found)} anuncios de RRHH revisados")
        all_items.extend(found)
    except requests.RequestException as exc:
        print(f"[WARN] Palamós: {exc}")

    # Deduplicar defensivamente por (municipio, url) antes de mandar a Supabase.
    dedup = {}
    for item in all_items:
        if not item.get("titulo") or not item.get("url"):
            continue
        dedup[(item["municipio"], item["url"])] = item
    rows = list(dedup.values())

    inserted = upsert_convocatorias(rows)

    print(f"\nTotal candidatos revisados: {len(rows)}")
    print(f"Convocatorias nuevas insertadas: {len(inserted)}")
    for row in inserted:
        print(f"  + [{row['municipio']}] {row['titulo']}")


if __name__ == "__main__":
    main()
