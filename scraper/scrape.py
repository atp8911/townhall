"""
Revisa diariamente los tablones de anuncios (tauler d'edictes / seu electronica)
de varios ayuntamientos del Baix Emporda y La Selva en busca de convocatorias de
empleo publico, y guarda las que sean nuevas en Supabase.

No se filtra por palabras clave en el titulo: cada plataforma clasifica sus
propios anuncios con metadatos estructurados (el dataset CKAN de la AOC ya es
en si mismo el catalogo oficial de convocatorias, la categoria "Recursos
Humans" en e-Tauler, el "Procediment" en las seus de espublico, o los propios
endpoints de "calls/bags/postProvisions" en Convoca.online), y usamos esos
campos oficiales en vez de adivinar por texto. Todo lo que entra se guarda con
estado "Nueva" para que la persona lo triage a mano en el dashboard.

Fuente principal (investigado en septiembre 2026):
  - Dataset CKAN "Convocatories de personal" de la AOC
    (https://dadesobertes.seu-e.cat), que es el que alimenta las paginas
    "Convocatories de personal" de seu-e.cat y enlaza a la ficha de CIDO
    (Diputacio de Barcelona). Cubre los 8 entes de golpe filtrando por
    CODI_ENS, da una fila por convocatoria (no por tramite) y no depende de
    que el ayuntamiento siga usando una plataforma de tablon concreta.

Fuentes complementarias, por si CIDO tarda en indexar algo:
  - e-Tauler (Consorci AOC, https://tauler.seu-e.cat): Sant Feliu de Guixols,
    Castell-Platja d'Aro, Calonge i Sant Antoni, Llagostera, Vidreres. API
    JSON publica sin autenticacion. OJO: Santa Cristina d'Aro dejo de publicar
    aqui el 25/06/2025 al migrar a espublico, y el scraper se paso 15 meses
    devolviendo cero sin que saltara ninguna alarma; de ahi que la fuente
    principal ya no sea esta.
  - Convoca.online (Savia): Consell Comarcal del Baix Emporda. API JSON publica
    sin autenticacion, identifica el ayuntamiento por el header Origin/Referer.
  - espublico / eAdministracio.cat: Palamos y Santa Cristina d'Aro. Tabla HTML
    server-rendered en la seu electronica, sin JS. Solo lista lo que sigue
    vigente en el tablon, no el historico.
"""

import json
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
# Fuente principal: dataset CKAN de convocatorias de la AOC
# ---------------------------------------------------------------------------

CKAN_API = "https://dadesobertes.seu-e.cat/api/3/action/datastore_search"
CKAN_RESOURCE_ID = "0e11c4f5-ce15-401f-b86f-f9d2604b94f6"
CKAN_PAGE_SIZE = 500

# El CODI_ENS lo comparten el ayuntamiento y sus organismos dependientes (la
# Residencia Josep Baulida publica bajo el codi de Llagostera, la Escola de
# Musica bajo el de Sant Feliu), asi que filtrar por codigo ya los arrastra.
CKAN_ENS = {
    "1716090004": "Sant Feliu de Guíxols",
    "1718120002": "Santa Cristina d'Aro",
    "1704860009": "Castell-Platja d'Aro",
    "1703400000": "Calonge i Sant Antoni",
    "1708900000": "Llagostera",
    "1721370005": "Vidreres",
    "1711810007": "Palamós",
    "8101080001": "Consell Comarcal del Baix Empordà",
}

# Excepcion: unos pocos organismos dependientes van con CODI_ENS vacio y solo
# se pueden pedir por nombre exacto.
CKAN_ENS_SIN_CODI = {
    "Consell Comarcal del Baix Empordà - Centre Ocupacional i Especial de Treball Tramuntana": (
        "Consell Comarcal del Baix Empordà"
    ),
}


