"""Carica e salva la configurazione condivisa da .env e config/ascii_config.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
ASCII_CONFIG_PATH = BASE_DIR / "config" / "ascii_config.json"

# Il pacchetto onvif-zeep punta di default a un percorso WSDL che spesso non
# viene installato correttamente dal wheel su PyPI. Vendorizziamo qui una
# copia nota funzionante (da github.com/FalkTannhaeuser/python-onvif-zeep)
# cosi' il progetto funziona subito senza configurazione aggiuntiva.
VENDORED_WSDL_DIR = BASE_DIR / "vendor" / "wsdl"

RAMP_PRESETS = {
    "standard": " .:-=+*#%@",
    "detailed": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "blocks": " ░▒▓█",
}


@dataclass
class CameraConfig:
    ip: str = ""
    port: int = 80
    user: str = ""
    password: str = ""
    protocol: str = "onvif"  # onvif | dahua | reolink | rtsp
    wsdl_dir: str = ""
    capture_method: str = "snapshot"  # snapshot (HTTP/CGI, consigliato) | rtsp (frame da stream)
    channel: int = 1  # canale/telecamera su NVR multi-canale (Dahua e Reolink)
    stream_subtype: str = "main"  # main | sub - risoluzione stream RTSP (Dahua/Reolink)
    rtsp_url: str = ""  # URL RTSP completo, usato solo con protocol="rtsp"
    snapshot_interval_seconds: int = 60
    cache_dir: str = "cache"
    save_history: bool = False
    history_retention_hours: int = 168  # 7 giorni
    history_max_files: int = 500  # tetto di sicurezza indipendente dall'eta'

    def resolved_wsdl_dir(self) -> str:
        """Percorso WSDL da usare davvero: quello custom se impostato,
        altrimenti la copia vendorizzata funzionante. Unico punto dove si
        applica questo fallback, cosi' vale sia per le CameraConfig lette da
        .env (load_settings) sia per quelle costruite al volo da un form
        (es. il pulsante "Cattura ora" della Web UI, che non passa da .env)."""
        return self.wsdl_dir or str(VENDORED_WSDL_DIR)


@dataclass
class AsciiConfig:
    width: int = 100
    char_aspect_ratio: float = 2.0
    ramp_preset: str = "standard"
    custom_ramp: str = ""
    brightness: float = 1.0
    contrast: float = 1.0
    gamma: float = 1.0
    invert: bool = False
    edge_detect: bool = False
    edge_mix: float = 0.5
    color_mode: str = "mono"  # mono | color
    color_palette: str = "full"  # full (4096 sfumature) | 16 | 8 (palette ANSI)

    def ramp(self) -> str:
        return self.custom_ramp if self.custom_ramp else RAMP_PRESETS.get(
            self.ramp_preset, RAMP_PRESETS["standard"]
        )


@dataclass
class Settings:
    camera: CameraConfig
    ascii: AsciiConfig


def load_settings() -> Settings:
    load_dotenv(ENV_PATH, override=True)

    camera = CameraConfig(
        ip=os.getenv("CAMERA_IP", ""),
        port=int(os.getenv("CAMERA_PORT", "80") or 80),
        user=os.getenv("CAMERA_USER", ""),
        password=os.getenv("CAMERA_PASSWORD", ""),
        protocol=os.getenv("CAMERA_PROTOCOL", "onvif"),
        wsdl_dir=os.getenv("CAMERA_WSDL_DIR", ""),
        capture_method=os.getenv("CAPTURE_METHOD", "snapshot"),
        channel=int(os.getenv("CAMERA_CHANNEL", "1") or 1),
        stream_subtype=os.getenv("CAMERA_STREAM_SUBTYPE", "main"),
        rtsp_url=os.getenv("CAMERA_RTSP_URL", ""),
        snapshot_interval_seconds=int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "60") or 60),
        cache_dir=os.getenv("CACHE_DIR", "cache"),
        save_history=os.getenv("SAVE_HISTORY", "false").strip().lower() in ("1", "true", "yes", "on"),
        history_retention_hours=int(os.getenv("HISTORY_RETENTION_HOURS", "168") or 168),
        history_max_files=int(os.getenv("HISTORY_MAX_FILES", "500") or 500),
    )

    ascii_cfg = AsciiConfig()
    if ASCII_CONFIG_PATH.exists():
        data = json.loads(ASCII_CONFIG_PATH.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(ascii_cfg, key):
                setattr(ascii_cfg, key, value)

    return Settings(camera=camera, ascii=ascii_cfg)


def save_camera_config(camera: CameraConfig) -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), "CAMERA_IP", camera.ip)
    set_key(str(ENV_PATH), "CAMERA_PORT", str(camera.port))
    set_key(str(ENV_PATH), "CAMERA_USER", camera.user)
    set_key(str(ENV_PATH), "CAMERA_PASSWORD", camera.password)
    set_key(str(ENV_PATH), "CAMERA_PROTOCOL", camera.protocol)
    set_key(str(ENV_PATH), "CAMERA_WSDL_DIR", camera.wsdl_dir)
    set_key(str(ENV_PATH), "CAPTURE_METHOD", camera.capture_method)
    set_key(str(ENV_PATH), "CAMERA_CHANNEL", str(camera.channel))
    set_key(str(ENV_PATH), "CAMERA_STREAM_SUBTYPE", camera.stream_subtype)
    set_key(str(ENV_PATH), "CAMERA_RTSP_URL", camera.rtsp_url)
    set_key(str(ENV_PATH), "SNAPSHOT_INTERVAL_SECONDS", str(camera.snapshot_interval_seconds))
    set_key(str(ENV_PATH), "CACHE_DIR", camera.cache_dir)
    set_key(str(ENV_PATH), "SAVE_HISTORY", "true" if camera.save_history else "false")
    set_key(str(ENV_PATH), "HISTORY_RETENTION_HOURS", str(camera.history_retention_hours))
    set_key(str(ENV_PATH), "HISTORY_MAX_FILES", str(camera.history_max_files))


def save_ascii_config(ascii_cfg: AsciiConfig) -> None:
    ASCII_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASCII_CONFIG_PATH.write_text(json.dumps(asdict(ascii_cfg), indent=2), encoding="utf-8")


def _resolved_cache_dir(camera: CameraConfig) -> Path:
    cache_dir = Path(camera.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = BASE_DIR / cache_dir
    return cache_dir


def cache_paths(camera: CameraConfig) -> Tuple[Path, Path]:
    cache_dir = _resolved_cache_dir(camera)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "latest.jpg", cache_dir / "latest_meta.json"


def history_dir_path(camera: CameraConfig) -> Path:
    history_dir = _resolved_cache_dir(camera) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir
