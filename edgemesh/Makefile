SHELL := /bin/bash

.PHONY: coordinator-dev agent-dev ui-dev lint format test

coordinator-dev:
	cd coordinator && PYTHONPATH=app:. uv run --project . python -m coordinator_service.main

agent-dev:
	cd agent && PYTHONPATH=src uv run --project . python main.py

ui-dev:
	npm --prefix ui run dev

lint:
	cd coordinator && PYTHONPATH=app:. uv run --project . ruff check app api db models scheduler tests scripts
	cd agent && PYTHONPATH=src uv run --project . ruff check src tests main.py
	npm --prefix ui run lint

format:
	cd coordinator && PYTHONPATH=app:. uv run --project . ruff format app api db models scheduler tests scripts
	cd agent && PYTHONPATH=src uv run --project . ruff format src tests main.py
	npm --prefix ui run format

test:
	cd coordinator && PYTHONPATH=app:. uv run --project . pytest
	cd agent && PYTHONPATH=src uv run --project . pytest
	npm --prefix ui run test
