.PHONY: help install embeddings api ui test evaluate demo search clean

VENV := .venv
PY := $(VENV)/bin/python
Q ?= ¿Qué nueva investigación puede ayudar a prevenir la deserción estudiantil?

help:
	@echo "Knowledge Nexus LATAM"
	@echo "  make install     Crea el entorno e instala dependencias"
	@echo "  make embeddings  Genera o reanuda los embeddings semánticos"
	@echo "  make api         Levanta la API en el puerto 8000"
	@echo "  make ui          Levanta la interfaz en el puerto 8501"
	@echo "  make test        Ejecuta las pruebas"
	@echo "  make evaluate    Mide el conjunto de revisión manual"
	@echo "  make demo        Regenera los casos demostrables"
	@echo '  make search Q="tu pregunta"'

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install -e .

embeddings:
	$(VENV)/bin/knowledge-nexus embeddings

api:
	$(VENV)/bin/knowledge-nexus serve --port 8000

ui:
	$(VENV)/bin/streamlit run ui/app.py --server.port 8501

test:
	$(PY) -m pytest -q

evaluate:
	$(VENV)/bin/knowledge-nexus evaluate > artifacts/evaluation/last_report.json
	@$(PY) -c "import json;d=json.load(open('artifacts/evaluation/last_report.json'));print(json.dumps(d['summary'],ensure_ascii=False,indent=2))"

demo:
	$(PY) scripts/build_demo_cases.py

search:
	$(VENV)/bin/knowledge-nexus search "$(Q)" --limit 5

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
