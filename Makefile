# Every target uses the project's virtualenv if it exists (run `make setup` once).
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python 3.12 .venv && uv pip install -r requirements-dev.txt; \
	elif command -v python3.12 >/dev/null 2>&1; then \
		python3.12 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; \
	elif command -v python3.11 >/dev/null 2>&1; then \
		python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; \
	elif command -v python3.10 >/dev/null 2>&1; then \
		python3.10 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; \
	else \
		python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; \
	fi
	@echo "done: run 'make check'"

check: lint test repo-check

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff check . --fix

test:
	$(PY) -m pytest -q -p no:warnings

repo-check:
	$(PY) tools/check_repo.py

check-api:
	$(PY) tools/check_openai.py

bench-sim:
	$(PY) -m bench.run --clips dev --simulate

gen:
	$(PY) -m bench.generate

audio-dev:
	$(PY) tools/make_audio.py --split dev

index-recordings:
	$(PY) tools/make_audio.py --split test --recordings

bench-dev:
	$(PY) -m bench.run --clips dev

bench-test-FINAL-ONCE:
	$(PY) -m bench.run --clips test_real

serve:
	$(PY) -m uvicorn app.server:app --reload --port 8000

.PHONY: setup check lint fmt test repo-check check-api bench-sim gen audio-dev index-recordings bench-dev bench-test-FINAL-ONCE serve
