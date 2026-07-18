#!/usr/bin/env bash
# Collega pages/index.mu alla cartella "pages" di un nodo NomadNet (Linux/macOS).
#
# Uso:
#   ./scripts/install_nomadnet_page.sh [percorso_cartella_pages]
#
# Se non specificato, usa il percorso di default di NomadNet:
#   ~/.nomadnetwork/storage/pages
#
# Crea un SYMLINK (non una copia): cosi' index.mu continua a leggere gli
# altri file del progetto (src/config.py, cache/) usando percorsi relativi
# al vero percorso del repository, indipendentemente da dove si trova il
# nodo NomadNet.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGES_DIR="${1:-$HOME/.nomadnetwork/storage/pages}"

mkdir -p "$PAGES_DIR"
chmod +x "$REPO_DIR/pages/index.mu"

TARGET="$PAGES_DIR/index.mu"
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
  echo "Attenzione: $TARGET esiste gia' e non e' un symlink. Rimuovilo o scegli un'altra cartella." >&2
  exit 1
fi

ln -sf "$REPO_DIR/pages/index.mu" "$TARGET"
echo "Pagina installata: $TARGET -> $REPO_DIR/pages/index.mu"
echo "Ricorda di avviare lo scheduler separatamente: python -m src.scheduler"
