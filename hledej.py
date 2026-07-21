#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Realitní asistent — hledá domy a pozemky ve více realitních serverech
v okolí vybraných obcí a vygeneruje živý HTML dashboard.

Zdroje (realitní servery):
  - Sreality.cz     (veřejné JSON API)         -> nejspolehlivější
  - Bezrealitky.cz  (veřejné GraphQL API)      -> spolehlivé
  - Reality.iDNES.cz(scraping HTML)            -> "best effort"
  - Bazoš.cz        (scraping HTML)            -> "best effort"

Co skript dělá:
  1) Stáhne inzeráty (domy + pozemky) ze všech zapnutých zdrojů.
  2) Vyfiltruje podle ceny a podle lokality (GPS radius nebo shoda názvu obce).
  3) Porovná s minulým během (seen.json) a označí NOVÉ nabídky.
  4) Vygeneruje dashboard.html — přehled, který si otevřeš v prohlížeči.

Spuštění:
    python3 hledej.py            # ostrý běh (stahuje z internetu)
    python3 hledej.py --demo     # ukázkový běh s testovacími daty (bez internetu)

Závislosti:  pip3 install requests beautifulsoup4
"""

import argparse
import datetime
import html
import json
import math
import os
import re
import time
import unicodedata

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from dashboard_template import HTML_SABLONA

# =========================================================================
#  NASTAVENÍ — vše důležité je tady
# =========================================================================

# Které zdroje zapnout. Když některý zlobí, dej False.
ZDROJE_ZAPNUTE = {
    "sreality": True,
    "bezrealitky": True,
    "idnes": True,
    "bazos": True,
}

# Obce, kolem kterých hledáme (název + GPS střed obce). GPS slouží k filtru radiusem.
OBCE = [
    {"nazev": "Ostravice",          "lat": 49.5340, "lon": 18.3870},
    {"nazev": "Raškovice",          "lat": 49.6150, "lon": 18.4360},
    {"nazev": "Horní Domaslavice",  "lat": 49.6970, "lon": 18.4640},
    {"nazev": "Dolní Domaslavice",  "lat": 49.7150, "lon": 18.4520},
]

# Radius v km kolem každé obce (pro zdroje, které mají GPS souřadnice).
RADIUS_KM = 5.0

# Názvy obcí v okruhu ~5 km — použije se u zdrojů BEZ GPS (Bazoš, iDNES),
# kde filtrujeme podle textu lokality. Klidně si seznam uprav/rozšiř.
OBCE_TEXTOVE = [
    # cílové obce
    "Ostravice", "Raškovice", "Horní Domaslavice", "Dolní Domaslavice",
    # okolí do ~5 km
    "Pražmo", "Krásná", "Morávka", "Janovice", "Metylovice", "Pstruží",
    "Malenovice", "Frýdlant nad Ostravicí", "Baška", "Kunčičky u Bašky",
    "Vyšní Lhoty", "Nižní Lhoty", "Dobrá", "Dobratice", "Nošovice",
    "Vojkovice", "Horní Tošanovice", "Dolní Tošanovice", "Třanovice",
    "Lučina", "Soběšovice", "Žermanice", "Pazderna", "Pržno", "Čeladná",
]

# Vyloučené lokality — inzeráty z těchto měst/obcí se zahodí (na všech zdrojích).
# Porovnává se na celá slova, takže "Ostrava" nevyřadí "Ostravice".
LOKALITA_VYLOUCIT = [
    "Karviná", "Havířov", "Orlová", "Bohumín", "Ostrava",
    "Český Těšín", "Třinec",
]

# Cenové stropy (Kč).
MAX_CENA_DUM = 15_000_000
MAX_CENA_POZEMEK = 5_000_000

# --- Kvalitativní kritéria -------------------------------------------------
# Pozemky: brát jen STAVEBNÍ (pro bydlení / výstavbu).
POZEMEK_JEN_STAVEBNI = True
# Domy: brát jen v dobrém stavu — novostavba / projekt / po rekonstrukci.
DUM_JEN_DOBRY_STAV = True

# Klíčová slova pro zdroje BEZ strukturovaného filtru (Bazoš, iDNES)
# a jako pojistka i jinde. Porovnává se bez diakritiky, malými písmeny.
POZEMEK_MUSI_OBSAHOVAT = [
    "stavebni", "k vystavbe", "parcela", "pro bydleni", "zasitov",
]
POZEMEK_NESMI_OBSAHOVAT = [
    "zahrad", "pole", "orna", "louka", "travni porost", "les", "lesni",
    "rybnik", "sad", "vinice", "komercni", "zemedel",
]
DUM_STAV_KLICOVA = [
    "novostavb", "projekt", "po rekonstrukci", "kompletni rekonstrukc",
    "zrekonstruov", "developer", "nova vystavb", "kolaudac", "velmi dobr",
]
# Jasně špatný stav domu — u scraping zdrojů takové inzeráty vyřadíme.
DUM_SPATNY_STAV = [
    "k rekonstrukci", "pred rekonstrukci", "nutna rekonstrukce", "k celkove rekonstrukci",
    "k demolici", "pred demolici", "ruina", "k uplne rekonstrukci", "vyzaduje rekonstrukci",
]

# Scraping zdroje (Bazoš, iDNES) mají krátké názvy bez uvedení stavu.
# Při True se filtr chová MÍRNĚ: vyřadí jen jasně nevhodné (zahrada/pole u pozemků,
# "k rekonstrukci" u domů), zbytek nechá projít (raději ukázat víc než něco minout).
# Při False musí název obsahovat přímo klíčové slovo (přísné, ale hodně vyřadí).
SCRAPING_FILTR_MIRNY = True

# Sreality kódy (posílají se serveru, ať filtruje rovnou on):
#   category_sub_cb pro pozemky: 18 = Bydlení (stavební). Uprav dle potřeby.
SREALITY_POZEMEK_STAVEBNI_SUB = 18
#   building_condition (stav objektu): 6=Novostavba, 5=Projekt, 8=Po rekonstrukci,
#   1=Velmi dobrý, 4=Ve výstavbě. Vyber, co chceš brát.
SREALITY_DUM_STAV_KODY = [6, 5, 8]

# --- Cílení na lokalitu přímo v dotazu (aby se nestahovala celá ČR) --------
# Sreality: skript si přes "našeptávač" sám najde okres podle názvu níže
# a hledá jen v něm (pak se ještě zúží na okruh kolem obcí přes GPS).
SREALITY_OKRES_FRAZE = "Frýdek-Místek"
# Kdyby našeptávač nefungoval, sem lze ručně vyplnit typ a id z Sreality
# (např. type="district"). Necháš-li prázdné, použije se našeptávač.
SREALITY_LOCALITY_TYPE = ""
SREALITY_LOCALITY_ID = ""

# Bazoš: hledá podle PSČ + okruhu. Uveď PSČ obcí (bez mezer) a okruh v km.
BAZOS_PSC = ["73914", "73904", "73951", "73938"]  # Ostravice, Raškovice, H./D. Domaslavice
BAZOS_OKRUH_KM = 10

# Podrobný výpis do logu (užitečné pro ladění v GitHub Actions).
VERBOSE = True
# --------------------------------------------------------------------------

# Ochrana proti přetížení serverů.
PER_PAGE = 60
MAX_STRANEK = 30

ZDE = os.path.dirname(os.path.abspath(__file__))
# Cesty k výstupům lze přebít proměnnými prostředí (využívá cloudový běh na GitHubu,
# kde se generuje rovnou index.html pro GitHub Pages).
SEEN_FILE = os.environ.get("SEEN_FILE") or os.path.join(ZDE, "seen.json")
DASHBOARD_FILE = os.environ.get("DASHBOARD_FILE") or os.path.join(ZDE, "dashboard.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}


# =========================================================================
#  Pomocné funkce (vzdálenost, text, filtry)
# =========================================================================

def _bez_diakritiky(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


OBCE_TEXTOVE_NORM = [_bez_diakritiky(o) for o in OBCE_TEXTOVE]
VYLOUCIT_NORM = [_bez_diakritiky(o) for o in LOKALITA_VYLOUCIT]


def je_vyloucena_lokalita(text):
    """True, pokud text lokality obsahuje některé z vyloučených měst (na celá slova)."""
    t = _bez_diakritiky(text)
    for v in VYLOUCIT_NORM:
        if v and re.search(r"\b" + re.escape(v) + r"\b", t):
            return True
    return False


def vzdalenost_km(lat1, lon1, lat2, lon2):
    """Haversine — vzdálenost dvou GPS bodů v km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nejblizsi_obec(lat, lon):
    nej = None
    for o in OBCE:
        d = vzdalenost_km(lat, lon, o["lat"], o["lon"])
        if nej is None or d < nej[1]:
            nej = (o["nazev"], d)
    return nej


def lokalita_vyhovuje(item):
    """
    Rozhodne, zda nabídka spadá do hledané oblasti.
    - Pokud má GPS: filtr radiusem od obcí.
    - Pokud nemá GPS: textová shoda názvu obce v poli 'lokalita'.
    Vrací (bool, nejblizsi_obec, vzdalenost_km_nebo_None).
    """
    # Vyloučené lokality (Karviná apod.) — platí vždy, i pro server-filtrované zdroje.
    if je_vyloucena_lokalita(item.get("lokalita", "")):
        return False, None, None

    # Zdroj už omezil lokalitu na serveru (např. Bazoš přes PSČ+okruh).
    if item.get("_lokalita_ok"):
        return True, None, None

    lat, lon = item.get("lat"), item.get("lon")
    if lat is not None and lon is not None:
        obec, d = nejblizsi_obec(lat, lon)
        return (d <= RADIUS_KM), obec, round(d, 1)

    lok = _bez_diakritiky(item.get("lokalita", ""))
    for nazev, nazev_norm in zip(OBCE_TEXTOVE, OBCE_TEXTOVE_NORM):
        if nazev_norm and nazev_norm in lok:
            return True, nazev, None
    return False, None, None


def format_cena(cena):
    if not cena:
        return "Cena na dotaz"
    return f"{cena:,.0f} Kč".replace(",", " ")


