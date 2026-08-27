# Entrega a la persona 1 — embeddings e índice vectorial

## Modelo elegido

| Dato | Valor |
|---|---|
| Modelo | `BAAI/bge-m3` |
| Dimensión | **1024** |
| Normalización | L2, vectores unitarios |
| Prefijos de codificación | ninguno (BGE-M3 no los usa) |
| Documentos procesados | 3,292 (cobertura total del corpus semántico) |
| Tiempo de generación | ~72 s en Apple Silicon (MPS), lotes de 32 |

Se usó el modelo principal recomendado, no el de respaldo: la máquina de
desarrollo tenía memoria suficiente. Si hubiera que cambiar a
`intfloat/multilingual-e5-small` (384d), habría que **regenerar el artefacto
completo y recrear el índice**: no se pueden mezclar modelos ni dimensiones.

## Artefactos entregados

| Archivo | Contenido |
|---|---|
| `artifacts/embeddings/semantic_embeddings.jsonl` | un vector por documento semántico (34 MB) |
| `artifacts/embeddings/embeddings_manifest.json` | modelo, dimensión, fecha, conteos y hash del origen |

El JSONL no se versiona en git por tamaño; se entrega como archivo.

Cada línea:

```json
{
  "id": "PRJ-002",
  "entity_type": "Project",
  "model": "BAAI/bge-m3",
  "dimension": 1024,
  "text_sha256": "…",
  "embedding": [0.012, -0.034]
}
```

`text_sha256` es el hash del texto exactamente como se indexó. Si un documento
semántico cambia, el motor lo detecta al validar (`validate_coverage`) y avisa en
lugar de servir un vector obsoleto.

El manifiesto incluye `source_sha256` del `semantic_documents.jsonl` usado:
`57b72929a2af719c42f84a33ab30ad661a254b0eeb42797b1e5a49ca9423fefb`. Si ese hash
cambia, hay que regenerar.

## Verificaciones ya hechas

- IDs idénticos a los del corpus, sin duplicados;
- dimensión constante 1024 en los 3,292 vectores;
- cobertura completa: ningún documento sin vector;
- el artefacto no contiene texto fuente ni credenciales (solo ID, tipo, modelo,
  dimensión, hash y vector).

## Índice vectorial sugerido en Neo4j

El nombre debe ser `semantic_embedding`, que es el que ya usa la consulta 7 de
`cypher/demo_queries.cypher`:

```cypher
CREATE VECTOR INDEX semantic_embedding IF NOT EXISTS
FOR (entity:Entity) ON (entity.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};
```

Se indexa sobre `:Entity` —no sobre `:SemanticEntity`— porque la consulta 7
filtra por `node.entity_type` y porque los 60 nodos `Document` también tienen
vector. Llevan embedding **3,292 de los 3,327 nodos**: los 35 `Source` no son
entidades semánticas y quedan fuera por diseño.

Carga de los vectores (por lotes, sin tocar otras propiedades):

```cypher
UNWIND $batch AS row
MATCH (entity:Entity {id: row.id})
CALL db.create.setNodeVectorProperty(entity, 'embedding', row.embedding);
```

Los vectores ya vienen normalizados, así que `cosine` y producto punto coinciden.

## Cómo activar Aura en el motor

El backend de grafo se elige por entorno; el motor **no lee ni registra
credenciales**: las resuelve `knowledge_nexus_data.GraphRepository.from_env()`.

```bash
export KNOWLEDGE_NEXUS_GRAPH_BACKEND=neo4j
# NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE en el entorno local
```

El motor consume únicamente los cuatro métodos del contrato (`get_entity`,
`get_neighbors`, `get_evidence`, `find_related_entities`); no escribe Cypher
propio. `tests/test_data_layer.py` comprueba que la implementación local tiene
exactamente las mismas firmas.

## Observaciones sobre los datos (sin cambios solicitados)

Ninguna incidencia bloqueante. Dos hechos que conviene conocer, no son errores:

1. **`InstitutionalNeed` no tiene relaciones explícitas hacia proyectos, tesis ni
   capacidades**: su única arista es `DESCRIBES` desde su documento. Toda
   conexión necesidad→conocimiento es, por construcción, inferida. El motor lo
   refleja (`explicit_distance_from_source: null`) en lugar de simularla.
2. **`originating_unit` de las necesidades es texto** (`"Unidad asociada a
   FAC-004"`), no una clave foránea. El motor extrae el ID canónico y lo usa solo
   si existe en el grafo. Si en una versión futura se normaliza como
   `faculty_id`, la señal de dominio mejora sin cambiar código.
