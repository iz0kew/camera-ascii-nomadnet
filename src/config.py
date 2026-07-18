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
    wsdl_dir: str = ""
    capture_method: str = "onvif"  # onvif | rtsp
    snapshot_interval_seconds: int = 60
    cache_dir: str = "cache"


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
        wsdl_dir=os.getenv("CAMERA_WSDL_DIR", ""),
        capture_method=os.getenv("CAPTURE_METHOD", "onvif"),
        snapshot_interval_seconds=int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "60") or 60),
        cache_dir=os.getenv("CACHE_DIR", "cache"),
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
    set_key(str(ENV_PATH), "CAMERA_WSDL_DIR", camera.wsdl_dir)
    set_key(str(ENV_PATH), "CAPTURE_METHOD", camera.capture_method)
    set_key(str(ENV_PATH), "SNAPSHOT_INTERVAL_SECONDS", str(camera.snapshot_interval_seconds))
    set_key(str(ENV_PATH), "CACHE_DIR", camera.cache_dir)


def save_ascii_config(ascii_cfg: AsciiConfig) -> None:
    ASCII_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASCII_CONFIG_PATH.write_text(json.dumps(asdict(ascii_cfg), indent=2), encoding="utf-8")


def cache_paths(camera: CameraConfig) -> Tuple[Path, Path]:
    cache_dir = Path(camera.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = BASE_DIR / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "latest.txt", cache_dir / "latest_meta.json"