def projde_kriterii(item):
    """
    Kvalitativní filtr: stavební pozemky / dobrý stav domů.
    Zdroje, které už filtroval server (Sreality přes API parametry), mají
    item['_server_filtered']=True a projdou automaticky. Ostatní se posuzují
    podle klíčových slov v názvu + lokalitě.
    """
    text = _bez_diakritiky(f"{item.get('nazev','')} {item.get('lokalita','')}")

    if item.get("kategorie") == "Pozemek" and POZEMEK_JEN_STAVEBNI:
        if item.get("_server_filtered"):
            return True
        # Jasně nestavební (zahrada, pole, les…) vždy pryč.
        if any(z in text for z in POZEMEK_NESMI_OBSAHOVAT):
            return False
        # Mírný režim: generický "pozemek" necháme (může být stavební).
        if SCRAPING_FILTR_MIRNY:
            return True
        return any(k in text for k in POZEMEK_MUSI_OBSAHOVAT)

    if item.get("kategorie") == "Dům" and DUM_JEN_DOBRY_STAV:
        if item.get("_server_filtered"):
            return True
        # Jasně špatný stav vždy pryč.
        if any(b in text for b in DUM_SPATNY_STAV):
            return False
        # Mírný režim: dům bez uvedení stavu necháme projít.
        if SCRAPING_FILTR_MIRNY:
            return True
        return any(k in text for k in DUM_STAV_KLICOVA)

    return True


# =========================================================================
#  ZDROJ 1: Sreality.cz  (JSON API)
# =========================================================================

def _sreality_session():
    """Session se 'zahřátím' — návštěva homepage kvůli cookies, což někdy
    obejde blokaci datacentrových IP (např. na GitHub Actions)."""
    s = requests.Session()
    s.headers.update({**HEADERS, "Accept-Language": "cs,en;q=0.8"})
    try:
        s.get("https://www.sreality.cz/", timeout=30)
    except Exception:
        pass
    return s


def _sreality_lokalita_params(session):
    """
    Zjistí parametry pro omezení dotazu na region (okres) — buď z ručního
    nastavení, nebo přes našeptávač Sreality. Vrací dict, který se přidá
    do dotazu na inzeráty (např. {'locality_district_id': 72}).
    """
    if SREALITY_LOCALITY_TYPE and SREALITY_LOCALITY_ID:
        p = {f"locality_{SREALITY_LOCALITY_TYPE}_id": SREALITY_LOCALITY_ID}
        print(f"  Sreality: lokalita ručně = {p}")
        return p
    try:
        r = session.get("https://www.sreality.cz/api/cs/v2/suggest",
                        params={"phrase": SREALITY_OKRES_FRAZE, "count": 15},
                        timeout=30)
        r.raise_for_status()
        data = r.json()
        results = (data.get("results")
                   or (data.get("_embedded", {}) or {}).get("results")
                   or data.get("items") or [])
        best, first = None, None
        for it in results:
            s = it.get("settings") or it.get("userData") or it.get("data") or {}
            typ, val = s.get("type"), s.get("value")
            if not (typ and val):
                continue
            if first is None:
                first = (typ, val)
            if typ == "district":          # okres = ideální šíře záběru
                best = (typ, val)
                break
        chosen = best or first
        if chosen:
            p = {f"locality_{chosen[0]}_id": chosen[1]}
            print(f"  Sreality: našeptávač našel lokalitu = {p} "
                  f"(fráze '{SREALITY_OKRES_FRAZE}')")
            return p
        print("  ! Sreality: našeptávač nevrátil použitelný region — "
              "hledám bez omezení lokality (může vrátit málo výsledků).")
    except Exception as e:
        print(f"  ! Sreality: našeptávač selhal ({e}) — hledám bez omezení.")
    return {}


