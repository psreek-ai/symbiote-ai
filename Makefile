.PHONY: help install test lint fmt db-reset run-pipeline run-webhook clean

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #
PYTHON    := python3
PIP       := pip3
SRC_DIR   := src
TEST_DIR  := tests

# ------------------------------------------------------------------ #
# Default target                                                       #
# ------------------------------------------------------------------ #
help:
	@echo ""
	@echo "  Symbiote AI — Makefile targets"
	@echo ""
	@echo "  install       Install all dependencies (editable)"
	@echo "  test          Run the full test suite"
	@echo "  lint          Check code style with ruff"
	@echo "  fmt           Auto-format code with ruff"
	@echo "  db-reset      Delete the local SQLite database"
	@echo "  run-pipeline  Run the full pipeline (dry-run mode)"
	@echo "  run-webhook   Start the inbound email + unsubscribe server"
	@echo "  clean         Remove .pyc files and __pycache__ directories"
	@echo ""

# ------------------------------------------------------------------ #
# Setup                                                                #
# ------------------------------------------------------------------ #
install:
	$(PIP) install -e ".[dev]"

# ------------------------------------------------------------------ #
# Quality                                                              #
# ------------------------------------------------------------------ #
test:
	pytest $(TEST_DIR) -v --tb=short

lint:
	ruff check $(SRC_DIR) $(TEST_DIR)

fmt:
	ruff check --fix $(SRC_DIR) $(TEST_DIR)
	ruff format $(SRC_DIR) $(TEST_DIR)

# ------------------------------------------------------------------ #
# Pipeline operations                                                  #
# ------------------------------------------------------------------ #
run-pipeline:
	@echo "Running pipeline in dry-run mode…"
	$(PYTHON) $(SRC_DIR)/cli.py pipeline --dry-run

run-webhook:
	@echo "Starting webhook server…"
	$(PYTHON) $(SRC_DIR)/cli.py webhook

# ------------------------------------------------------------------ #
# Database                                                             #
# ------------------------------------------------------------------ #
db-reset:
	@echo "Deleting symbiote.db…"
	rm -f symbiote.db
	@echo "Done. Database will be recreated on next run."

# ------------------------------------------------------------------ #
# Housekeeping                                                         #
# ------------------------------------------------------------------ #
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache"  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info"     -exec rm -rf {} + 2>/dev/null || true
