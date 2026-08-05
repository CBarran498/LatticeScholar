.PHONY: install dev run test lint check online-smoke

install:
	python3 -m pip install -e .

dev:
	python3 -m pip install -e ".[dev]"

run:
	latticescholar

test:
	pytest -q

lint:
	ruff check .

check: lint test

online-smoke:
	python3 scripts/smoke_online.py