def zdroj_sreality():
    if requests is None:
        print("  ! requests není nainstalováno — Sreality přeskočeno.")
        return []
    API = "https://www.sreality.cz/api/cs/v2/estates"
    session = _sreality_session()
    lok_params = _sreality_lokalita_params(session)
    # category_main_cb: 2 = dům, 3 = pozemek; category_type_cb: 1 = prodej
    kategorie = [("Dům", 2, MAX_CENA_DUM), ("Pozemek", 3, MAX_CENA_POZEMEK)]
    out = []
    for kat_nazev, cmc, _max in kategorie:
        pocet_kat = 0
        for page in range(1, MAX_STRANEK + 1):
            params = {
                "category_main_cb": cmc, "category_type_cb": 1,
                "per_page": PER_PAGE, "page": page, "tms": int(time.time() * 1000),
            }
            params.update(lok_params)  # omezení na region (okres)
            # Kvalitativní kritéria řešíme rovnou na serveru Sreality.
            if cmc == 3 and POZEMEK_JEN_STAVEBNI:
                params["category_sub_cb"] = SREALITY_POZEMEK_STAVEBNI_SUB
            if cmc == 2 and DUM_JEN_DOBRY_STAV and SREALITY_DUM_STAV_KODY:
                params["building_condition"] = SREALITY_DUM_STAV_KODY  # opakuje se v URL
            try:
                r = session.get(API, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"  ! Sreality chyba ({kat_nazev}, str.{page}): {e}")
                break
            if page == 1 and VERBOSE:
                print(f"  Sreality {kat_nazev}: server hlásí result_size="
                      f"{data.get('result_size')} (URL: {r.url})")
            estates = (data.get("_embedded", {}) or {}).get("estates", []) or []
            if not estates:
                break
            pocet_kat += len(estates)
            for e in estates:
                gps = e.get("gps", {}) or {}
                links = e.get("_links", {}) or {}
                imgs = links.get("images") or []
                img = ""
                if imgs and isinstance(imgs[0], dict):
                    img = imgs[0].get("href", "")
                hash_id = e.get("hash_id")
                seo = (e.get("seo", {}) or {}).get("locality", "")
                url = (f"https://www.sreality.cz/detail/prodej/dum/rodinny/{seo}/{hash_id}"
                       if hash_id else "https://www.sreality.cz/")
                out.append({
                    "id": f"sreality-{hash_id}",
                    "zdroj": "Sreality",
                    "kategorie": kat_nazev,
                    "nazev": e.get("name", "") or "",
                    "lokalita": e.get("locality", "") or "",
                    "cena": e.get("price", 0) or 0,
                    "max_cena": _max,
                    "lat": gps.get("lat"), "lon": gps.get("lon"),
                    "url": url, "obrazek": img,
                    "_server_filtered": True,  # kritéria už vyřešilo Sreality API
                })
            if data.get("result_size") and page * PER_PAGE >= data["result_size"]:
                break
            time.sleep(0.4)
        if VERBOSE:
            print(f"  Sreality {kat_nazev}: staženo {pocet_kat} inzerátů (před filtrem lokality)")
    return out


# =========================================================================
#  ZDROJ 2: Bezrealitky.cz  (GraphQL API)
# =========================================================================

