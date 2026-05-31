cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg-info/
dist/
build/
*.egg

# Virtual environments
venv/
env/
.venv/
.conda/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Jupyter
.ipynb_checkpoints/
*.ipynb_checkpoints

# Data and results (حجم بالا دارن)
data/raw/*
data/processed/*
!data/raw/.gitkeep
!data/processed/train/.gitkeep
!data/processed/val/.gitkeep
!data/processed/test/.gitkeep

# Models and checkpoints
results/checkpoints/*
results/logs/*
results/predictions/*
!results/checkpoints/.gitkeep
!results/logs/.gitkeep
!results/predictions/.gitkeep

# Environment
.env
.env.local
wandb/

# OS
.DS_Store
Thumbs.db

# Docker
.docker/

# Mypy
.mypy_cache/
EOF