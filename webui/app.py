"""Piccola Web UI locale per impostare i parametri della camera e dell'ASCII
art, con anteprima live in stile asciiart.eu.

Uso:
    python webui/app.py
poi apri http://127.0.0.1:5000 nel browser. Pensata per essere usata solo
in locale/LAN durante la configurazione, non per essere esposta su internet.
"""
from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ascii_converter import image_to_ascii  # noqa: E402
from src.config import (  # noqa: E402
    AsciiConfig,
    CameraConfig,
    load_settings,
    save_ascii_config,
    save_camera_config,
)
from src.onvif_camera import CameraError, get_snapshot_jpeg  # noqa: E402

app = Flask(__name__)


def _ascii_config_from_form(form) -> AsciiConfig:
    return AsciiConfig(
        width=int(form.get("width") or 100),
        char_aspect_ratio=float(form.get("char_aspect_ratio") or 2.0),
        ramp_preset=form.get("ramp_preset", "standard"),
        custom_ramp=form.get("custom_ramp", ""),
        brightness=float(form.get("brightness") or 1.0),
        contrast=float(form.get("contrast") or 1.0),
        gamma=float(form.get("gamma") or 1.0),
        invert=form.get("invert") in ("on", "true", "1"),
        edge_detect=form.get("edge_detect") in ("on", "true", "1"),
        edge_mix=float(form.get("edge_mix") or 0.5),
        color_mode=form.get("color_mode", "mono"),
    )


def _camera_config_from_form(form) -> CameraConfig:
    return CameraConfig(
        ip=form.get("ip", ""),
        port=int(form.get("port") or 80),
        user=form.get("user", ""),
        password=form.get("password", ""),
        wsdl_dir=form.get("wsdl_dir", ""),
        capture_method=form.get("capture_method", "onvif"),
        snapshot_interval_seconds=int(form.get("snapshot_interval_seconds") or 60),
        cache_dir=form.get("cache_dir", "cache"),
    )


@app.route("/")
def index():
    settings = load_settings()
    return render_template(
        "config.html",
        camera=settings.camera,
        ascii_cfg=settings.ascii,
        saved=request.args.get("saved") == "1",
    )


@app.route("/save", methods=["POST"])
def save():
    save_camera_config(_camera_config_from_form(request.form))
    save_ascii_config(_ascii_config_from_form(request.form))
    return redirect(url_for("index", saved="1"))


@app.route("/preview", methods=["POST"])
def preview():
    ascii_cfg = _ascii_config_from_form(request.form)

    upload = request.files.get("image")
    if upload and upload.filename:
        jpeg_bytes = upload.read()
    elif request.form.get("source") == "camera":
        camera = _camera_config_from_form(request.form)
        try:
            jpeg_bytes = get_snapshot_jpeg(camera)
        except CameraError as exc:
            return jsonify({"error": str(exc)}), 400
    else:
        return jsonify({"error": "Carica un'immagine oppure usa \"Cattura dalla camera\"."}), 400

    try:
        # target="html": nel browser i tag colore Micron (`Fxxx...`f) non
        # verrebbero interpretati e comparirebbero come testo grezzo mischiato
        # all'ascii art; per l'anteprima serve un rendering HTML equivalente.
        ascii_art = image_to_ascii(jpeg_bytes, ascii_cfg, target="html")
    except Exception as exc:  # immagine non valida, parametri incoerenti, ecc.
        return jsonify({"error": f"Conversione fallita: {exc}"}), 400

    return jsonify({"ascii": ascii_art, "is_html": ascii_cfg.color_mode == "color"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
