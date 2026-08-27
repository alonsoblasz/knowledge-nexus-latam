# Knowledge Nexus LATAM

Motor híbrido que conecta **necesidades institucionales** con la investigación,
las personas, las capacidades y el currículo que ya existen en la universidad, y
que **explica y sustenta cada conexión** hasta el archivo, la fila y el campo que
la respaldan.

> El caso que resume el problema: una necesidad institucional habla de
> «**deserción estudiantil**». El proyecto que mejor la responde nunca usa esa
> palabra: habla de «**student attrition**». Una búsqueda por palabras clave no
> los conecta. Este sistema sí, y muestra por qué.

Los scores expresan **relevancia para la consulta**. No son verdad científica,
probabilidad de éxito ni aprobación institucional. Toda conexión calculada se
marca como `INFERRED` y se distingue visualmente de los hechos registrados.

---

## Puesta en marcha

Requiere **Python 3.11 o superior** (probado en 3.13).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
```

Generar los embeddings (una sola vez; descarga el modelo la primera vez, ~2,3 GB):

```bash
make embeddings
```

Levantar el motor y la interfaz, cada uno en su terminal:

```bash
make api
```

```bash
make ui
```

La interfaz queda en `http://localhost:8501` y la API en `http://localhost:8000`
(documentación interactiva en `/docs`).

### Todos los comandos

| Comando | Qué hace |
|---|---|
| `make embeddings` | genera o reanuda los 3.292 embeddings (~72 s) |
| `make api` | levanta la API en el puerto 8000 |
| `make ui` | levanta la interfaz Streamlit en el 8501 |
| `make test` | ejecuta las 74 pruebas (~15 s, sin red) |
| `make evaluate` | mide el conjunto de revisión y escribe el reporte |
| `make demo` | reconstruye los casos demostrables con salida real |
| `make search Q="tu pregunta"` | consulta desde la terminal |

---

## Arquitectura

**Fuentes → procesamiento → representación → descubrimiento → valoración → resultados.**
El diagrama detallado, con la correspondencia entre cada caja y los módulos que
la implementan, está en **[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)**.

```
data/                       Data V1.0 inmutable (22 CSV + Markdown)
  ↓  validación, normalización, documentos semánticos
artifacts/generated/        3.327 nodos · 6.353 aristas · 3.292 documentos
  ↓  embeddings BGE-M3 (1024d), por lotes y reanudables
artifacts/embeddings/       índice vectorial reproducible
  ↓  recuperación híbrida + ranking de 6 señales + evidencia
src/knowledge_nexus_retrieval/
  ↓  contrato estable
api  (FastAPI)  →  ui  (Streamlit)
```

| Carpeta | Contenido |
|---|---|
| `src/knowledge_nexus_data/` | capa de datos: validación, grafo y contrato de lectura |
| `src/knowledge_nexus_retrieval/` | motor: embeddings, recuperación, ranking, evidencia, oportunidades, API |
| `ui/` | interfaz de demostración en Streamlit |
| `config/` | pesos, perfiles por tipo, reglas de relación y léxico (versionados) |
| `tests/` | 74 pruebas automatizadas |
| `docs/` | arquitectura, ranking, contrato, evidencia y casos |
| `cypher/` | consultas de demostración para Neo4j |

---

## Mecanismo de descubrimiento y priorización

### Descubrimiento: tres canales complementarios

| Canal | Qué aporta | Qué no puede hacer solo |
|---|---|---|
| **Vectorial** (BGE-M3, 1024d) | equivalencia conceptual entre idiomas y sinónimos | distinguir entre cuatro documentos igual de parecidos |
| **Léxico** (BM25 propio) | anclaje literal, término a término, verificable | cruzar «deserción» con «student attrition» |
| **Expansión de grafo** | personas, grupos y producción que ningún texto menciona | saber de qué trata la consulta |

Los tres se deduplican por ID. Cada candidato conserva la traza de por qué canal
entró.

