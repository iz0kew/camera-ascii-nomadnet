"""Cattura uno snapshot JPEG dalla telecamera, con supporto multi-protocollo:

- ``onvif``: standard ONVIF (GetSnapshotUri), con fallback RTSP via GetStreamUri.
- ``dahua``: CGI HTTP proprietario Dahua (snapshot.cgi), con fallback RTSP
  sullo stream ``realmonitor`` (compatibile anche con molti brand OEM Dahua,
  es. Amcrest, alcuni Foscam).
- ``reolink``: API HTTP proprietaria Reolink (api.cgi?cmd=Snap), con fallback
  RTSP sullo stream ``h264Preview``.
- ``rtsp``: nessuna scoperta automatica, si usa direttamente l'URL RTSP
  inserito in configurazione (utile per telecamere generiche "solo RTSP").

Le import di onvif-zeep e opencv sono volutamente lazy (dentro le funzioni):
sono librerie pesanti e non servono, ad esempio, a chi usa solo la Web UI
per modificare i parametri ASCII su un'immagine caricata a mano.
"""
from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .config import CameraConfig

logger = logging.getLogger(__name__)


class CameraError(Exception):
    """Errore nel recupero dello snapshot dalla telecamera."""


# --------------------------------------------------------------------------
# Helper condivisi tra protocolli
# --------------------------------------------------------------------------


def _redact_credentials(url: str) -> str:
    """Rimuove eventuali credenziali da un URL, per non finire nei log/errori."""
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    _, host_part = rest.split("@", 1)
    return f"{scheme}://***:***@{host_part}"


def _with_credentials(url: str, user: str, password: str) -> str:
    """Inietta user/password in un URL (es. RTSP) se non gia' presenti."""
    if not user or "@" in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{rest}"


def _download_snapshot(uri: str, camera: CameraConfig) -> bytes:
    """Scarica uno snapshot HTTP provando, in ordine, autenticazione Digest,
    Basic e nessuna autenticazione (alcune telecamere/CGI la richiedono
    esplicitamente, altre falliscono se ne viene inviata una)."""
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
            last_error = CameraError(f"HTTP {resp.status_code} da {_redact_credentials(uri)}")
        except requests.RequestException as exc:
            last_error = exc
            logger.debug("Download snapshot fallito con auth=%s: %s", auth, exc)
    raise CameraError(f"Impossibile scaricare lo snapshot da {_redact_credentials(uri)}: {last_error}")


def _capture_rtsp_frame_from_url(rtsp_url: str) -> bytes:
    import os

    import cv2

    # Il backend ffmpeg di OpenCV usa di default il trasporto RTSP via UDP:
    # con molte telecamere Dahua/Hikvision dietro NAT o firewall i pacchetti
    # RTP via UDP vengono droppati e lo stream non si apre mai (isOpened()
    # resta False dopo un lungo timeout). Forzare TCP risolve la stragrande
    # maggioranza di questi casi; stimeout abbassa anche il timeout di
    # connessione (in microsecondi) cosi' un errore vero fallisce in fretta
    # invece di restare appeso per ~30s.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;10000000"

    capture = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    try:
        if not capture.isOpened():
            raise CameraError(f"Impossibile aprire lo stream RTSP: {_redact_credentials(rtsp_url)}")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraError("Nessun frame ricevuto dallo stream RTSP")
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            raise CameraError("Impossibile codificare il frame catturato in JPEG")
        return buffer.tobytes()
    finally:
        capture.release()


# --------------------------------------------------------------------------
# ONVIF
# --------------------------------------------------------------------------


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


def _capture_onvif_rtsp_frame(camera: CameraConfig) -> bytes:
    rtsp_url = _with_credentials(_get_stream_uri(camera), camera.user, camera.password)
    return _capture_rtsp_frame_from_url(rtsp_url)


# --------------------------------------------------------------------------
# Dahua (e OEM compatibili: Amcrest, alcuni Foscam/Loryta)
# --------------------------------------------------------------------------


def _dahua_snapshot_url(camera: CameraConfig) -> str:
    return f"http://{camera.ip}:{camera.port}/cgi-bin/snapshot.cgi?channel={camera.channel}"


def _dahua_rtsp_url(camera: CameraConfig) -> str:
    subtype = 1 if camera.stream_subtype == "sub" else 0
    url = f"rtsp://{camera.ip}:554/cam/realmonitor?channel={camera.channel}&subtype={subtype}"
    return _with_credentials(url, camera.user, camera.password)


