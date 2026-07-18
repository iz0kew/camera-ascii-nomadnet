"""Converte un'immagine in ASCII art.

Copre le stesse leve di asciiart.eu (larghezza, rampa di caratteri,
luminosita'/contrasto, inversione) piu' due aggiunte:
- edge-detection mescolata alla luminosita', per contorni piu' leggibili
  su soggetti con poco contrasto (es. inquadrature notturne della camera);
- modalita' colore, che genera tag colore Micron per riga (usata solo se
  l'interfaccia di trasporto lo permette, vedi COLOR_MODE in config).
"""
from __future__ import annotations

import html
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


# Palette terminale ANSI standard (xterm), usata per le modalita' colore
# "8" e "16": accorpa i pixel simili su un numero fisso di colori, cosi' i
# run consecutivi diventano piu' lunghi (pagina Micron piu' leggera) e il
# risultato ricorda l'estetica di un terminale a 8/16 colori.
_ANSI_PALETTE_8 = np.array(
    [
        (0, 0, 0),
        (128, 0, 0),
        (0, 128, 0),
        (128, 128, 0),
        (0, 0, 128),
        (128, 0, 128),
        (0, 128, 128),
        (192, 192, 192),
    ],
    dtype=np.int16,
)

_ANSI_PALETTE_16 = np.concatenate(
    [
        _ANSI_PALETTE_8,
        np.array(
            [
                (128, 128, 128),
                (255, 0, 0),
                (0, 255, 0),
                (255, 255, 0),
                (0, 0, 255),
                (255, 0, 255),
                (0, 255, 255),
                (255, 255, 255),
            ],
            dtype=np.int16,
        ),
    ]
)

_ANSI_PALETTES = {"8": _ANSI_PALETTE_8, "16": _ANSI_PALETTE_16}


def _quantize_to_palette(rgb_arr: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Rimpiazza ogni pixel con il colore piu' vicino (distanza euclidea) della
    palette data."""
    pixels = rgb_arr.astype(np.int32)
    diffs = pixels[:, :, None, :] - palette[None, None, :, :].astype(np.int32)
    distances = np.sum(diffs ** 2, axis=-1)
    nearest_idx = np.argmin(distances, axis=-1)
    return palette[nearest_idx].astype(np.uint8)


def _render_mono(luminance: np.ndarray, ramp: str) -> str:
    lines = ["".join(_char_for_value(v, ramp) for v in row) for row in luminance]
    return "\n".join(lines)


def _color_runs_per_row(
    luminance: np.ndarray, rgb_arr: np.ndarray, ramp: str
) -> List[List[Tuple[str, str]]]:
    """Per ogni riga, calcola i run consecutivi di pixel con lo stesso colore
    quantizzato (colore Micron a 3 cifre hex, es. "f30") come lista di
    coppie (colore, testo). Un solo posto dove si decide come raggruppare i
    pixel, riusato sia dal renderer Micron sia da quello HTML per l'anteprima."""
    height, width = luminance.shape
    rows: List[List[Tuple[str, str]]] = []
    for y in range(height):
        runs: List[Tuple[str, str]] = []
        current_color = None
        run_chars: List[str] = []
        for x in range(width):
            char = _char_for_value(luminance[y, x], ramp)
            color = _rgb_to_micron_hex(tuple(rgb_arr[y, x]))
            if color != current_color:
                if run_chars:
                    runs.append((current_color, "".join(run_chars)))
                run_chars = []
                current_color = color
            run_chars.append(char)
        if run_chars:
            runs.append((current_color, "".join(run_chars)))
        rows.append(runs)
    return rows


def _render_color_micron(rows: List[List[Tuple[str, str]]]) -> str:
    """Renderizza i run colore come tag Micron `FxxxTesto`f, per la pagina
    NomadNet reale."""
    lines = ["".join(f"`F{color}{text}`f" for color, text in row) for row in rows]
    return "\n".join(lines)


def _micron_hex_to_css(hexcode: str) -> str:
    return "#" + "".join(ch * 2 for ch in hexcode)


def _render_color_html(rows: List[List[Tuple[str, str]]]) -> str:
    """Renderizza i run colore come <span> HTML, per l'anteprima nel browser
    della Web UI (che non sa interpretare la sintassi Micron)."""
    lines = []
    for row in rows:
        parts = [
            f'<span style="color:{_micron_hex_to_css(color)}">{html.escape(text)}</span>'
            for color, text in row
        ]
        lines.append("".join(parts))
    return "\n".join(lines)


def image_to_ascii(jpeg_bytes: bytes, cfg: AsciiConfig, target: str = "micron") -> str:
    """Converte i byte di un'immagine (JPEG/PNG) in una stringa ASCII art.

    "target" sceglie il formato di output della modalita' colore:
    - "micron" (default): tag colore Micron, per la pagina NomadNet reale.
    - "html": <span> con colore CSS, per l'anteprima nel browser della Web UI.
    In modalita' mono "target" non ha effetto: e' sempre testo semplice.

    "cfg.color_palette" sceglie la ricchezza di colore quando color_mode e'
    "color": "full" (fino a 4096 sfumature, 16 livelli per canale), "16" o
    "8" (palette terminale ANSI, pagina piu' leggera e look piu' "retro").
    """
    image = _load_image(jpeg_bytes)
    image = _resize_for_ascii(image, cfg.width, cfg.char_aspect_ratio)
    image = _apply_enhancements(image, cfg)

    luminance = _luminance_array(image, cfg)
    ramp = cfg.ramp()
    if cfg.invert:
        ramp = ramp[::-1]

    if cfg.color_mode == "color":
        rgb_arr = np.asarray(image, dtype=np.uint8)
        palette = _ANSI_PALETTES.get(cfg.color_palette)
        if palette is not None:
            rgb_arr = _quantize_to_palette(rgb_arr, palette)
        rows = _color_runs_per_row(luminance, rgb_arr, ramp)
        if target == "html":
            return _render_color_html(rows)
        return _render_color_micron(rows)
    return _render_mono(luminance, ramp)
