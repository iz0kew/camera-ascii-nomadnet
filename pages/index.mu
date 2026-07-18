#!/usr/bin/env python3
"""Pagina Micron dinamica per NomadNet: mostra l'ultimo screenshot della
telecamera convertito in ASCII art.

Va installata come file ESEGUIBILE nella cartella "pages" di un nodo
NomadNet (vedi scripts/install_nomadnet_page.sh). Legge solo la cache
scritta da src/scheduler.py: non si collega mai direttamente alla camera,
cosi' risponde in fretta e non blocca il nodo durante la richiesta.

Nota sulla sintassi Micron usata qui sotto (intestazioni `>`, link
`` `[testo`:percorso] ``, blocco letterale `` `= ``...`` `= ``): verificata
su piu' fonti pubbliche ma puo' variare leggermente tra versioni di
NomadNet. In caso di rendering inatteso, confronta con la guida integrata
del client (tab Guide -> Markup).
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(os.path.realpath(__file__)).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.config import cache_paths, load_settings  # noqa: E402

settings = load_settings()
latest_txt, latest_meta = cache_paths(settings.camera)

meta = {}
if latest_meta.exists():
    try:
        meta = json.loads(latest_meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        meta = {}

updated_at = meta.get("updated_at")
error = meta.get("error")

print(">Telecamera - ASCII Snapshot")
print()

if updated_at:
    print(f"Ultimo aggiornamento: {updated_at} UTC")
if error:
    print(f"`!Attenzione`!: ultima cattura fallita - {error}")
print()

if latest_txt.exists() and latest_txt.stat().st_size > 0:
    ascii_art = latest_txt.read_text(encoding="utf-8")
    print("`=")
    print(ascii_art)
    print("`=")
else:
    print("Nessuno snapshot disponibile ancora.")
    print("Verifica che lo scheduler (python -m src.scheduler) sia in esecuzione.")

print()
print("-")
print("`[Aggiorna`:/page/index.mu]")
