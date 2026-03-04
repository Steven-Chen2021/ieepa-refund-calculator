#!/usr/bin/env bash
# setup.sh — IEEPA Refund Calculator — Project Scaffold
# Run from C:\Project\RefundCal using Git Bash or WSL
# Usage: bash setup.sh

set -euo pipefail

# ── Colours ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   IEEPA Refund Calculator — Project Setup Script    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 0. Pre-flight checks ─────────────────────────────────────────────────────
command -v git  >/dev/null 2>&1 || error "git is not installed or not in PATH"
command -v gh   >/dev/null 2>&1 || error "GitHub CLI (gh) is not installed. Install from https://cli.github.com"
gh auth status  >/dev/null 2>&1 || error "Not authenticated with GitHub CLI. Run: gh auth login"

# ── 1. Create directory structure ────────────────────────────────────────────
info "Creating project directories..."

mkdir -p backend/{app/{api/v1/endpoints,core,db,models,schemas,services,ocr,tasks},tests/{unit,integration},scripts,alembic/versions}
mkdir -p frontend/{src/{components/{ui,forms,layout},pages,hooks,store,utils,types,i18n},public}
mkdir -p nginx/certs
mkdir -p data/keys
mkdir -p e2e/tests
mkdir -p ai_specs
mkdir -p .github/workflows

# Secure permissions for the keys directory (Unix-side)
chmod 700 data/keys 2>/dev/null || warn "chmod 700 on data/keys skipped (Windows FS; set manually)"

info "Directory structure created."

# ── 2. Create placeholder files so git tracks empty dirs ─────────────────────
touch backend/app/__init__.py
touch backend/app/main.py
touch backend/app/celery_app.py
touch backend/requirements.txt
touch backend/requirements-dev.txt
touch backend/Dockerfile
touch backend/.env.example

touch frontend/package.json
touch frontend/vite.config.ts
touch frontend/tsconfig.json
touch frontend/Dockerfile
touch frontend/index.html

touch nginx/nginx.conf

# data/keys must NOT be committed — tracked via .gitkeep + .gitignore
touch data/.gitkeep
# data/keys intentionally left out of git (secrets)

touch e2e/.gitkeep
touch ai_specs/.gitkeep

# ── 3. Create .gitignore ─────────────────────────────────────────────────────
info "Writing .gitignore..."

cat > .gitignore << 'GITIGNORE'
# ═══════════════════════════════════════════════════════════
#  .gitignore — IEEPA Refund Calculator
#  Covers: Python · FastAPI · Node.js · React/Vite · Docker
# ═══════════════════════════════════════════════════════════

# ── Secrets & environment variables ─────────────────────────
.env
.env.*
!.env.example          # keep the example template
*.key
*.pem
*.p12
*.pfx
data/keys/

# ── Python ───────────────────────────────────────────────────
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/
eggs/
parts/
var/
sdist/
develop-eggs/
.installed.cfg
lib/
lib64/
*.manifest
*.spec
MANIFEST

# Virtual environments
.venv/
venv/
ENV/
env/
.Python
pip-wheel-metadata/

# pytest / coverage
.pytest_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/
nosetests.xml
*.coveragerc
junit*.xml

# mypy / pyright / ruff
.mypy_cache/
.dmypy.json
dmypy.json
.pyright/
.ruff_cache/

# Bandit
.bandit

# Celery
celerybeat-schedule
celerybeat.pid

# Alembic (keep versions folder, ignore auto-generated env)
backend/alembic/env.pyc

# ── Node.js / npm ────────────────────────────────────────────
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
.yarn/
.pnp.*
package-lock.json.bak

# ── React / Vite ─────────────────────────────────────────────
frontend/dist/
frontend/dist-ssr/
frontend/.vite/
frontend/build/
*.local

# Vitest / testing
frontend/coverage/
frontend/test-results/
playwright-report/
playwright/.cache/
e2e/test-results/
e2e/playwright-report/

# ── TypeScript ───────────────────────────────────────────────
*.tsbuildinfo

# ── Docker ───────────────────────────────────────────────────
# Keep Dockerfile and docker-compose.yml, ignore local overrides
docker-compose.override.yml
docker-compose.local.yml

# ── Data directories (uploaded files, reports — never commit) ─
data/uploads/
data/reports/
data/keys/

# ── Logs ─────────────────────────────────────────────────────
*.log
logs/
*.out

# ── OS & editor artefacts ────────────────────────────────────
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db
Desktop.ini

.idea/
.vscode/
*.swp
*.swo
*~
*.sublime-project
*.sublime-workspace

# ── Google credentials (GCP service account JSON) ────────────
credentials/
*.service-account.json

# ── Misc ─────────────────────────────────────────────────────
*.bak
*.tmp
*.orig
.cache/
.sass-cache/
GITIGNORE

info ".gitignore written."

# ── 4. Copy ai_specs files into project (if they exist alongside) ────────────
if ls ai_specs/*.md >/dev/null 2>&1; then
    info "ai_specs/*.md already present — will be committed."
else
    warn "No .md files found in ai_specs/ — add them before committing specs."
fi

# ── 5. Initialise git repository ────────────────────────────────────────────
info "Initialising git repository..."

git init -b main
git config user.email "$(gh api user --jq '.email // "noreply@dimerco.com"')" 2>/dev/null || true
git config user.name  "$(gh api user --jq '.name  // "Dimerco CIO"')"          2>/dev/null || true

# ── 6. Initial commit ────────────────────────────────────────────────────────
info "Staging files for initial commit..."

git add .
git status --short

git commit -m "chore: project scaffold for IEEPA Refund Calculator

- Created backend, frontend, nginx, data/keys directory structure
- Added comprehensive .gitignore (Python, Node.js, React/Vite, Docker)
- Added ai_specs/ Phase 1–4 specification Markdown files
- Added placeholder source files for backend and frontend

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

info "Initial commit created."

# ── 7. Create GitHub repository and push ────────────────────────────────────
info "Creating private GitHub repository and pushing..."

gh repo create ieepa-refund-calculator \
  --private \
  --source=. \
  --push \
  --description "IEEPA Tariff Refund Calculator — Dimerco Express Group (Internal)"

info "Repository pushed to GitHub."

# ── 8. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                    Setup Complete                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Repository : $(gh repo view ieepa-refund-calculator --json url -q .url 2>/dev/null || echo 'see GitHub')"
echo "  Branch     : main"
echo ""
echo "  Next steps:"
echo "    1. cp backend/.env.example backend/.env   # fill in secrets"
echo "    2. python -c \"from cryptography.fernet import Fernet; open('data/keys/app_secret.key','wb').write(Fernet.generate_key())\""
echo "    3. docker compose up -d"
echo "    4. docker compose exec api alembic upgrade head"
echo ""
warn "IMPORTANT: data/keys/ is gitignored. Back up app_secret.key offline."
echo ""
