"""Wbudowane szablony .gitignore (dodatkowe pobierane są z GitHuba)."""

TEMPLATES: dict[str, str] = {
    "Windows / ogólne": """# Windows
Thumbs.db
ehthumbs.db
Desktop.ini
$RECYCLE.BIN/
*.lnk
# Pliki tymczasowe
*.tmp
*.temp
*.bak
*.swp
~$*
""",
    "Python": """# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/
env/
.pytest_cache/
.mypy_cache/
.ipynb_checkpoints/
*.spec
""",
    "Visual Studio / C#": """# Visual Studio
.vs/
bin/
obj/
*.user
*.suo
*.userosscache
*.sln.docstates
packages/
TestResults/
""",
    "VS Code / JetBrains": """# Edytory
.vscode/*
!.vscode/settings.json
!.vscode/extensions.json
.idea/
*.iml
""",
    "Node.js": """# Node
node_modules/
npm-debug.log*
yarn-error.log*
.env
dist/
""",
    "Siemens TIA Portal": """# TIA Portal – katalogi generowane / tymczasowe
Logs/
TMP/
XRef/
*.~*
*.bak
# Projekty TIA są binarne – rozważ wersjonowanie eksportów
# (np. SIMATIC VCI / Openness) lub archiwów *.zapXX zamiast całego projektu.
""",
    "Mitsubishi GX Works": """# GX Works – pliki tymczasowe i kopie zapasowe
*.bak
*.tmp
*.log
~*
""",
    "Office": """# Pliki blokad Office
~$*
*.~lock.*
""",
}