### Priorización: seis señales explicables

```
total = 0.35·semantic + 0.20·domain + 0.15·method
      + 0.10·graph + 0.10·evidence + 0.10·actionable
      − penalizaciones
```

| Señal | Qué mide |
|---|---|
| `semantic` | coseno calibrado del modelo, fusionado con BM25 |
| `domain` | unidad institucional compartida, vocabulario y área declarada |
| `method` | compatibilidad metodológica declarada |
| `graph` | proximidad explícita, conectividad y vecinos compartidos |
| `evidence` | cobertura de campos y procedencia verificable |
| `actionable` | estado, vigencia, personas identificables y recursos |

Penalizaciones: entidad inactiva, evidencia escasa, coincidencia superficial,
dominio incompatible y redundancia.

**Los pesos están en `config/ranking.yaml`, versionados y ajustables sin tocar
código.** La respuesta incluye el desglose completo, los pesos aplicados, las
penalizaciones y la versión del ranking. El detalle de cada cálculo, con un
ejemplo real señal por señal, está en **[docs/RANKING.md](docs/RANKING.md)**.

### Y por qué una conexión **no** aparece

Cada respuesta incluye candidatos descartados con su motivo: quedaron por debajo
del último mostrado, chocaron con la cuota por tipo o fueron penalizados. La
interfaz lo muestra en la pestaña «Por qué otras no».

### Cuándo el sistema admite que no sabe

Si la señal semántica del primer resultado es baja, la respuesta se marca como
**confianza baja** con un aviso explícito, en lugar de presentar coincidencias
débiles como un hallazgo.

---

## Reproducción de la demostración

```bash
make api      # terminal 1
make ui       # terminal 2
```

En la interfaz, la consulta de ejemplo ya viene cargada. Al pulsar **Buscar
conexiones** aparecen cinco pestañas:

1. **Conexiones** — ranking con el desglose de las seis señales, la explicación
   del motor y la evidencia con archivo, fila, campo y fragmento.
2. **Subgrafo** — 11 nodos, con las relaciones explícitas en línea continua y las
   inferidas en discontinua, más la misma información en tabla.
3. **Oportunidades** — propuestas sustentadas, con sus entidades y su
   incertidumbre declarada.
4. **Por qué otras no** — candidatos descartados y el motivo.
5. **Diagnóstico** — latencia, candidatos evaluados y aporte de cada canal.

**El prototipo responde a consultas nuevas**, no a un guion. Prueba con
«¿cómo podemos monitorear la calidad del agua en cuencas con sensores?» o
«detectar fraude en transacciones financieras».

Desde la terminal, sin interfaz:

```bash
make search Q="¿qué capacidades hay para mantenimiento predictivo?"
```

Los casos completos, con salida real del motor, están en
**[docs/CASOS_DEMOSTRABLES.md](docs/CASOS_DEMOSTRABLES.md)** y se regeneran con
`make demo`.

---

## Desempeño

10 casos de revisión en dominios distintos, k = 5:

| Métrica | Valor |
|---|---|
| Precisión@5 (tipos etiquetados) | 0.833 |
| NDCG@5 | 0.662 |
| Cobertura de evidencia | 1.000 |
| Trazabilidad completa (archivo, fila, campo, fragmento) | 1.000 |
| Oportunidades que solo usan IDs existentes | sí |
| Violaciones en pruebas negativas | 0 |
| Latencia mediana / p95 | 165 ms / 256 ms |

Metodología, limitaciones y pruebas negativas en
**[docs/EVIDENCIA_DESEMPENO.md](docs/EVIDENCIA_DESEMPENO.md)**.

---

## Tecnologías

Python 3.13 · BGE-M3 (embeddings multilingües, local) · FastAPI · Pydantic ·
NumPy · Neo4j (opcional) · Streamlit · pytest.