def zdroj_bezrealitky():
    if requests is None:
        print("  ! requests není nainstalováno — Bezrealitky přeskočeno.")
        return []
    API = "https://api.bezrealitky.cz/graphql/"
    # estateType: DUM / POZEMEK ; offerType: PRODEJ
    query = """
    query AdvertList($estateType:[EstateType],$offerType:[OfferType],$limit:Int,$offset:Int){
      listAdverts(estateType:$estateType, offerType:$offerType, limit:$limit, offset:$offset, order:TIMEORDER_DESC){
        list{
          id uri
          estateType offerType
          imageAltText(locale: CS)
          price
          address(locale: CS)
          gps{ lat lng }
          mainImage{ url(filter: RECORD_THUMB) }
        }
      }
    }"""
    kategorie = [("Dům", "DUM", MAX_CENA_DUM), ("Pozemek", "POZEMEK", MAX_CENA_POZEMEK)]
    out = []
    for kat_nazev, etype, _max in kategorie:
        offset = 0
        for _ in range(MAX_STRANEK):
            payload = {"query": query, "variables": {
                "estateType": [etype], "offerType": ["PRODEJ"],
                "limit": PER_PAGE, "offset": offset}}
            try:
                r = requests.post(API, json=payload, headers=HEADERS, timeout=30)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"  ! Bezrealitky chyba ({kat_nazev}): {e}")
                break
            if data.get("errors"):
                print(f"  ! Bezrealitky GraphQL chyba ({kat_nazev}): {data['errors']}")
            lst = (((data.get("data") or {}).get("listAdverts") or {}).get("list")) or []
            if offset == 0 and VERBOSE:
                print(f"  Bezrealitky {kat_nazev}: 1. dávka vrátila {len(lst)} inzerátů")
            if not lst:
                break
            for a in lst:
                gps = a.get("gps") or {}
                img = ((a.get("mainImage") or {}).get("url")) or ""
                uri = a.get("uri", "")
                out.append({
                    "id": f"bezrealitky-{a.get('id')}",
                    "zdroj": "Bezrealitky",
                    "kategorie": kat_nazev,
                    "nazev": a.get("imageAltText") or "Inzerát Bezrealitky",
                    "lokalita": a.get("address", "") or "",
                    "cena": a.get("price", 0) or 0,
                    "max_cena": _max,
                    "lat": gps.get("lat"), "lon": gps.get("lng"),
                    "url": f"https://www.bezrealitky.cz/nemovitosti-byty-domy/{uri}" if uri else "https://www.bezrealitky.cz/",
                    "obrazek": img,
                })
            offset += PER_PAGE
            time.sleep(0.4)
    return out


# =========================================================================
#  ZDROJ 3: Reality.iDNES.cz  (scraping HTML)  — best effort
# =========================================================================

def zdroj_idnes():
    if requests is None or BeautifulSoup is None:
        print("  ! requests/bs4 chybí — iDNES přeskočeno.")
        return []
    # s-qc[category] : 2=domy? Používáme veřejné URL s parametry ceny a typu.
    zakladny = [
        ("Dům", "https://reality.idnes.cz/s/prodej/domy/", MAX_CENA_DUM),
        ("Pozemek", "https://reality.idnes.cz/s/prodej/pozemky/", MAX_CENA_POZEMEK),
    ]
    out = []
    for kat_nazev, base, _max in zakladny:
        for page in range(1, 6):  # iDNES stránkuje, bereme prvních pár stran
            url = base if page == 1 else f"{base}?page={page}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as e:
                print(f"  ! iDNES chyba ({kat_nazev}, str.{page}): {e}")
                break
            karty = soup.select("div.c-products__item, div.c-list__item")
            if page == 1 and VERBOSE:
                print(f"  iDNES {kat_nazev}: nalezeno {len(karty)} karet (URL: {r.url})")
            if not karty:
                break
            for k in karty:
                a = k.select_one("a.c-products__link, a[href]")
                nazev_el = k.select_one(".c-products__title, h2, .c-list__title")
                cena_el = k.select_one(".c-products__price, .c-list__price")
                lok_el = k.select_one(".c-products__info, .c-list__info, address")
                img_el = k.select_one("img")
                href = a.get("href") if a else ""
                if href and href.startswith("/"):
                    href = "https://reality.idnes.cz" + href
                cena = _cislo_z_textu(cena_el.get_text() if cena_el else "")
                out.append({
                    "id": f"idnes-{_id_z_url(href)}",
                    "zdroj": "iDNES",
                    "kategorie": kat_nazev,
                    "nazev": (nazev_el.get_text(strip=True) if nazev_el else "Inzerát iDNES"),
                    "lokalita": (lok_el.get_text(" ", strip=True) if lok_el else ""),
                    "cena": cena, "max_cena": _max,
                    "lat": None, "lon": None,
                    "url": href or "https://reality.idnes.cz/",
                    "obrazek": (img_el.get("src") or img_el.get("data-src") or "") if img_el else "",
                })
            time.sleep(0.5)
    return out


