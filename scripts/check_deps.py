"""
ExperimentIQ — Python dependency checker
Run before pip install:  python scripts/check_deps.py && pip install -r backend/requirements.txt

Checks: Docker, Python version, pip
"""

import shutil
import subprocess
import sys
import platform

GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}[✓]{RESET} {msg}")
def warn(msg): print(f"{YELLOW}[!]{RESET} {msg}")
def log(msg):  print(f"{BLUE}[setup]{RESET} {msg}")

OS = platform.system()  # Darwin | Linux | Windows


def check_python_version():
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 11):
        warn(f"Python {major}.{minor} detected — ExperimentIQ requires Python 3.11+.")
        if OS == "Darwin":
            warn("  Install via Homebrew:  brew install python@3.11")
        else:
            warn("  Download from:         https://www.python.org/downloads/")
        sys.exit(1)
    ok(f"Python {major}.{minor} — OK")


def daemon_running():
    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_docker():
    if shutil.which("docker") is None:
        warn("Docker not found. ExperimentIQ requires Docker to run GrowthBook.\n")
        if OS == "Darwin":
            warn("  Install option 1 (Homebrew):  brew install --cask docker")
            warn("  Install option 2 (direct):    https://docs.docker.com/desktop/install/mac-install/")
        elif OS == "Linux":
            warn("  Quick install:  curl -fsSL https://get.docker.com | sh")
            warn("  Full guide:     https://docs.docker.com/engine/install/")
        elif OS == "Windows":
            warn("  Docker Desktop: https://docs.docker.com/desktop/install/windows-install/")
        warn("\n  After installing, run:  docker compose up -d  from the project root.")
        return

    version = subprocess.check_output(["docker", "--version"]).decode().strip()
    ok(f"{version}")

    if not daemon_running():
        warn("Docker is installed but the daemon is not running.")
        if OS == "Darwin":
            warn("  Open Docker Desktop, then run:  docker compose up -d")
        else:
            warn("  Start with:  sudo systemctl start docker")
        return

    ok("Docker daemon is running.")


if __name__ == "__main__":
    print()
    log("Checking system dependencies...\n")
    check_python_version()
    check_docker()
    print()
    ok("All checks passed. Run:  pip install -r backend/requirements.txt")
    print()
