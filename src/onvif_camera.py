"""Cattura uno snapshot JPEG dalla telecamera ONVIF, con fallback RTSP via OpenCV.

Le import di onvif-zeep e opencv sono volutamente lazy (dentro le funzioni):
sono librerie pesanti e non servono, ad esempio, a chi usa solo la Web UI
per modificare i parametri ASCII su un'immagine caricata a mano.
"""
from __future__ import annotations

import logging

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .config import CameraConfig

logger = logging.getLogger(__name__)


class CameraError(Exception):
    """Errore nel recupero dello snapshot dalla telecamera."""


def _onvif_media_service(camera: CameraConfig):
    from onvif import ONVIFCamera

    cam = ONVIFCamera(camera.ip, camera.port, camera.user, camera.password, camera.resolved_wsdl_dir())
    return cam, cam.create_media_service()


def _profile_token(profile) -> str:
    # A seconda della versione di onvif-zeep/zeep, il token del profilo
    # può comparire come attributo "token" o "_token".
    token = getattr(profile, "token", None) or getattr(profile, "_token", None)
    if not token:
        raise CameraError("Impossibile determinare il token del profilo media")
    return token


def _get_snapshot_uri(camera: CameraConfig) -> str:
    _, media = _onvif_media_service(camera)
    profiles = media.GetProfiles()
    if not profiles:
        raise CameraError("La telecamera non espone alcun profilo media ONVIF")
    token = _profile_token(profiles[0])
    resp = media.GetSnapshotUri({"ProfileToken": token})
    uri = getattr(resp, "Uri", None)
    if not uri:
        raise CameraError("GetSnapshotUri non ha restituito un URI valido")
    return uri


def _get_stream_uri(camera: CameraConfig) -> str:
    _, media = _onvif_media_service(camera)
    profiles = media.GetProfiles()
    if not profiles:
        raise CameraError("La telecamera non espone alcun profilo media ONVIF")
    token = _profile_token(profiles[0])

    request = media.create_type("GetStreamUri")
    request.ProfileToken = token
    request.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
    resp = media.GetStreamUri(request)
    uri = getattr(resp, "Uri", None)
    if not uri:
        raise CameraError("GetStreamUri non ha restituito un URI valido")
    return uri


def _download_snapshot(uri: str, camera: CameraConfig) -> bytes:
    attempts = (
        HTTPDigestAuth(camera.user, camera.password),
        HTTPBasicAuth(camera.user, camera.password),
        None,
    )
    last_error: Exception | None = None
    for auth in attempts:
        try:
            resp = requests.get(uri, auth=auth, timeout=10)
            if resp.status_code == 200 and resp.content:
                return resp.content
            last_error = CameraError(f"HTTP {resp.status_code} da {uri}")
        except requests.RequestException as exc:
            last_error = exc
            logger.debug("Download snapshot fallito con auth=%s: %s", auth, exc)
    raise CameraError(f"Impossibile scaricare lo snapshot da {uri}: {last_error}")


def _capture_rtsp_frame(camera: CameraConfig) -> bytes:
    import cv2

    rtsp_url = _get_stream_uri(camera)
    if camera.user and "@" not in rtsp_url:
        scheme, rest = rtsp_url.split("://", 1)
        rtsp_url = f"{scheme}://{camera.user}:{camera.password}@{rest}"

    capture = cv2.VideoCapture(rtsp_url)
    try:
        if not capture.isOpened():
            raise CameraError(f"Impossibile aprire lo stream RTSP: {rtsp_url}")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraError("Nessun frame ricevuto dallo stream RTSP")
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            raise CameraError("Impossibile codificare il frame catturato in JPEG")
        return buffer.tobytes()
    finally:
        capture.release()


def get_snapshot_jpeg(camera: CameraConfig) -> bytes:
    """Ritorna i byte di uno snapshot JPEG dalla telecamera, secondo il metodo configurato.

    Se il metodo e' "onvif" ma lo snapshot fallisce (camera che non lo supporta
    bene), tenta automaticamente il fallback RTSP prima di arrendersi.
    """
    if camera.capture_method == "rtsp":
        return _capture_rtsp_frame(camera)

    try:
        uri = _get_snapshot_uri(camera)
        return _download_snapshot(uri, camera)
    except CameraError as exc:
        logger.warning("Snapshot ONVIF fallito (%s), provo fallback RTSP", exc)
        return _capture_rtsp_frame(camera)