def _capture_dahua_snapshot(camera: CameraConfig) -> bytes:
    return _download_snapshot(_dahua_snapshot_url(camera), camera)


def _capture_dahua_rtsp(camera: CameraConfig) -> bytes:
    return _capture_rtsp_frame_from_url(_dahua_rtsp_url(camera))


# --------------------------------------------------------------------------
# Reolink
# --------------------------------------------------------------------------


def _reolink_snapshot_url(camera: CameraConfig) -> str:
    # L'API Reolink usa canali 0-based, mentre in UI/RTSP si ragiona in
    # canali 1-based (piu' naturale per chi configura una singola camera).
    reolink_channel = max(camera.channel - 1, 0)
    token = secrets.token_hex(4)
    user = quote(camera.user, safe="")
    password = quote(camera.password, safe="")
    return (
        f"http://{camera.ip}:{camera.port}/cgi-bin/api.cgi?cmd=Snap"
        f"&channel={reolink_channel}&rs={token}&user={user}&password={password}"
    )


def _capture_reolink_snapshot(camera: CameraConfig) -> bytes:
    uri = _reolink_snapshot_url(camera)
    try:
        resp = requests.get(uri, timeout=10)
    except requests.RequestException as exc:
        raise CameraError(f"Impossibile scaricare lo snapshot Reolink: {exc}") from exc
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code != 200 or not resp.content or not content_type.startswith("image"):
        # In caso di errore l'API Reolink risponde spesso con JSON (200 OK
        # incluso), quindi il solo status code non basta a distinguere.
        raise CameraError(f"Risposta inattesa dall'API Reolink (HTTP {resp.status_code}, {content_type or 'n/d'})")
    return resp.content


def _reolink_rtsp_url(camera: CameraConfig) -> str:
    stream = "sub" if camera.stream_subtype == "sub" else "main"
    url = f"rtsp://{camera.ip}:554/h264Preview_{camera.channel:02d}_{stream}"
    return _with_credentials(url, camera.user, camera.password)


def _capture_reolink_rtsp(camera: CameraConfig) -> bytes:
    return _capture_rtsp_frame_from_url(_reolink_rtsp_url(camera))


# --------------------------------------------------------------------------
# RTSP diretto (nessuna scoperta: URL inserito manualmente in configurazione)
# --------------------------------------------------------------------------


def _capture_generic_rtsp(camera: CameraConfig) -> bytes:
    if not camera.rtsp_url:
        raise CameraError("Protocollo RTSP diretto: manca l'URL dello stream in configurazione")
    rtsp_url = _with_credentials(camera.rtsp_url, camera.user, camera.password)
    return _capture_rtsp_frame_from_url(rtsp_url)


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

_SNAPSHOT_AND_FALLBACK = {
    "onvif": (lambda camera: _download_snapshot(_get_snapshot_uri(camera), camera), _capture_onvif_rtsp_frame),
    "dahua": (_capture_dahua_snapshot, _capture_dahua_rtsp),
    "reolink": (_capture_reolink_snapshot, _capture_reolink_rtsp),
}

_RTSP_ONLY = {
    "onvif": _capture_onvif_rtsp_frame,
    "dahua": _capture_dahua_rtsp,
    "reolink": _capture_reolink_rtsp,
    "rtsp": _capture_generic_rtsp,
}


def get_snapshot_jpeg(camera: CameraConfig) -> bytes:
    """Ritorna i byte di uno snapshot JPEG dalla telecamera, secondo il
    protocollo (``camera.protocol``) e il metodo (``camera.capture_method``)
    configurati.

    Per i protocolli con scoperta HTTP (onvif/dahua/reolink), se il metodo e'
    "snapshot" ma la cattura fallisce, tenta automaticamente il fallback RTSP
    prima di arrendersi. Il protocollo "rtsp" usa sempre e solo l'URL RTSP
    configurato manualmente, senza alcuna scoperta.
    """
    protocol = camera.protocol or "onvif"

    if protocol == "rtsp":
        return _capture_generic_rtsp(camera)

    if protocol not in _SNAPSHOT_AND_FALLBACK:
        raise CameraError(f"Protocollo camera non supportato: {protocol}")

    snapshot_fn, rtsp_fallback_fn = _SNAPSHOT_AND_FALLBACK[protocol]

    if camera.capture_method == "rtsp":
        return rtsp_fallback_fn(camera)

    try:
        return snapshot_fn(camera)
    except CameraError as exc:
        logger.warning("Snapshot %s fallito (%s), provo fallback RTSP", protocol, exc)
        return rtsp_fallback_fn(camera)
