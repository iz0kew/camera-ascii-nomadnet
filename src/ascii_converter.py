"""Converte un'immagine in ASCII art.

Copre le stesse leve di asciiart.eu (larghezza, rampa di caratteri,
luminosita'/contrasto, inversione) piu' due aggiunte:
- edge-detection mescolata alla luminosita', per contorni piu' leggibili
  su soggetti con poco contrasto (es. inquadrature notturne della camera);
- modalita' colore, che genera tag colore Micron per riga (usata solo se
  l'interfaccia di trasporto lo permette, vedi COLOR_MODE in config).
"""
from __future__ import annotations

import io
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import AsciiConfig


def _load_image(jpeg_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")


def _resize_for_ascii(image: Image.Image, width: int, char_aspect_ratio: float) -> Image.Image:
    w, h = image.size
    width = max(1, width)
    height = max(1, int((h / w) * width / char_aspect_ratio))
    return image.resize((width, height))


def _apply_enhancements(image: Image.Image, cfg: AsciiConfig) -> Image.Image:
    if cfg.brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(cfg.brightness)
    if cfg.contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(cfg.contrast)
    if cfg.gamma != 1.0:
        inv_gamma = 1.0 / cfg.gamma
        lut = [min(255, int((i / 255.0) ** inv_gamma * 255.0)) for i in range(256)]
        image = image.point(lut)
    return image


def _luminance_array(image: Image.Image, cfg: AsciiConfig) -> np.ndarray:
    gray = ImageOps.grayscale(image)
    gray_arr = np.asarray(gray, dtype=np.float32)
    if cfg.edge_detect:
        edges_arr = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
        gray_arr = gray_arr * (1 - cfg.edge_mix) + edges_arr * cfg.edge_mix
    return np.clip(gray_arr, 0, 255)


def _char_for_value(value: float, ramp: str) -> str:
    idx = int((value / 255.0) * (len(ramp) - 1))
    return ramp[max(0, min(len(ramp) - 1, idx))]


def _rgb_to_micron_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(c))) // 16 for c in rgb)
    return f"{r:x}{g:x}{b:x}"


def _render_mono(luminance: np.ndarray, ramp: str) -> str:
    lines = ["".join(_char_for_value(v, ramp) for v in row) for row in luminance]
    return "\n".join(lines)


def _render_color(luminance: np.ndarray, rgb_arr: np.ndarray, ramp: str) -> str:
    """Genera righe con tag colore Micron `FxxxTesto`f, raggruppando i run di
    pixel dello stesso colore cosi' da non moltiplicare i byte per carattere."""
    height, width = luminance.shape
    lines: List[str] = []
    for y in range(height):
        parts: List[str] = []
        current_color = None
        run_chars: List[str] = []
        for x in range(width):
            char = _char_for_value(luminance[y, x], ramp)
            color = _rgb_to_micron_hex(tuple(rgb_arr[y, x]))
            if color != current_color:
                if run_chars:
                    parts.append(f"`F{current_color}" + "".join(run_chars) + "`f")
                run_chars = []
                current_color = color
            run_chars.append(char)
        if run_chars:
            parts.append(f"`F{current_color}" + "".join(run_chars) + "`f")
        lines.append("".join(parts))
    return "\n".join(lines)


def image_to_ascii(jpeg_bytes: bytes, cfg: AsciiConfig) -> str:
    """Converte i byte di un'immagine (JPEG/PNG) in una stringa ASCII art."""
    image = _load_image(jpeg_bytes)
    image = _resize_for_ascii(image, cfg.width, cfg.char_aspect_ratio)
    image = _apply_enhancements(image, cfg)

    luminance = _luminance_array(image, cfg)
    ramp = cfg.ramp()
    if cfg.invert:
        ramp = ramp[::-1]

    if cfg.color_mode == "color":
        rgb_arr = np.asarray(image, dtype=np.uint8)
        return _render_color(luminance, rgb_arr, ramp)
    return _render_mono(luminance, ramp)
