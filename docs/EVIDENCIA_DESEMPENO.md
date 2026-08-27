# Evidencia de desempeño

> Reproducible con `make evaluate` (o `knowledge-nexus evaluate`). El reporte
> completo se guarda en `artifacts/evaluation/last_report.json`.

## 1. Qué se midió y por qué así

El dataset público **no incluye Gold Standard**. En lugar de inventar uno o de
presentar métricas sin base, el equipo construyó un conjunto de revisión pequeño
y transparente, y lo declara como lo que es.

**Metodología** (`scripts/build_review_set.py`, congelado antes de ajustar pesos):

1. Se eligieron **10 necesidades institucionales de dominios distintos**:
   educación, salud digital, epidemiología, seguridad laboral, ambiental,
   energía, fraude financiero, riesgo crediticio, industrial y ciberseguridad.
2. Para cada una se fijó un **término declarado** del dominio (por ejemplo
   «calidad del agua» para `NEED-009`).
3. Se marcaron como pertinentes (grado 1) las entidades cuyos campos declarados
   (`keywords`, `title`, `main_topics`) contienen ese término.
4. Se añadió **revisión manual** para el caso multilingüe: `PRJ-002` es grado 2
   para `NEED-001` aunque no comparta ninguna palabra con la necesidad.
5. Se definieron **pruebas negativas**: entidades de otro dominio que no deben
   aparecer en el top-5.

**Limitaciones que reconocemos:**

- cobertura parcial: solo se etiquetan entidades que nombran el término, así que
  hay resultados correctos sin etiqueta;
- sesgo hacia coincidencias literales, justo lo contrario de lo que el sistema
  aporta;
- un solo revisor, sin acuerdo entre evaluadores;
- 10 casos es un tamaño pequeño: sirve como control de regresión, no como
  validación científica.

Por eso `precision@5` se reporta como **cota inferior**: lo no etiquetado se
trata como *desconocido*, no como irrelevante.

## 2. Resultados (k = 5, 10 casos)

| Métrica | Valor | Cómo se obtuvo |
|---|---|---|
| Precisión@5 en tipos etiquetados | **0.833** | proporción de resultados etiquetados, restringida a los tipos que la regla cubre |
| Precisión@5 sobre todos los tipos | 0.580 | incluye investigadores y grupos, que la regla no etiqueta nunca |
| NDCG@5 | 0.662 | ganancia con grados 2/1/0 sobre el ideal alcanzable |
| Recuperación de etiquetados@5 | 0.220 (techo 0.364) | con 13 etiquetas y k=5, el máximo posible es 5/13 |
| Cobertura de evidencia | **1.000** | conexiones mostradas con al menos un elemento de evidencia |
| Trazabilidad completa | **1.000** | elementos de evidencia con archivo, fila, campo y fragmento |
| Oportunidades con solo IDs existentes | **sí** | validado por `IdentifierGuard` en cada respuesta |
| Violaciones negativas | **0** | ninguna entidad de dominio incompatible entró al top-5 |
| Latencia mediana | 165 ms | consulta completa: codificación, recuperación, ranking y evidencia |
| Latencia p95 | 256 ms | idem |

Medido en Apple Silicon (MPS), backend de grafo JSONL local, modelo `BAAI/bge-m3`
de 1024 dimensiones, ranking versión `1.0.0`.

## 3. Cómo interpretar la diferencia entre las dos precisiones

El sistema devuelve deliberadamente varios tipos de entidad: proyectos, tesis,
**personas**, capacidades y currículo. La regla de etiquetado solo cubre
documentos (proyecto, tesis, publicación, capacidad, asignatura), así que cada
investigador recuperado cuenta como fallo aunque sea correcto.

En el caso de demostración, `INV-124` es una investigadora que participó en los
proyectos de riesgo académico: es un resultado útil que la métrica penaliza. Por
eso se reportan las dos cifras y no solo la favorable.

## 4. Pruebas automatizadas

74 pruebas, ~15 segundos, sin red (usan un proveedor de embeddings determinista):

```bash
make test
```

Cubren, entre otras cosas:

| Qué se comprueba | Archivo |
|---|---|
| Dimensión constante y cobertura total de los embeddings | `tests/test_embeddings.py` |
| Reanudación sin recalcular y rechazo de mezcla de modelos | `tests/test_embeddings.py` |
| Paridad de firma entre el grafo local y el de Aura | `tests/test_data_layer.py` |
| Deduplicación de candidatos y aporte de los tres canales | `tests/test_retrieval.py` |
| `PRJ-002` en el top-5 de la consulta de deserción | `tests/test_retrieval.py` |
| Que el puente multilingüe no depende del léxico auxiliar | `tests/test_retrieval.py` |
| Suma de pesos, consistencia del desglose y determinismo | `tests/test_ranking.py` |
| Evidencia no vacía y fragmento que procede del campo citado | `tests/test_evidence_and_opportunities.py` |
| Rechazo de IDs inexistentes en oportunidades y en el LLM | `tests/test_evidence_and_opportunities.py` |
| Compatibilidad de la respuesta con el fixture del equipo | `tests/test_api_contract.py` |
| Que la interfaz no use claves de contrato inventadas | `tests/test_discarded_and_ui_contract.py` |
| Ausencia de secretos en el repositorio | `tests/test_security_and_evaluation.py` |

## 5. Pruebas negativas ejecutadas

Están documentadas con salida real en [`CASOS_DEMOSTRABLES.md`](CASOS_DEMOSTRABLES.md):

| Escenario | Resultado observado |
|---|---|
| Misma palabra, dominio incompatible (`NEED-009` + pregunta de educación) | el motor prioriza el dominio de la necesidad; ningún proyecto educativo entra al top-5 |
| Consulta sin respuesta en el dataset (cocina medieval) | confianza **baja** declarada: semántica 0.27, dominio 0.08 |
| Umbral de calidad activado | la respuesta queda vacía y bien formada, con el motivo explicado |
| El LLM intenta citar un ID inexistente | el texto se descarta y se conserva la redacción determinista |
| Entidad sin evidencia | no se muestra: se descarta antes de responder |

## 6. Qué no medimos

- **Utilidad real para un investigador**: requeriría evaluación humana con
  expertos del dominio, que no teníamos.
- **Calidad de las oportunidades generadas**: se verifica que sean trazables y
  que no inventen entidades, no que sean buenas ideas.
- **Comportamiento con datos institucionales reales**: Data V1.0 es sintético y
  muy regular; un corpus real tendrá más ruido, duplicados y campos vacíos.
