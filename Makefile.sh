cat > Makefile << 'EOF'
.PHONY: setup install test lint clean

# Install project in development mode
setup:
	python -m venv venv
	. venv/bin/activate && pip install -e .

# Install all dependencies
install:
	pip install -r requirements/base.txt
	pip install -r requirements/dev.txt
	pre-commit install

# Run tests
test:
	pytest tests/ -v --cov=src

# Code quality
lint:
	black src/ tests/
	isort src/ tests/
	flake8 src/ tests/

# Clean temporary files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov
EOF