# =========================================================================
#  ZDROJ 4: Bazoš.cz  (scraping HTML)  — best effort
# =========================================================================

def zdroj_bazos():
    if requests is None or BeautifulSoup is None:
        print("  ! requests/bs4 chybí — Bazoš přeskočeno.")
        return []
    # reality.bazos.cz — hledáme podle PSČ + okruhu (hlokalita + humkreis),
    # takže se rovnou omezíme na tvoji oblast.
    hledani = [
        ("Dům", "https://reality.bazos.cz/prodam/dum/", MAX_CENA_DUM),
        ("Pozemek", "https://reality.bazos.cz/prodam/pozemek/", MAX_CENA_POZEMEK),
    ]
    out = []
    videno_href = set()
    for kat_nazev, base, _max in hledani:
        pocet_kat = 0
        for psc in (BAZOS_PSC or [""]):
            for crz in range(0, 60, 20):  # stránkování po 20 (param crz)
                params = {
                    "hlokalita": psc,
                    "humkreis": BAZOS_OKRUH_KM,
                    "cenaod": "",
                    "cenado": _max,
                }
                if crz:
                    params["crz"] = crz
                try:
                    r = requests.get(base, params=params, headers=HEADERS, timeout=30)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")
                except Exception as e:
                    print(f"  ! Bazoš chyba ({kat_nazev}, PSČ {psc}): {e}")
                    break
                karty = soup.select("div.inzeraty.inzeratyflex, div.inzeraty, div.inzeratyflex")
                if crz == 0 and VERBOSE:
                    print(f"  Bazoš {kat_nazev} PSČ {psc}: nalezeno {len(karty)} karet "
                          f"(URL: {r.url})")
                if not karty:
                    break
                for k in karty:
                    a = k.select_one("h2.nadpis a, .inzeratynadpis a, a.nadpis, h2 a")
                    cena_el = k.select_one(".inzeratycena, span.cena")
                    lok_el = k.select_one(".inzeratylok, .lokalita")
                    img_el = k.select_one("img")
                    if not a:
                        continue
                    href = a.get("href", "")
                    if href and href.startswith("/"):
                        href = "https://reality.bazos.cz" + href
                    if href in videno_href:
                        continue
                    videno_href.add(href)
                    cena = _cislo_z_textu(cena_el.get_text() if cena_el else "")
                    out.append({
                        "id": f"bazos-{_id_z_url(href)}",
                        "zdroj": "Bazoš",
                        "kategorie": kat_nazev,
                        "nazev": a.get_text(strip=True) or "Inzerát Bazoš",
                        "lokalita": (lok_el.get_text(" ", strip=True) if lok_el else ""),
                        "cena": cena, "max_cena": _max,
                        "lat": None, "lon": None,
                        "url": href or "https://reality.bazos.cz/",
                        "obrazek": (img_el.get("src") or "") if img_el else "",
                        # PSČ+okruh omezil lokalitu na serveru → GPS filtr netřeba
                        "_lokalita_ok": True,
                    })
                    pocet_kat += 1
                time.sleep(0.4)
        if VERBOSE:
            print(f"  Bazoš {kat_nazev}: staženo {pocet_kat} inzerátů (v okruhu PSČ)")
    return out


def _cislo_z_textu(t):
    """Vytáhne cenu z textu. Bere jen ASCII číslice (pozor na 'm²' — '²' je
    v Unicode taky číslice!). Vezme první souvislé číslo (cenu) před 'Kč'."""
    if not t:
        return 0
    # Odřízneme případný údaj o ploše ("... m²") — cena bývá první číslo.
    t = t.split("m²")[-1] if "Kč" in t.split("m²")[-1] else t
    cislice = "".join(ch for ch in t if ch in "0123456789")
    if not cislice:
        return 0
    try:
        cena = int(cislice)
    except ValueError:
        return 0
    # Absurdně velké číslo = spojená plocha+cena apod. → ber jako "na dotaz".
    return cena if cena < 1_000_000_000 else 0


def _id_z_url(url):
    if not url:
        return str(int(time.time() * 1000))
    return url.rstrip("/").split("/")[-1][:40] or str(int(time.time() * 1000))


