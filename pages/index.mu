#!/usr/bin/env python3
"""Pagina Micron dinamica per NomadNet: mostra l'ultimo screenshot della
telecamera convertito in ASCII art.

Va installata come file ESEGUIBILE nella cartella "pages" di un nodo
NomadNet (vedi scripts/install_nomadnet_page.sh). Legge solo il JPEG in
cache scritto da src/scheduler.py (mai la camera direttamente, cosi'
risponde in fretta) e lo converte in ASCII art al volo, cosi' la modalita'
colore (mono/a colori) e' una scelta che si puo' fare ad ogni richiesta
tramite i link in fondo alla pagina, invece di restare "congelata" a
quella impostata nella Web UI.

La modalita' richiesta arriva dal client NomadNet come variabile
d'ambiente "var_color_mode" (vedi i link "`[...`:/page/index.mu`color_mode=...]"
qui sotto: ogni coppia chiave=valore nella coda di un link Micron viene
inviata allo script come variabile d'ambiente "var_<chiave>", per
convenzione di NomadNet stesso - confermato leggendo Node.py/Browser.py
del progetto NomadNet). Se assente o non valida, si usa il default da
config/ascii_config.json (quello impostabile dalla Web UI).

Nota sulla sintassi Micron usata qui sotto (intestazioni `>`, link
`` `[testo`:percorso] ``, blocco letterale `` `= ``...`` `= ``): verificata
su piu' fonti pubbliche ma puo' variare leggermente tra versioni di
NomadNet. In caso di rendering inatteso, confronta con la guida integrata
del client (tab Guide -> Markup).
"""
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

BASE_DIR = Path(os.path.realpath(__file__)).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ascii_converter import image_to_ascii  # noqa: E402
from src.config import cache_paths, load_settings  # noqa: E402

settings = load_settings()
latest_jpg, latest_meta = cache_paths(settings.camera)

meta = {}
if latest_meta.exists():
    try:
        meta = json.loads(latest_meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        meta = {}

updated_at = meta.get("updated_at")
error = meta.get("error")

requested_mode = os.environ.get("var_color_mode")
if requested_mode not in ("mono", "color"):
    requested_mode = settings.ascii.color_mode

print(">Telecamera - ASCII Snapshot")
print()

if updated_at:
    print(f"Ultimo aggiornamento: {updated_at} UTC")
if error:
    print(f"`!Attenzione`!: ultima cattura fallita - {error}")
print()

if latest_jpg.exists() and latest_jpg.stat().st_size > 0:
    ascii_cfg = replace(settings.ascii, color_mode=requested_mode)
    ascii_art = image_to_ascii(latest_jpg.read_bytes(), ascii_cfg, target="micron")
    if requested_mode == "color":
        # I tag colore Micron (`Fxxx...`f) devono restare fuori dal blocco
        # letterale qui sotto, altrimenti il client li mostra come testo
        # grezzo invece di interpretarli (il blocco letterale disattiva
        # ogni parsing di markup, non solo il reflow del testo).
        print(ascii_art)
    else:
        print("`=")
        print(ascii_art)
        print("`=")
else:
    print("Nessuno snapshot disponibile ancora.")
    print("Verifica che lo scheduler (python -m src.scheduler) sia in esecuzione.")

print()
print("-")
mono_label = "Mono (attivo)" if requested_mode == "mono" else "Mono"
color_label = "A colori (attivo)" if requested_mode == "color" else "A colori"
print(f"`[{mono_label}`:/page/index.mu`color_mode=mono]")
print(f"`[{color_label}`:/page/index.mu`color_mode=color]")
print(f"`[Aggiorna`:/page/index.mu`color_mode={requested_mode}]")
