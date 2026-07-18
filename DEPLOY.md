# Guida al deploy su un nodo Reticulum / NomadNet

Questa guida spiega come far girare questo progetto su una macchina che fa
da nodo NomadNet reale (tipicamente Linux, anche un Raspberry Pi): cosa
copiare, cosa installare, come avviare i processi e come gestire la
cache nel tempo.

## 1. Prerequisiti

- Una macchina Linux (o macOS) con Python 3.10+ dove far girare **Reticulum**
  (`rns`) e **NomadNet** (`nomadnet`). Se non li hai ancora installati:

  ```bash
  pip install rns nomadnet
  ```

- Accesso di rete dalla macchina alla telecamera ONVIF (stessa LAN o VPN).
- `git` per scaricare/aggiornare il progetto.

Questo progetto **non sostituisce** Reticulum/NomadNet: aggiunge una pagina
Micron dinamica a un nodo NomadNet già funzionante.

## 2. Quali file copiare sul nodo (e quali no)

Copia l'intera cartella del repository sulla macchina che ospiterà il nodo
(es. via `git clone` diretto sul nodo, oppure `scp`/`rsync` da qui). Ecco
cosa serve davvero a runtime e cosa puoi escludere:

| Percorso | Serve sul nodo? | Note |
|---|---|---|
| `src/` | **Sì** | Logica di cattura/conversione/scheduler |
| `pages/index.mu` | **Sì** | La pagina Micron da collegare al nodo |
| `vendor/wsdl/` | **Sì** | File WSDL ONVIF: senza questi onvif-zeep non funziona (vedi README) |
| `config/ascii_config.json` | **Sì** | Parametri ASCII correnti |
| `requirements.txt` | **Sì** | Per installare le dipendenze Python |
| `scripts/install_nomadnet_page.sh` | **Sì** | Automatizza il collegamento della pagina |
| `.env.example` | Sì (come modello) | Da copiare in `.env` e compilare **sul nodo stesso** |
| `.env` | **No, non copiarlo da qui** | Va creato/compilato direttamente sul nodo con le credenziali; se lo generi qui e lo trasferisci, trasferisci anche la password in chiaro su un altro canale — meglio ricompilarlo sul posto |
| `webui/` | Opzionale | Serve solo se vuoi poter riconfigurare i parametri da quella stessa macchina via browser. Se configuri tutto da qui e sposti solo `.env`/`ascii_config.json` sul nodo, puoi ometterla |
| `cache/` | Sì, ma vuota | Basta la cartella (con `.gitkeep`); i contenuti (`latest.txt`, `latest_meta.json`) li rigenera da solo lo scheduler al primo avvio |
| `.git/` | **No** | Storia del repository, non serve a runtime (a meno che tu voglia poi fare `git pull` direttamente sul nodo, nel qual caso tienila) |
| `.claude/` | **No** | Configurazione locale dell'ambiente di sviluppo, irrilevante sul nodo |
| `contesto.txt` | No | Appunti iniziali del progetto, non usati dal codice |
| `__pycache__/`, `*.pyc` | No | Rigenerati automaticamente da Python |
| `venv/` / `.venv/` | **No** | Va ricreato sul nodo (architettura/OS possibilmente diversi) |

In pratica, se fai `git clone` direttamente sul nodo (consigliato, così poi
`git pull` per aggiornare), tutto quello che serve escludere è già gestito
da `.gitignore` (`.env`, cache generata, `.claude/`, `venv/`, ecc.).

## 3. Pacchetti da installare sul nodo

Pacchetti di sistema (esempio Debian/Ubuntu/Raspberry Pi OS):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Dipendenze Python del progetto, in un virtualenv dedicato:

