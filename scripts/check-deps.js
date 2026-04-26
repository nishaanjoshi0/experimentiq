/**
 * ExperimentIQ — Dependency checker
 * Runs automatically after `npm install` via the postinstall hook.
 * Checks for Docker and prints install instructions if missing.
 * Does NOT block the install — exits 0 regardless so npm never fails.
 */

const { execSync, spawnSync } = require("child_process");
const os = require("os");

const platform = os.platform(); // darwin | linux | win32

const GREEN  = "\x1b[32m";
const YELLOW = "\x1b[33m";
const BLUE   = "\x1b[34m";
const RESET  = "\x1b[0m";

const ok   = (msg) => console.log(`${GREEN}[✓]${RESET} ${msg}`);
const warn = (msg) => console.log(`${YELLOW}[!]${RESET} ${msg}`);
const log  = (msg) => console.log(`${BLUE}[setup]${RESET} ${msg}`);

function isAvailable(cmd) {
  const result = spawnSync(cmd, ["--version"], { stdio: "ignore" });
  return result.status === 0;
}

function isDaemonRunning() {
  const result = spawnSync("docker", ["info"], { stdio: "ignore" });
  return result.status === 0;
}

function checkDocker() {
  if (!isAvailable("docker")) {
    warn("Docker not found. ExperimentIQ requires Docker to run GrowthBook.");
    warn("");
    if (platform === "darwin") {
      warn("  Install option 1 (Homebrew):  brew install --cask docker");
      warn("  Install option 2 (direct):    https://docs.docker.com/desktop/install/mac-install/");
    } else if (platform === "linux") {
      warn("  Install guide: https://docs.docker.com/engine/install/");
      warn("  Quick install: curl -fsSL https://get.docker.com | sh");
    } else if (platform === "win32") {
      warn("  Install Docker Desktop for Windows: https://docs.docker.com/desktop/install/windows-install/");
    }
    warn("");
    warn("  After installing Docker, run:  docker compose up -d  from the project root.");
    return;
  }

  ok(`Docker found: ${execSync("docker --version").toString().trim()}`);

  if (!isDaemonRunning()) {
    warn("Docker is installed but the daemon is not running.");
    if (platform === "darwin") {
      warn("  Open Docker Desktop from your Applications folder, then run: docker compose up -d");
    } else {
      warn("  Start Docker with: sudo systemctl start docker");
    }
    return;
  }

  ok("Docker daemon is running.");
}

console.log("");
log("Checking system dependencies...");
checkDocker();
console.log("");

// Always exit 0 — never block npm install
process.exit(0);
