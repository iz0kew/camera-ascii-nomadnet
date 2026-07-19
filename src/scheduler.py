"""Loop di scheduling: cattura periodicamente uno snapshot dalla camera
e lo salva nella cache letta dalla pagina NomadNet. La conversione in ASCII
art (mono/colore) avviene invece al volo in pages/index.mu ad ogni
richiesta, cosi' la modalita' colore e' una scelta per-richiesta e non
resta "congelata" a quella impostata al momento della cattura.

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

from .config import CameraConfig, Settings, cache_paths, history_dir_path, load_settings
from .onvif_camera import CameraError, get_snapshot_jpeg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def _write_atomic(path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _write_atomic_bytes(path, content: bytes) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(content)
    os.replace(tmp_path, path)


def _save_history_snapshot(camera: CameraConfig, jpeg_bytes: bytes, timestamp: datetime) -> None:
    """Salva una copia dello snapshot in cache/history/, con nome a timestamp
    (formato senza ':' per restare valido anche su filesystem Windows)."""
    filename = timestamp.strftime("%Y%m%dT%H%M%SZ") + ".jpg"
    (history_dir_path(camera) / filename).write_bytes(jpeg_bytes)


def _prune_history(camera: CameraConfig) -> None:
    """Rimuove dallo storico i file oltre la scadenza configurata e, come
    ulteriore tetto di sicurezza, quelli in eccesso rispetto al numero
    massimo consentito (i piu' vecchi per primi). Un valore <= 0 disattiva
    il relativo criterio."""
    if camera.history_retention_hours <= 0 and camera.history_max_files <= 0:
        return

    files = sorted(history_dir_path(camera).glob("*.jpg"), key=lambda p: p.stat().st_mtime)
    removed = 0

    if camera.history_retention_hours > 0:
        cutoff = time.time() - camera.history_retention_hours * 3600
        kept = []
        for f in files:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
            else:
                kept.append(f)
        files = kept

    if camera.history_max_files > 0 and len(files) > camera.history_max_files:
        excess = len(files) - camera.history_max_files
        for f in files[:excess]:
            f.unlink(missing_ok=True)
            removed += 1

    if removed:
        logger.info("Storico: rimossi %d screenshot vecchi", removed)


def capture_once(settings: Settings) -> None:
    latest_jpg, latest_meta = cache_paths(settings.camera)
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    try:
        jpeg_bytes = get_snapshot_jpeg(settings.camera)
        _write_atomic_bytes(latest_jpg, jpeg_bytes)
        _write_atomic(latest_meta, json.dumps({"updated_at": now, "error": None}, indent=2))
        logger.info("Snapshot aggiornato (%d byte)", len(jpeg_bytes))

        if settings.camera.save_history:
            _save_history_snapshot(settings.camera, jpeg_bytes, now_dt)
            _prune_history(settings.camera)
    except CameraError as exc:
        # Il dettaglio completo (con IP, porta, URI e in certi casi persino
        # le credenziali RTSP) va solo nel log locale: il messaggio scritto
        # in cache/latest_meta.json e' letto anche dalla pagina NomadNet
        # pubblica (pages/index.mu), quindi deve restare generico.
        logger.error("Cattura fallita: %s", exc)
        _write_atomic(
            latest_meta,
            json.dumps({"updated_at": now, "error": "Errore nella comunicazione con la telecamera"}, indent=2),
        )
    except Exception:  # difesa da errori imprevisti: il loop non deve mai morire
        logger.exception("Errore imprevisto durante la cattura")
        _write_atomic(
            latest_meta,
            json.dumps({"updated_at": now, "error": "Errore imprevisto durante la cattura"}, indent=2),
        )


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