# =========================================================================
#  Sjednocení + filtr
# =========================================================================

ZDROJE_FUNKCE = {
    "sreality": zdroj_sreality,
    "bezrealitky": zdroj_bezrealitky,
    "idnes": zdroj_idnes,
    "bazos": zdroj_bazos,
}


def najdi_nemovitosti(demo=False):
    raw = []
    if demo:
        raw = _demo_data()
    else:
        for klic, zapnuto in ZDROJE_ZAPNUTE.items():
            if not zapnuto:
                continue
            print(f"Stahuji zdroj: {klic} ...")
            try:
                raw.extend(ZDROJE_FUNKCE[klic]())
            except Exception as e:
                print(f"  ! Zdroj {klic} selhal: {e}")

    if VERBOSE:
        syrove = {}
        for it in raw:
            syrove[it["zdroj"]] = syrove.get(it["zdroj"], 0) + 1
        print("\n--- Staženo celkem (před filtry) ---")
        for z, c in sorted(syrove.items()):
            print(f"   {z}: {c}")

    # Počítadla, kolik vypadlo na kterém filtru (pro diagnostiku).
    stat = {"cena": 0, "kriteria": 0, "lokalita": 0, "prohlo": 0}
    vyhovujici = []
    for item in raw:
        # Filtr ceny (cena 0 = "na dotaz" -> necháme projít).
        if item["cena"] and item["max_cena"] and item["cena"] > item["max_cena"]:
            stat["cena"] += 1
            continue
        # Kvalitativní filtr (stavební pozemek / dobrý stav domu).
        if not projde_kriterii(item):
            stat["kriteria"] += 1
            continue
        # Filtr lokality.
        ok, obec, d = lokalita_vyhovuje(item)
        if not ok:
            stat["lokalita"] += 1
            continue
        item["nejblizsi_obec"] = obec
        item["vzdalenost_km"] = d
        stat["prohlo"] += 1
        vyhovujici.append(item)

    if VERBOSE:
        print(f"--- Vyřazeno: cena={stat['cena']}, kritéria={stat['kriteria']}, "
              f"lokalita={stat['lokalita']} | prošlo={stat['prohlo']} ---\n")

    vyhovujici.sort(key=lambda x: (x.get("vzdalenost_km") if x.get("vzdalenost_km") is not None else 999,
                                   x.get("cena") or 0))
    return vyhovujici


# =========================================================================
#  Dedup
# =========================================================================

def nacti_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def uloz_seen(ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=0)


# =========================================================================
#  Dashboard
# =========================================================================

def vygeneruj_dashboard(nabidky, nove_ids):
    cas = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    pocet_novych = sum(1 for n in nabidky if n["id"] in nove_ids)
    data_json = json.dumps(
        [{**n, "je_nova": n["id"] in nove_ids, "cena_text": format_cena(n["cena"])}
         for n in nabidky], ensure_ascii=False)
    obce_txt = ", ".join(o["nazev"] for o in OBCE)
    zdroje_txt = ", ".join(k for k, v in ZDROJE_ZAPNUTE.items() if v)
    kriteria = []
    kriteria.append("pozemky jen stavební" if POZEMEK_JEN_STAVEBNI else "pozemky všechny")
    kriteria.append("domy jen v dobrém stavu (novostavba / projekt / po rekonstrukci)"
                    if DUM_JEN_DOBRY_STAV else "domy všechny")
    kriteria_txt = "; ".join(kriteria)

    out = (HTML_SABLONA
           .replace("__CAS__", html.escape(cas))
           .replace("__POCET__", str(len(nabidky)))
           .replace("__POCET_NOVYCH__", str(pocet_novych))
           .replace("__OBCE__", html.escape(obce_txt))
           .replace("__ZDROJE__", html.escape(zdroje_txt))
           .replace("__KRITERIA__", html.escape(kriteria_txt))
           .replace("__RADIUS__", str(int(RADIUS_KM)))
           .replace("__MAX_DUM__", format_cena(MAX_CENA_DUM))
           .replace("__MAX_POZEMEK__", format_cena(MAX_CENA_POZEMEK))
           .replace("/*__DATA__*/", data_json))
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(out)


# =========================================================================
#  Demo data (--demo, bez internetu)
# =========================================================================

