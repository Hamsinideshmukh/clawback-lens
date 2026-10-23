.PHONY: setup db up down demo check test eval train seed web

BACKEND := cd backend &&

setup:  ## Install backend (with the C++ extension) and frontend dependencies
	$(BACKEND) pip install -r requirements-dev.txt ../native
	cd frontend && npm ci

db:  ## Start only PostgreSQL
	docker compose up -d db

up:  ## Run the full stack: http://localhost:3000 (UI), http://localhost:8000/docs (API)
	docker compose up --build

down:
	docker compose down

demo:  ## Seed demo disputes through the API (works against any deployment: make demo API=https://...)
	scripts/demo.sh $(or $(API),http://localhost:8000)

check:  ## Everything CI runs, except the slower eval
	$(BACKEND) ruff check . && ruff format --check . && mypy app && pytest
	cd frontend && npm run lint && npm run typecheck && npm test

test:
	$(BACKEND) pytest

eval:  ## End-to-end document AI evaluation with quality gates
	$(BACKEND) python -m evals.run_eval --per-type 10

train:  ## Retrain and export the ONNX models (deterministic)
	$(BACKEND) python -m training.train

seed:  ## Demo cases and sample scans
	$(BACKEND) alembic upgrade head && python -m scripts.seed

web:
	cd frontend && npm run dev