BM25, el ranking, la evidencia y las oportunidades son implementación propia.
**No se usa ninguna API de IA de pago**: el prototipo funciona sin Internet una
vez descargado el modelo. Declaración completa en
**[docs/COMPONENTES_EXTERNOS.md](docs/COMPONENTES_EXTERNOS.md)**.

---

## Configuración

```bash
cp .env.example .env   # y ajusta lo que necesites
```

| Variable | Por defecto | Para qué |
|---|---|---|
| `KNOWLEDGE_NEXUS_GRAPH_BACKEND` | `jsonl` | `jsonl` (local, sin credenciales) o `neo4j` (Aura) |
| `KNOWLEDGE_NEXUS_EMBEDDING_MODEL` | `BAAI/bge-m3` | modelo activo |
| `KNOWLEDGE_NEXUS_EMBEDDING_DIMENSION` | `1024` | dimensión activa |
| `KNOWLEDGE_NEXUS_EMBEDDING_PROVIDER` | `sentence-transformers` | `hashing` para operar sin descargas (solo pruebas) |
| `KNOWLEDGE_NEXUS_API_URL` | `http://localhost:8000` | a qué motor apunta la interfaz |
| `KNOWLEDGE_NEXUS_DATA_SOURCE` | `api` | `api` o `fixture` |

Las credenciales de Neo4j se leen del entorno (`NEO4J_URI`, `NEO4J_USERNAME`,
`NEO4J_PASSWORD`) y **nunca aparecen en el código, en la interfaz ni en los
artefactos**. Hay una prueba que escanea el repositorio buscando secretos.

---

## Limitaciones

Lo que este prototipo **no** hace, dicho antes de que lo pregunten:

- **No valida académicamente nada.** Una oportunidad es una hipótesis con
  evidencia, no una decisión aprobada por la universidad.
- **Las necesidades no tienen relaciones explícitas en Data V1.0.** Su única
  arista es hacia su documento. Toda conexión necesidad→conocimiento es inferida
  por construcción, y el sistema lo declara en lugar de simular el enlace.
- **El conjunto de evaluación no es un Gold Standard**: 10 casos, un revisor,
  etiquetas derivadas de campos declarados. `precision@5` es una cota inferior.
- **La señal `method` no discrimina** cuando la consulta no declara metodología:
  aporta un desplazamiento, no un orden.
- **El dataset es sintético y muy regular.** Con datos institucionales reales
  habrá más ruido, duplicados y campos vacíos.
- **El índice vectorial vive en memoria.** Suficiente para 3.292 documentos;
  con un corpus mayor hay que moverlo a Neo4j o a un motor vectorial dedicado.
- **No hay autenticación ni control de acceso.** Es un prototipo de
  demostración, no un sistema en producción.

---

## Documentación

| Documento | Contenido |
|---|---|
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | arquitectura implementada y sus diferencias con el diseño original |
| [docs/RANKING.md](docs/RANKING.md) | qué se tiene en cuenta para priorizar, señal por señal |
| [docs/CASOS_DEMOSTRABLES.md](docs/CASOS_DEMOSTRABLES.md) | cinco casos con salida real, incluidas dos pruebas negativas |
| [docs/EVIDENCIA_DESEMPENO.md](docs/EVIDENCIA_DESEMPENO.md) | métricas, metodología y limitaciones |
| [docs/COMPONENTES_EXTERNOS.md](docs/COMPONENTES_EXTERNOS.md) | modelos, bibliotecas, servicios y herramientas generativas |
| [docs/CONTRATO_API.md](docs/CONTRATO_API.md) | contrato que consume la interfaz |
| [docs/ENTREGA_PERSONA_1.md](docs/ENTREGA_PERSONA_1.md) | modelo, dimensión y Cypher del índice vectorial |
| [docs/CHECKLIST_EVALUACION.md](docs/CHECKLIST_EVALUACION.md) | dónde se cumple cada punto del checklist de evaluación |
| [docs/presentacion.html](docs/presentacion.html) | presentación visual: cada parte del programa explicada |
