# Declaración de componentes externos

Todo lo que el prototipo usa y no escribimos nosotros. Versiones tomadas del
entorno con el que se ejecutaron las pruebas y la demostración.

## 1. Modelos de IA

| Componente | Versión | Uso | Dónde se ejecuta | Licencia |
|---|---|---|---|---|
| `BAAI/bge-m3` | descargado de Hugging Face Hub | embeddings multilingües de 1024 dimensiones para los 3.292 documentos semánticos y para cada consulta | **local**, en la máquina de la demostración (CPU o GPU Apple/CUDA) | MIT |

- Se descarga una vez (~2,3 GB) y después el sistema funciona **sin Internet**.
- No hay ninguna llamada a APIs de modelos de pago. No se usa OpenAI, Anthropic,
  Gemini ni ningún servicio de inferencia remoto en tiempo de ejecución.
- Alternativa documentada si falta memoria: `intfloat/multilingual-e5-small`
  (384d, MIT). Cambiar de modelo obliga a regenerar el índice completo.

## 2. Adaptador de LLM

Existe el punto de extensión (`src/knowledge_nexus_retrieval/llm/provider.py`)
pero **está desactivado**: `KNOWLEDGE_NEXUS_LLM_PROVIDER=template` es el valor por
defecto y la redacción es determinista.

Si algún día se conecta un proveedor, la salida se valida contra el paquete de
evidencia y se descarta si cita identificadores inexistentes. La recuperación, el
ranking y la evidencia no dependen del LLM.

## 3. Bibliotecas y frameworks

| Componente | Versión | Uso | Licencia |
|---|---|---|---|
| Python | 3.13 (requiere ≥ 3.11) | lenguaje | PSF |
| `sentence-transformers` | 6.0.0 | carga y ejecución del modelo de embeddings | Apache-2.0 |
| `torch` | 2.13.0 | motor de inferencia del modelo | BSD-3 |
| `transformers` | 5.16.1 | tokenizador y arquitectura del modelo | Apache-2.0 |
| `numpy` | 2.5.2 | índice vectorial en memoria y álgebra | BSD-3 |
| `fastapi` | 0.141.1 | API HTTP y OpenAPI | MIT |
| `pydantic` | 2.13.4 | validación del contrato de entrada y salida | MIT |
| `uvicorn` | 0.52.4 | servidor ASGI | BSD-3 |
| `PyYAML` | 6.0.3 | carga de la configuración versionada | MIT |
| `neo4j` (driver oficial) | 6.2.0 | acceso a Aura cuando el backend de grafo es `neo4j` | Apache-2.0 |
| `streamlit` | 1.62.0 | interfaz de demostración | Apache-2.0 |
| `pandas` | 3.0.5 | tablas de la interfaz | BSD-3 |
| `pytest` | 9.1.1 | pruebas | MIT |
| `httpx` | 0.28.1 | cliente de pruebas de la API | BSD-3 |
| `vis-network` | standalone (CDN) | dibujo del subgrafo en el navegador | Apache-2.0 / MIT |

`vis-network` es el único recurso que la interfaz carga desde Internet
(`unpkg.com`). Sin conexión, la aplicación sigue funcionando: solo el lienzo del
grafo queda vacío, y las mismas relaciones se pueden leer en la tabla que hay
justo debajo.

BM25, el ranking, el ensamblado de evidencia y el generador de oportunidades son
**implementación propia**, no bibliotecas de terceros.

## 4. Servicios en la nube

| Servicio | Uso | Estado |
|---|---|---|
| Neo4j Aura | almacén del grafo e índice vectorial | **opcional**: el prototipo se demuestra con los JSONL locales. Se activa con `KNOWLEDGE_NEXUS_GRAPH_BACKEND=neo4j` |
| Hugging Face Hub | descarga inicial del modelo | solo la primera vez |

No se despliega nada en la nube para la demostración. No se envía ningún dato del
dataset a servicios externos.

## 5. Datos

| Recurso | Origen | Uso |
|---|---|---|
| Data V1.0 RC2 (participantes) | entregado por la organización | única fuente de verdad; se lee, nunca se escribe |
| `team_fixture_search_response.json`, `team_fixture_graph.json` | producidos por el equipo | contrato de desarrollo de la interfaz |

No se incorporaron datasets complementarios, corpus externos ni datos scrapeados.

## 6. Herramientas generativas usadas en el desarrollo

Para transparencia, y porque la convocatoria lo pide explícitamente:

| Herramienta | Para qué se usó |
|---|---|
| Claude (Anthropic), vía Claude Code | escritura del motor de recuperación, ranking, evidencia, oportunidades, API, pruebas y documentación; adaptación de la interfaz al contrato real |
| Gemini | primera versión de la interfaz Streamlit (`ui/app_original_persona3.py`) |

El código generado fue revisado, ejecutado y probado por el equipo: las 74
pruebas automatizadas y las métricas de este repositorio se obtuvieron
ejecutando el sistema, no describiéndolo.

## 7. Configuración que no es código

| Archivo | Qué define |
|---|---|
| `config/ranking.yaml` | pesos, calibración del coseno, penalizaciones, umbrales |
| `config/entity_profiles.yaml` | qué campos de cada tipo alimentan cada señal |
| `config/relation_rules.yaml` | etiquetas de relación inferida y reglas de oportunidad |
| `config/lexicon.yaml` | sinónimos, vocabulario metodológico y palabras vacías |

El léxico de sinónimos es una lista escrita por el equipo a partir de términos
observados en Data V1.0. Se puede desactivar entero
(`retrieval.use_lexicon_expansion: false`) y el caso multilingüe sigue
funcionando: hay una prueba que lo demuestra.
