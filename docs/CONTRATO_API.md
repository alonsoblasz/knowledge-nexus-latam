# Contrato de la API (para la interfaz)

La respuesta de `POST /v1/search` **conserva la estructura de
`team_fixture_search_response.json`**. Cambiar del fixture a la API requiere solo
apuntar a la URL del servicio.

```env
KNOWLEDGE_NEXUS_DATA_SOURCE=api
KNOWLEDGE_NEXUS_API_URL=http://localhost:8000
```

## Endpoints

| Método | Ruta | Resultado |
|---|---|---|
| `GET` | `/health` | estado, modelo, dimensión, versión del ranking |
| `POST` | `/v1/search` | conexiones priorizadas con evidencia y oportunidades |
| `POST` | `/v1/opportunities` | oportunidades y las conexiones que las sustentan |
| `GET` | `/v1/entities/{type}/{id}` | entidad, vecindario explícito y evidencia |
| `GET` | `/v1/needs` | necesidades institucionales para el selector (añadido) |

Documentación interactiva en `http://localhost:8000/docs`.

## Solicitud

```json
{
  "query": "¿Qué investigación puede ayudar a prevenir la deserción estudiantil?",
  "source_entity_id": "NEED-001",
  "target_types": ["Project", "Thesis", "Researcher", "Capability", "Subject"],
  "limit": 5
}
```

Campos opcionales: `include_opportunities` (bool), `max_opportunities` (int),
`include_graph` (bool). Se rechaza cualquier campo desconocido y cualquier tipo
de entidad fuera de la lista permitida.

## Qué se conserva del fixture

Idénticos en nombre y significado:

`contract_version`, `fixture_only`, `warning`, `query_entity{id,type,title}`,
`connections[]{connection_id, source, target, relation, relation_origin,
relevance{total,semantic,domain,method,graph,evidence}, explanation,
evidence[]{file,row,record_id,field,excerpt}}`,
`opportunities[]{opportunity_id,type,title,reason,priority,related_entities[]}`.

## Qué se añade (compatible)

| Campo | Dónde | Para qué |
|---|---|---|
| `relevance.actionable` | conexión | sexta señal de la fórmula |
| `relevance.weights`, `weighted_contributions`, `base_total`, `penalties`, `penalty_total`, `ranking_version`, `interpretation` | conexión | desglose completo y auditable |
| `components_detail` | conexión | subseñales y motivos de cada componente |
| `retrieval` | conexión | canales usados, términos coincidentes y camino de expansión |
| `rank`, `global_rank` | conexión | posición mostrada y posición en el ranking completo |
| `evidence[].path`, `origin`, `relation_origin` | evidencia | ruta completa y si el fragmento viene de un campo o de una relación explícita |
| `opportunities[].supporting_connections`, `uncertainty`, `relation_origin`, `status`, `disclaimer` | oportunidad | trazabilidad e incertidumbre declarada |
| `graph{nodes,edges}` | respuesta | subgrafo listo para pintar (máx. 20 nodos) |
| `query` | respuesta | términos, anclas y notas de la interpretación |
| `meta` | respuesta | versión del ranking, modelo, latencia, diagnóstico y `empty_result` |

## Diferencias de valor respecto al fixture

| Campo | Fixture | API |
|---|---|---|
| `fixture_only` | `true` | `false` |
| `relation_origin` | `INFERRED_FIXTURE` | `INFERRED` |
| `connection_id` | `FIXTURE-CONN-001` | `CONN-NEED-001-PRJ-002` |
| `opportunity_id` | `FIXTURE-OPP-001` | `OPP-NEED-001-001` |
| `warning` | aviso de datos simulados | aviso de interpretación del score |

Mientras la interfaz use el fixture debe mostrar la etiqueta de "resultado
simulado"; con la API, `fixture_only: false` indica que puede retirarla.

## Estados que la interfaz debe cubrir

- **Sin resultados**: `connections: []`, `opportunities: []`,
  `meta.empty_result: true` y `meta.reason` con el motivo. La respuesta sigue
  siendo válida.
- **Consulta libre sin necesidad**: `query_entity.id` es `null` y
  `query_entity.type` es `"FreeTextQuery"`.
- **Errores**: `404` si la entidad de origen o la entidad consultada no existe;
  `422` si faltan `query` y `source_entity_id`, si el tipo no está permitido o si
  llega un campo desconocido. El cuerpo trae `detail` legible.

## Subgrafo

`graph.nodes[]` usa `{id, label, title, source_file, source_row}` y
`graph.edges[]` usa `{source_id, source_label, relationship, target_id,
target_label, properties, provenance, relation_origin}` — la misma forma que
`team_fixture_graph.json`.

Las aristas con `relation_origin: "INFERRED"` son las calculadas por el ranking
(dibujar discontinuas) y llevan `properties.score_total`; las `EXPLICIT`
provienen de Data V1.0 y traen su procedencia.

## Cambios de contrato

Cualquier renombrado o eliminación se coordina antes de aplicarse. Las pruebas
`tests/test_api_contract.py` comprueban que toda clave del fixture sigue
existiendo en la respuesta real.