def _demo_data():
    # Sloupce: zdroj, kategorie, název, lokalita, cena, lat, lon, server_filtered
    v = [
        # --- projdou (dům v dobrém stavu) ---
        ("Sreality", "Dům", "Prodej rodinného domu 5+kk, 180 m²", "Ostravice, okres Frýdek-Místek", 8_900_000, 49.537, 18.390, True),
        ("Sreality", "Dům", "Novostavba rodinného domu 6+kk, 220 m²", "Horní Domaslavice", 14_500_000, 49.699, 18.466, True),
        ("iDNES", "Dům", "Rodinný dům 4+1 po rekonstrukci, 140 m²", "Dolní Domaslavice", 12_800_000, None, None, False),
        ("Bezrealitky", "Dům", "Prodej domu – developerský projekt novostavby", "Raškovice", 9_300_000, 49.612, 18.440, False),
        # --- vypadnou (dům ve špatném stavu / nad rozpočet / daleko) ---
        ("Bezrealitky", "Dům", "Chalupa 3+1 k rekonstrukci", "Raškovice", 5_400_000, 49.612, 18.440, False),   # špatný stav
        ("Sreality", "Dům", "Luxusní vila 7+kk", "Frýdek-Místek", 19_900_000, 49.685, 18.350, True),           # nad rozpočet
        ("Bazoš", "Dům", "Prodám dům po rekonstrukci v Ostravě", "Ostrava-Poruba", 6_500_000, None, None, False), # daleko
        # --- projdou (stavební pozemky) ---
        ("Bezrealitky", "Pozemek", "Stavební pozemek 1 200 m²", "Ostravice", 3_600_000, 49.530, 18.383, False),
        ("Bazoš", "Pozemek", "Prodám stavební parcelu 900 m²", "Pražmo u Raškovic", 2_950_000, None, None, False),
        ("iDNES", "Pozemek", "Stavební pozemek pro bydlení 2 500 m²", "Raškovice, Beskydy", 4_200_000, None, None, False),
        # --- vypadnou (nestavební pozemky) ---
        ("Bazoš", "Pozemek", "Prodám zahradu 800 m²", "Ostravice", 1_200_000, None, None, False),               # zahrada
        ("iDNES", "Pozemek", "Zemědělský pozemek – orná půda 5 000 m²", "Dolní Domaslavice", 2_100_000, None, None, False), # pole
    ]
    out = []
    for i, (zdroj, kat, nazev, lok, cena, lat, lon, srv) in enumerate(v, 1):
        out.append({
            "id": f"{zdroj.lower()}-demo{i}",
            "zdroj": zdroj, "kategorie": kat, "nazev": nazev, "lokalita": lok,
            "cena": cena, "max_cena": MAX_CENA_DUM if kat == "Dům" else MAX_CENA_POZEMEK,
            "lat": lat, "lon": lon,
            "url": "https://www.sreality.cz/", "obrazek": "",
            "_server_filtered": srv,
        })
    return out


# =========================================================================
#  Main
# =========================================================================

def main():
    ap = argparse.ArgumentParser(description="Realitní asistent — více serverů")
    ap.add_argument("--demo", action="store_true",
                    help="Ukázkový běh s testovacími daty (bez internetu).")
    args = ap.parse_args()

    print("=" * 60)
    print("REALITNÍ ASISTENT — domy a pozemky (Sreality, Bezrealitky, iDNES, Bazoš)")
    print("=" * 60)

    nabidky = najdi_nemovitosti(demo=args.demo)
    seen = nacti_seen()
    aktualni_ids = {n["id"] for n in nabidky}
    nove_ids = (aktualni_ids - seen) if seen else set()

    vygeneruj_dashboard(nabidky, nove_ids)
    uloz_seen(aktualni_ids)

    # Přehled podle zdroje.
    podle_zdroje = {}
    for n in nabidky:
        podle_zdroje[n["zdroj"]] = podle_zdroje.get(n["zdroj"], 0) + 1

    print(f"\nNalezeno vyhovujících nabídek: {len(nabidky)}")
    for z, c in sorted(podle_zdroje.items()):
        print(f"   - {z}: {c}")
    if seen:
        print(f"NOVÝCH od minula: {len(nove_ids)}")
    else:
        print("(První běh — příště se budou zvýrazňovat nové nabídky.)")
    print(f"\nDashboard: {DASHBOARD_FILE}")
    print("Otevřít:   open dashboard.html")


if __name__ == "__main__":
    main()