def _ckan_records(filters: dict, offset: int) -> list:
    resp = requests.get(
        CKAN_API,
        params={
            "resource_id": CKAN_RESOURCE_ID,
            "filters": json.dumps(filters, ensure_ascii=False),
            "sort": "DATA_DARRER_ANUNCI desc",
            "limit": CKAN_PAGE_SIZE,
            "offset": offset,
        },
        headers=HEADERS_HTTP,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN respondio success=false: {payload}")
    return payload["result"]["records"]


def _ckan_item(record: dict, municipio: str):
    titulo = (record.get("RESUM") or "").strip()
    url = (record.get("ENLLAÇ") or "").strip()
    if not titulo or not url:
        return None

    # "Ajuntament de Llagostera - Residencia Josep Baulida" -> anotar de quien
    # es la plaza, porque el municipio que guardamos es el del ayuntamiento.
    nom_ens = (record.get("NOM_ENS") or "").strip()
    if " - " in nom_ens:
        titulo = f"{titulo} ({nom_ens.split(' - ', 1)[1]})"

    fecha = record.get("DATA_PUB") or record.get("DATA_DARRER_ANUNCI")
    return {
        "municipio": municipio,
        "titulo": titulo,
        "url": url,
        "fecha_publicacion": fecha[:10] if fecha else None,
    }


def fetch_ckan(filters: dict, resolve_municipio, cutoff_date: str) -> list:
    """Pagina el dataset ordenado por DATA_DARRER_ANUNCI desc hasta el cutoff."""
    items = []
    offset = 0
    while True:
        records = _ckan_records(filters, offset)
        if not records:
            return items
        for record in records:
            ultimo_anuncio = (record.get("DATA_DARRER_ANUNCI") or "")[:10]
            # Los registros sin fecha salen primero al ordenar desc: no cortan
            # la paginacion, simplemente se dejan pasar.
            if ultimo_anuncio and ultimo_anuncio < cutoff_date:
                return items
            item = _ckan_item(record, resolve_municipio(record))
            if item:
                items.append(item)
        offset += CKAN_PAGE_SIZE


# ---------------------------------------------------------------------------
# Fuente complementaria 1: e-Tauler (Consorci AOC) - https://tauler.seu-e.cat
# ---------------------------------------------------------------------------

ETAULER_API = "https://tauler.seu-e.cat/api/edictes"
ETAULER_DETAIL_URL = "https://tauler.seu-e.cat/detall?idEns={id_ens}&idEdicte={id_edicte}"

# Santa Cristina d'Aro ya no esta aqui: su e-Tauler lleva parado desde el
# 25/06/2025 y ahora publica en santacristina.eadministracio.cat (ver abajo).
ETAULER_SOURCES = {
    "Sant Feliu de Guíxols": "1716090004",
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
# Fuente complementaria 2: Convoca.online (Savia) - Consell Comarcal
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
# Fuente complementaria 3: espublico / eAdministracio.cat
# ---------------------------------------------------------------------------

EADMIN_SOURCES = {
    "Palamós": "https://palamos.eadministracio.cat/board",
    "Santa Cristina d'Aro": "https://santacristina.eadministracio.cat/board",
}

# Cada ayuntamiento nombra a su manera la carpeta de RRHH ("Procediment"), asi
# que comparamos contra el conjunto de nombres vistos en las seus que leemos.
EADMIN_HR_PROCEDIMENTS = {
    "seleccions de personal i provisions de llocs de treball",
    "planificació i ordenació de personal",
    "planificacio i ordenacio de personal",
}


def fetch_eadministracio(municipio: str, board_url: str) -> list:
    resp = requests.get(board_url, headers=HEADERS_HTTP, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table.AdvertisementBoardListPanel tbody tr"):
        procediment_cell = row.select_one("td.class_folderName span")
        if not procediment_cell:
            continue
        if procediment_cell.get_text(strip=True).lower() not in EADMIN_HR_PROCEDIMENTS:
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
                "municipio": municipio,
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

    try:
        found = fetch_ckan(
            {"CODI_ENS": list(CKAN_ENS)},
            lambda rec: CKAN_ENS[str(rec["CODI_ENS"])],
            cutoff_date,
        )
        found += fetch_ckan(
            {"NOM_ENS": list(CKAN_ENS_SIN_CODI)},
            lambda rec: CKAN_ENS_SIN_CODI[rec["NOM_ENS"]],
            cutoff_date,
        )
        print(f"[INFO] CKAN/AOC: {len(found)} convocatorias revisadas en los 8 entes")
        all_items.extend(found)
    except (requests.RequestException, RuntimeError, KeyError) as exc:
        print(f"[WARN] CKAN/AOC: {exc}")

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

    for municipio, board_url in EADMIN_SOURCES.items():
        try:
            found = fetch_eadministracio(municipio, board_url)
            print(f"[INFO] eAdministracio {municipio}: {len(found)} anuncios de RRHH revisados")
            all_items.extend(found)
        except requests.RequestException as exc:
            print(f"[WARN] eAdministracio {municipio}: {exc}")

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
