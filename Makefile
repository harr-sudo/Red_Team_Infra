SHELL := /bin/bash

.PHONY: help dev install-dev test test-backend test-js test-browser test-browser-headed test-fast refresh-cs-spec

help:
	@echo "Red Team Infrastructure — test framework targets"
	@echo ""
	@echo "  make dev                  Start Flask dev server on port 5050 (foreground)"
	@echo "  make install-dev          Install Python + Node dev dependencies"
	@echo "  make test                 Run all test layers (backend + js + browser)"
	@echo "  make test-backend         Run pytest (Flask + CS contract)"
	@echo "  make test-js              Run Vitest (frontend JS unit tests)"
	@echo "  make test-browser         Run Playwright browser tests (headless)"
	@echo "  make test-browser-headed  Run Playwright browser tests (headed)"
	@echo "  make test-fast            Run backend + js only (skip browser layer)"
	@echo "  make refresh-cs-spec      Regenerate Cobalt Strike OpenAPI spec.json (T0.2)"

dev:
	source venv/bin/activate && PYTHONPATH=. python3 -m flask --app webapp.backend.app run --debug --port 5050 --host 127.0.0.1

install-dev:
	pip install -r requirements-dev.txt && npm install

test: test-backend test-js test-browser

test-backend:
	@source venv/bin/activate && PYTHONPATH=. python3 -m pytest tests/backend tests/cs_contract -v; \
		status=$$?; \
		if [ $$status -eq 5 ]; then echo "(no tests collected — treating as success)"; exit 0; fi; \
		exit $$status

test-js:
	npm run test:js -- --passWithNoTests

test-browser:
	npm run test:browser

test-browser-headed:
	npm run test:browser:headed

test-fast: test-backend test-js

refresh-cs-spec:
	@echo "T0.2 not yet implemented"
