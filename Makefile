# EduMetria — tarefas reproduzíveis. No Windows sem make, use os comandos
# equivalentes documentados no README (python -m edumetria.cli ...).
PY ?= python
export PYTHONPATH := src

.PHONY: setup demo-data analyze analyze-dif test test-statistical test-integration test-r report benchmark recovery api worker dashboard

setup:
	$(PY) -m pip install -r requirements.txt

demo-data:
	$(PY) -m edumetria.cli demo-data --scenario s0
	$(PY) -m edumetria.cli demo-data --scenario s2

analyze:
	$(PY) -m edumetria.cli analyze --scenario s0

analyze-dif:
	$(PY) -m edumetria.cli analyze --scenario s2

report: analyze-dif

test:
	$(PY) -m pytest -q

test-statistical:
	$(PY) -m pytest -q -m statistical

test-integration:
	$(PY) -m pytest -q tests/integration

test-r:
	$(PY) -m pytest -q -m r_parity

benchmark:
	$(PY) -m edumetria.cli benchmark

recovery:
	$(PY) -m edumetria.cli recovery-study --reps 100 --dif-reps 50

api:
	$(PY) -m uvicorn apps.api.main:app --port 8000

worker:
	$(PY) -m edumetria.worker --loop

dashboard:
	$(PY) -m streamlit run apps/dashboard/app.py
