"""Loop di scheduling: cattura periodicamente uno snapshot dalla camera,
lo converte in ASCII art e aggiorna la cache letta dalla pagina NomadNet.

Va eseguito come processo indipendente e di lunga durata, separato dalla
pagina NomadNet (che deve rispondere subito e non puo' fare I/O di rete
lento ad ogni richiesta), ad esempio:

    python -m src.scheduler
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from .ascii_converter import image_to_ascii
from .config import Settings, cache_paths, load_settings
from .onvif_camera import CameraError, get_snapshot_jpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def _write_atomic(path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def capture_once(settings: Settings) -> None:
    latest_txt, latest_meta = cache_paths(settings.camera)
    now = datetime.now(timezone.utc).isoformat()
    try:
        jpeg_bytes = get_snapshot_jpeg(settings.camera)
        ascii_art = image_to_ascii(jpeg_bytes, settings.ascii)
        _write_atomic(latest_txt, ascii_art)
        _write_atomic(latest_meta, json.dumps({"updated_at": now, "error": None}, indent=2))
        logger.info("Snapshot aggiornato (%d caratteri)", len(ascii_art))
    except CameraError as exc:
        logger.error("Cattura fallita: %s", exc)
        _write_atomic(latest_meta, json.dumps({"updated_at": now, "error": str(exc)}, indent=2))
    except Exception as exc:  # difesa da errori imprevisti: il loop non deve mai morire
        logger.exception("Errore imprevisto durante la cattura")
        _write_atomic(latest_meta, json.dumps({"updated_at": now, "error": str(exc)}, indent=2))


def run_forever() -> None:
    logger.info("Scheduler avviato")
    while True:
        # Ricaricate ad ogni ciclo: le modifiche fatte dalla Web UI diventano
        # effettive dal giro successivo, senza dover riavviare il processo.
        settings = load_settings()
        capture_once(settings)
        time.sleep(max(1, settings.camera.snapshot_interval_seconds))


if __name__ == "__main__":
    run_forever()
