# Camera ONVIF → ASCII Art per NomadNet

![Repo pubblico](https://img.shields.io/badge/repo-public-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)

Pagina dinamica per un nodo [NomadNet](https://github.com/markqvist/NomadNet) (rete
[Reticulum](https://reticulum.network/)) che mostra l'ultimo screenshot di una
telecamera di rete ONVIF, convertito in ASCII art e renderizzato in Micron.

> Per installare e far girare questo progetto su un nodo Reticulum/NomadNet
> reale (file da copiare/escludere, pacchetti di sistema, servizi systemd,
> gestione della cache) vedi la **[guida al deploy](DEPLOY.md)**.

## Come funziona

Il progetto è diviso in tre parti indipendenti:

1. **`src/scheduler.py`** — processo di lunga durata: ogni `SNAPSHOT_INTERVAL_SECONDS`
   si collega alla camera via ONVIF (fallback RTSP se necessario), scarica uno
   snapshot e lo scrive in `cache/latest.jpg` (+ `cache/latest_meta.json` con
   timestamp/errori).
2. **`pages/index.mu`** — script Python eseguibile, installato nella cartella
   `pages` di un nodo NomadNet. Ad ogni richiesta legge solo il JPEG già in
   cache (non si collega mai direttamente alla camera, resta veloce) e lo
   converte al volo in ASCII art nella modalità colore scelta dall'utente
   tramite i link "Mono"/"A colori" in fondo alla pagina stessa.
3. **`webui/app.py`** — piccola interfaccia web locale (Flask), in stile
   [asciiart.eu](https://www.asciiart.eu/image-to-ascii), per impostare i
   parametri di camera e conversione con anteprima live.

```
plugin_camera_nomadnet/
├── .env.example        # copia in .env e compila con i tuoi dati
├── config/ascii_config.json
├── src/                # config, onvif_camera, ascii_converter, scheduler
├── pages/index.mu       # pagina Micron dinamica
├── webui/               # form di configurazione + anteprima live
├── cache/               # generata a runtime, non versionata
└── scripts/install_nomadnet_page.sh
```

## Installazione

Richiede Python 3.10+.

```bash
python -m venv venv
source venv/bin/activate          # su Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # poi modifica .env con i tuoi dati
```

`opencv-python` (usato solo per il fallback RTSP) è una dipendenza pesante:
se la tua camera funziona bene con il semplice snapshot ONVIF puoi rimuoverla
da `requirements.txt` e da `src/onvif_camera.py` (funzione `_capture_rtsp_frame`).

> **Nota**: la cartella `vendor/wsdl/` contiene una copia dei file WSDL ONVIF
> necessari a `onvif-zeep`. È vendorizzata volutamente nel repository perché
> il pacchetto pubblicato su PyPI non li installa correttamente di default
> (percorso rotto): senza questa copia ogni chiamata ONVIF fallisce subito
> con un `TypeError` prima ancora di contattare la camera.

## Configurazione

Compila `.env` (vedi `.env.example`):

- `CAMERA_IP`, `CAMERA_PORT`, `CAMERA_USER`, `CAMERA_PASSWORD` — dati della camera.
- `CAPTURE_METHOD` — `onvif` (consigliato) oppure `rtsp`.
- `SNAPSHOT_INTERVAL_SECONDS` — ogni quanti secondi catturare un nuovo frame.
- `CACHE_DIR` — dove scrivere l'ultima ascii art (default `cache/`).

I parametri di conversione ASCII (larghezza, rampa di caratteri,
luminosità/contrasto/gamma, inversione, edge detection, modalità colore) sono
in `config/ascii_config.json` — modificabili a mano o dalla Web UI.

### Modalità colore: mono vs. color

Reticulum è pensato anche per interfacce a bassissima banda (LoRa). Con
`color_mode=color` ogni gruppo di caratteri dello stesso colore viene avvolto
in tag Micron `` `Fxxx...`f ``, che appesantiscono parecchio la pagina.
**Scegli in base all'interfaccia che il tuo nodo NomadNet userà per servire
questa pagina**: `mono` su LoRa/reti lente, `color` va bene su interfacce
TCP/veloci.

Il valore in `config/ascii_config.json` (cambiabile in ogni momento dalla Web
UI) è solo il **default**: la pagina Micron reale (`pages/index.mu`) mostra
anche due link "Mono" / "A colori" in fondo, che permettono di scegliere la
modalità ad ogni richiesta, direttamente dal client NomadNet, senza dover
passare dalla Web UI.

## Avvio

Avvia lo scheduler (processo separato, sempre attivo):

```bash
python -m src.scheduler
```

Avvia la Web UI di configurazione (solo in locale/LAN):

```bash
python webui/app.py
# poi apri http://127.0.0.1:5000
```

## Installare la pagina su un nodo NomadNet

Su Linux/macOS dove gira il nodo NomadNet:

```bash
./scripts/install_nomadnet_page.sh                     # usa ~/.nomadnetwork/storage/pages
./scripts/install_nomadnet_page.sh /percorso/pages      # oppure una cartella custom
```

Lo script crea un **symlink** eseguibile verso `pages/index.mu`, così la
pagina continua a leggere `cache/` e `src/config.py` dal repository reale.
Se il tuo nodo NomadNet gira su un'altra macchina rispetto a questo progetto,
copia l'intera cartella del repository su quella macchina prima di lanciare
lo script.

> **Nota sulla sintassi Micron**: le intestazioni (`>`), il blocco letterale
> (`` `= `` ... `` `= ``, usato per mostrare l'ASCII art senza che i suoi
> caratteri vengano interpretati come markup) e i link (`` `[testo`:percorso] ``)
> usati in `pages/index.mu` sono stati verificati su più fonti pubbliche, ma
> la sintassi esatta può variare leggermente tra versioni di NomadNet. Se il
> rendering non è quello atteso, confronta con la guida integrata del client
> (tab **Guide → Markup**) e correggi `pages/index.mu` di conseguenza.

## Sviluppo / test senza una camera reale

`webui/app.py` permette di caricare un'immagine a mano ("Anteprima da
immagine locale") per testare tutti i parametri di conversione ASCII senza
bisogno di una camera ONVIF collegata.

## Repository GitHub

Il progetto è pubblicato su:

https://github.com/iz0kew/camera-ascii-nomadnet

## Licenza

MIT — vedi [LICENSE](LICENSE).