```bash
cd plugin_camera_nomadnet
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Note pratiche:

- `opencv-python` (usato solo per il fallback RTSP) è pesante e su
  Raspberry Pi/ARM può non avere un wheel precompilato, richiedendo una
  compilazione lunga. Se non ti serve RTSP (la tua camera risponde bene
  allo snapshot ONVIF), puoi rimuoverlo da `requirements.txt` e non
  installarlo affatto: `_capture_rtsp_frame` in `src/onvif_camera.py` verrà
  chiamata solo se `CAPTURE_METHOD=rtsp` o se lo snapshot ONVIF fallisce.
  In alternativa, su Debian/RPi puoi installare `sudo apt install
  python3-opencv` invece della versione pip.
- Reticulum/NomadNet vanno installati separatamente (vedi punto 1), non
  sono nel `requirements.txt` di questo progetto.

## 4. Configurazione sul nodo

```bash
cp .env.example .env
nano .env   # inserisci CAMERA_IP, CAMERA_USER, CAMERA_PASSWORD, ecc.
```

`config/ascii_config.json` è già incluso con i parametri che hai messo a
punto con la Web UI; non serve ricrearlo, a meno che tu voglia
regolarli anche da quella macchina (in tal caso porta con te anche
`webui/` e lancia `python webui/app.py` in loco).

## 5. Abilitare l'hosting delle pagine in NomadNet

Perché altri nodi possano navigare la tua pagina, NomadNet deve essere
configurato per **ospitare un nodo** (non solo client). Nel file di
configurazione di NomadNet (di norma `~/.nomadnetwork/config`), sezione
`[node]`:

```ini
[node]
enable_node = yes
node_name = La tua camera
announce_at_start = yes
```

Poi avvia NomadNet (se non gira già), ad esempio in modalità headless:

```bash
nomadnet --daemon
```

## 6. Collegare la pagina Micron al nodo

```bash
./scripts/install_nomadnet_page.sh
# oppure, con cartella pages custom:
./scripts/install_nomadnet_page.sh /percorso/pages
```

Lo script crea un symlink eseguibile verso `pages/index.mu` dentro la
cartella `pages` del nodo, così la pagina continua a leggere `cache/` e
`src/config.py` dal repository reale.

## 7. Avviare lo scheduler come servizio persistente

Lo scheduler (`src/scheduler.py`) deve restare sempre attivo, separato dal
nodo NomadNet. Il modo più robusto su Linux è un servizio `systemd` che si
riavvia da solo in caso di crash o reboot. Esempio
`/etc/systemd/system/camera-ascii-scheduler.service`:

```ini
[Unit]
Description=Camera ONVIF -> ASCII scheduler per NomadNet
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<tuo-utente>
WorkingDirectory=/percorso/a/plugin_camera_nomadnet
ExecStart=/percorso/a/plugin_camera_nomadnet/venv/bin/python -m src.scheduler
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Attivazione:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camera-ascii-scheduler.service
sudo systemctl status camera-ascii-scheduler.service
journalctl -u camera-ascii-scheduler.service -f   # log in tempo reale
```

Per una prova rapida senza systemd va bene anche una sessione `screen`/`tmux`
con `python -m src.scheduler` dentro, ma non sopravvive a un riavvio della
macchina.

## 8. Rimuovere le vecchie foto / pulizia automatica

**Con l'impostazione attuale del progetto non serve nessuna pulizia**: lo
scheduler non accumula screenshot. Ad ogni ciclo scrive sempre sugli stessi
due file, sovrascrivendoli in modo atomico (`os.replace`):

- `cache/latest.txt` — l'ultimo ASCII art generato
- `cache/latest_meta.json` — timestamp e ultimo eventuale errore

Nessun file JPEG viene salvato su disco: lo snapshot scaricato dalla camera
resta solo in memoria per il tempo della conversione. Quindi lo spazio
occupato da `cache/` **resta costante nel tempo** e non c'è nulla da
eliminare periodicamente in condizioni normali.

Se in fase di test hai salvato a mano qualche screenshot (come è successo
durante lo sviluppo, con file tipo `cache/_test_snapshot.jpg`), rimuovili
semplicemente con:

```bash
rm -f cache/*.jpg
```

Se in futuro vorrai tenere uno **storico** delle immagini (es. per
timelapse o debug), oggi il progetto non lo prevede: andrebbe aggiunta una
piccola funzione che salva ogni JPEG con un nome a timestamp in una
cartella dedicata (es. `cache/history/`). In quel caso, per evitare che
cresca all'infinito, uno di questi due approcci funziona su qualunque
cartella di questo tipo:

- **Pulizia via cron** (rimuove i file più vecchi di 7 giorni, ogni notte
  alle 3):

  ```bash
  crontab -e
  # aggiungi questa riga:
  0 3 * * * find /percorso/a/plugin_camera_nomadnet/cache/history -type f -mtime +7 -delete
  ```

- **Pulizia via systemd timer**, se preferisci restare coerente con il
  servizio dello scheduler: un piccolo `.service` con `ExecStart=find
  .../cache/history -type f -mtime +7 -delete` abbinato a un `.timer` con
  `OnCalendar=daily`.

Se vuoi che implementi davvero questa funzione di storico + pulizia
automatica nel codice (invece della sola cache "ultimo scatto"), dimmelo:
è un cambiamento mirato a `src/scheduler.py`, non serve toccare il resto.

## 9. Aggiornare il progetto sul nodo

Se hai clonato con `git` direttamente sul nodo:

```bash
cd plugin_camera_nomadnet
git pull
source venv/bin/activate
pip install -r requirements.txt   # nel caso siano cambiate le dipendenze
sudo systemctl restart camera-ascii-scheduler.service
```

## 10. Problemi comuni

- **Timeout di rete verso la camera**: verifica che il nodo e la camera
  siano sulla stessa rete/subnet raggiungibile (`ping <CAMERA_IP>`).
- **`TypeError` all'avvio di `get_snapshot_jpeg`**: mancano i file WSDL —
  assicurati di aver copiato anche `vendor/wsdl/` (vedi punto 2) e che
  `CAMERA_WSDL_DIR` in `.env` sia vuoto (userà quelli vendorizzati) o
  punti a una copia valida.
- **La pagina non appare/non si aggiorna nel client NomadNet**: controlla
  che `pages/index.mu` sia eseguibile (`ls -l`, deve avere `x`) e che lo
  scheduler stia scrivendo `cache/latest.txt` (`journalctl -u
  camera-ascii-scheduler -f`).
- **Sintassi Micron resa in modo inatteso**: vedi la nota nel README — la
  sintassi usata è stata verificata su più fonti pubbliche ma può variare
  leggermente tra versioni; confronta con Guide → Markup nel client.
