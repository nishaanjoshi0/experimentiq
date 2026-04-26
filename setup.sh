#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────
# ExperimentIQ — Environment Setup
# Checks for and installs: Docker, Node.js, Python 3.11+
# Safe to run multiple times (idempotent)
# ─────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()    { echo -e "${BLUE}[setup]${NC} $1"; }
ok()     { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
error()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

OS="$(uname -s)"

# ── Docker ───────────────────────────────────
install_docker() {
  log "Docker not found. Installing..."

  if [ "$OS" = "Darwin" ]; then
    if command -v brew &>/dev/null; then
      log "Installing Docker Desktop via Homebrew..."
      brew install --cask docker
      log "Launching Docker Desktop..."
      open -a Docker
      log "Waiting for Docker daemon to start (this can take ~30 seconds)..."
      local retries=0
      until docker info &>/dev/null 2>&1; do
        sleep 3
        retries=$((retries + 1))
        if [ $retries -ge 20 ]; then
          warn "Docker daemon didn't start automatically."
          warn "Please open Docker Desktop manually, then re-run this script or run: docker compose up -d"
          return
        fi
      done
      ok "Docker is running."
    else
      warn "Homebrew not found. Install Docker Desktop manually from https://docs.docker.com/desktop/install/mac-install/"
      warn "Then re-run this script."
    fi

  elif [ "$OS" = "Linux" ]; then
    if command -v apt-get &>/dev/null; then
      log "Installing Docker via apt..."
      sudo apt-get update -qq
      sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
      sudo mkdir -p /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
      sudo apt-get update -qq
      sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
      sudo usermod -aG docker "$USER"
      ok "Docker installed. You may need to log out and back in for group permissions to take effect."
    elif command -v yum &>/dev/null; then
      log "Installing Docker via yum..."
      sudo yum install -y -q docker
      sudo systemctl start docker
      sudo systemctl enable docker
      sudo usermod -aG docker "$USER"
      ok "Docker installed."
    else
      warn "Could not detect a supported package manager (apt/yum)."
      warn "Install Docker manually: https://docs.docker.com/engine/install/"
    fi

  elif [[ "$OS" == MINGW* ]] || [[ "$OS" == CYGWIN* ]] || [[ "$OS" == MSYS* ]]; then
    warn "Windows detected. Download and install Docker Desktop from:"
    warn "https://docs.docker.com/desktop/install/windows-install/"
    warn "Then re-run this script."
  else
    warn "Unknown OS. Install Docker manually: https://docs.docker.com/engine/install/"
  fi
}

check_docker() {
  if command -v docker &>/dev/null; then
    ok "Docker found: $(docker --version)"
    if ! docker info &>/dev/null 2>&1; then
      warn "Docker is installed but the daemon isn't running."
      if [ "$OS" = "Darwin" ]; then
        log "Attempting to start Docker Desktop..."
        open -a Docker
        log "Waiting for Docker daemon..."
        local retries=0
        until docker info &>/dev/null 2>&1; do
          sleep 3
          retries=$((retries + 1))
          if [ $retries -ge 20 ]; then
            warn "Docker daemon didn't respond. Open Docker Desktop manually before running 'docker compose up -d'."
            return
          fi
        done
        ok "Docker daemon is running."
      else
        warn "Start Docker with: sudo systemctl start docker"
      fi
    else
      ok "Docker daemon is running."
    fi
  else
    install_docker
  fi
}

# ── Node.js ──────────────────────────────────
check_node() {
  if command -v node &>/dev/null; then
    NODE_VER=$(node -e "process.exit(parseInt(process.version.slice(1)) < 18 ? 1 : 0)" 2>/dev/null && echo "ok" || echo "old")
    if [ "$NODE_VER" = "old" ]; then
      warn "Node.js $(node --version) found but v18+ is required."
      warn "Update via: https://nodejs.org or use nvm: nvm install 18"
    else
      ok "Node.js found: $(node --version)"
    fi
  else
    warn "Node.js not found. Install v18+ from https://nodejs.org or via nvm:"
    warn "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash"
    warn "  nvm install 18"
  fi
}

# ── Python ───────────────────────────────────
check_python() {
  PYTHON_BIN=""
  for bin in python3.11 python3.12 python3.13 python3; do
    if command -v "$bin" &>/dev/null; then
      VER=$("$bin" -c "import sys; print(sys.version_info >= (3,11))")
      if [ "$VER" = "True" ]; then
        PYTHON_BIN="$bin"
        break
      fi
    fi
  done

  if [ -n "$PYTHON_BIN" ]; then
    ok "Python found: $($PYTHON_BIN --version)"
  else
    warn "Python 3.11+ not found."
    if [ "$OS" = "Darwin" ] && command -v brew &>/dev/null; then
      log "Installing Python 3.11 via Homebrew..."
      brew install python@3.11
      ok "Python 3.11 installed."
    else
      warn "Install Python 3.11+ from https://www.python.org/downloads/"
    fi
  fi
}

# ── Main ─────────────────────────────────────
echo ""
echo "  ExperimentIQ — Setup"
echo "  ────────────────────"
echo ""

check_docker
check_node
check_python

echo ""
ok "Dependency check complete."
echo ""
echo "  Next steps:"
echo "  1. cd backend && pip install -r requirements.txt"
echo "  2. cd frontend && npm install"
echo "  3. docker compose up -d   (starts GrowthBook)"
echo "  4. See README.md for .env setup"
echo ""
