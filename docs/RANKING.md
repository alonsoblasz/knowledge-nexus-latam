# Qué se tiene en cuenta para rankear

> El total expresa **relevancia para la consulta**. No es verdad científica, ni
> probabilidad de éxito, ni una aprobación institucional. La interfaz debe
> mostrar el desglose, nunca solo el número.

Versión de la fórmula: `1.0.0` (`config/ranking.yaml`). Cada respuesta de la API
incluye `relevance.ranking_version`, los pesos aplicados y el detalle de cada
señal en `components_detail`.

## 1. La búsqueda vectorial genera candidatos, no decide

El embedding responde a una sola pregunta: *¿de qué habla este texto?*. Eso basta
para descubrir que «deserción estudiantil» y «student attrition» son lo mismo,
pero no para decidir cuál de cuatro proyectos igualmente parecidos sirve más.

Por eso la similitud vectorial es **una de seis señales**, y el candidato llega
al ranking por tres vías distintas:

| Canal | Qué aporta | Riesgo si se usara solo |
|---|---|---|
| Vectorial (BGE-M3, 1024d) | equivalencia conceptual entre idiomas y sinónimos | similitud superficial: textos que "suenan" parecido |
| Léxico (BM25) | anclaje literal y explicable, término por término | no cruza idiomas ni sinónimos |
| Expansión del grafo | quién participó, qué grupo, qué producción | no sabe de qué trata la consulta |

Los tres se deduplican por ID antes de puntuar. Un candidato conserva la traza
de por qué canales entró (`retrieval.channels`).

## 2. Las seis señales

### `semantic` — peso 0.35

Fusión del canal vectorial y el léxico:

```text
semantic = 0.70 * coseno_calibrado + 0.30 * bm25_normalizado
```

- **Coseno calibrado.** El coseno crudo de BGE-M3 sobre Data V1.0 tiene mediana
  0.35 (ruido del corpus) y máximo ≈ 0.65. Un 0.55 crudo no significa "55 % de
  parecido". Se reescala con piso 0.35 y techo 0.62, medidos sobre este corpus y
  registrados en el manifiesto de embeddings. Cambiar de modelo obliga a
  recalibrar.
- **BM25 normalizado.** Se divide por el mejor BM25 de esa misma consulta, así
  que es relativo al conjunto de resultados, no comparable entre consultas.
- **Términos coincidentes.** Se guardan y se muestran (`matched_terms`): son la
  parte de la explicación que un evaluador puede verificar a ojo.

La consulta combina texto libre y entidad de origen: `0.65 * vector(pregunta) +
0.35 * vector(necesidad)`, renormalizado. Ambos se codifican como *consulta*
para no mezclar convenciones de codificación.

### `domain` — peso 0.20

Responde a "¿es del mismo mundo institucional y temático?". Tres subseñales:

| Subseñal | Peso | Cómo se calcula |
|---|---|---|
| `institutional` | 0.35 | unidades declaradas compartidas (`faculty_id`, `program_id`, `group_id`, `responsible_unit`, `originating_unit`) |
| `topical` | 0.40 | coseno de términos entre el perfil de la consulta y los campos de dominio del candidato |
| `area` | 0.25 | solapamiento del área disciplinar declarada, incluida la de las unidades ancladas |

`NEED-001` no declara área disciplinar, pero sí `originating_unit: "Unidad
asociada a FAC-004"`. De ahí se extrae el ID canónico `FAC-004` —**solo si
existe** en el grafo— y se hereda su área ("Educación y Ciencias Humanas"). Ese
puente explica por qué `PRJ-002` (dominio 0.54) supera a proyectos con el mismo
tema pero sin la unidad compartida.

Si la consulta no puede evaluar una subseñal (por ejemplo, no hay unidad de
origen), esa subseñal se **excluye y se reparte su peso**: no se castiga al
candidato por algo que la consulta no preguntó.

### `method` — peso 0.15

Compatibilidad metodológica, con dos modos explícitos:

- **Modo comparado** (la consulta o la entidad de origen declaran metodología):
  proporción del vocabulario metodológico pedido que el candidato cubre.
- **Modo de respaldo** (nadie declara metodología, como en la consulta de
  demostración): se valora la sustancia metodológica del propio candidato
  —¿declara metodología?, ¿con cuántos términos reconocibles?— con tope 0.75,
  porque no hubo comparación real.

El vocabulario metodológico (`config/lexicon.yaml`) proviene de los valores
observados en `methodology`, `methodological_expertise` y `data_or_population`
de Data V1.0.

Solo el modo comparado puede etiquetar una relación como
`METHODOLOGICALLY_COMPATIBLE`.

### `graph` — peso 0.10

Soporte estructural, calculado **solo con relaciones explícitas**:

| Subseñal | Peso | Cómo se calcula |
|---|---|---|
| `proximity` | 0.45 | 1 salto = 1.0, 2 = 0.6, 3 = 0.3. Si el candidato llegó por expansión desde otro candidato, el mismo decaimiento con descuento 0.75 |
| `connectivity` | 0.35 | `log1p(grado)/log1p(12)`: una entidad conectada es más accionable |
| `context_bridge` | 0.20 | vecinos compartidos con la entidad de origen y sus unidades ancladas |

Detalle importante del dataset: **`InstitutionalNeed` no tiene aristas hacia
proyectos**; su única relación explícita es con su documento. La distancia
`NEED-001 → PRJ-002` es infinita y así se reporta
(`explicit_distance_from_source: null`). El motor no inventa el enlace que falta:
usa la conectividad del candidato y los vecinos compartidos (`FAC-004`).

### `evidence` — peso 0.10

Cuánta evidencia verificable respalda a la entidad:

| Subseñal | Peso | Cómo se calcula |
|---|---|---|
| `field_coverage` | 0.50 | proporción de campos semánticos del tipo con contenido real |
| `provenance` | 0.20 | archivo, fila y ruta presentes |
| `relation_provenance` | 0.20 | número de relaciones explícitas con procedencia (tope 3) |
| `document_support` | 0.10 | tiene documento `DESCRIBES` o referencia documental |

### `actionable` — peso 0.10

Si la conexión puede convertirse en una acción:

| Subseñal | Peso | Cómo se calcula |
|---|---|---|
| `status` | 0.35 | tabla configurable: `COMPLETED` 1.00, `ACTIVE` 1.00, `FORMULATION` 0.55, `INACTIVE` 0.20… |
| `recency` | 0.25 | decaimiento exponencial con vida media de 6 años |
| `people` | 0.20 | investigadores identificables asociados |
| `outputs` | 0.10 | producción derivada (publicaciones, tesis dirigidas) |
| `resources` | 0.10 | nivel de madurez declarado (capacidades) |

La vigencia usa como año de referencia **el año máximo presente en Data V1.0**
(2026), no la fecha del sistema: el mismo dataset produce siempre el mismo score.

## 3. Penalizaciones

Se restan del total y se muestran con su motivo:

| Penalización | Valor | Cuándo |
|---|---|---|
| `inactive_entity` | 0.15 | estado `INACTIVE`/`CLOSED`/`DEPRECATED`/`SUSPENDED` o `active = false` |
| `missing_evidence` | 0.10 | cobertura de evidencia < 0.30 |
| `superficial_match` | 0.08 | semántica < 0.35, un término coincidente o ninguno y sin soporte de grafo |
| `domain_mismatch` | 0.10 | dominio 0.0 y semántica < 0.55 habiendo dominio consultable |
| `redundancy` | 0.06 | contenido casi idéntico (coseno ≥ 0.92) a un resultado mejor situado |

El total de penalizaciones se recorta en 0.35 para que ninguna entidad quede
anulada por acumulación.

```text
total = clamp01( Σ pesoᵢ · señalᵢ − Σ penalizaciones )
```

## 4. Selección final

- **Umbral de calidad** (`retrieval.min_total_score`): por debajo de él no se
  muestra nada. Permite responder "sin resultados" en vez de rellenar con
  coincidencias débiles.
- **Diversificación por tipo** (`selection.max_per_type: 2`): cuando la consulta
  pide varios tipos, ninguno ocupa toda la respuesta. El primer puesto siempre es
  el de mayor relevancia; la cuota solo afecta a los siguientes.
- **Sin evidencia, no se muestra.** Una conexión sin al menos un elemento de
  evidencia se descarta antes de responder.

## 5. Ejemplo real: `NEED-001` → `PRJ-002`

Consulta: *«¿Qué nueva investigación puede ayudar a prevenir la deserción
estudiantil?»*

| Señal | Valor | Peso | Aporte | Por qué |
|---|---|---|---|---|
| semantic | 0.974 | 0.35 | 0.341 | coseno 0.663 (calibrado a 1.0) + BM25 0.91; términos `student attrition`, `riesgo académico` |
| domain | 0.544 | 0.20 | 0.109 | comparte `FAC-004`; área "Ciencias de la Educación" |
| method | 0.750 | 0.15 | 0.113 | modo de respaldo: declara integración de fuentes, análisis comparativo, validación |
| graph | 0.602 | 0.10 | 0.060 | sin camino explícito desde la necesidad; grado 8; vecino compartido `FAC-004` |
| evidence | 1.000 | 0.10 | 0.100 | 9/9 campos con contenido, procedencia completa, documento asociado |
| actionable | 0.878 | 0.10 | 0.088 | `COMPLETED`, 2020–2021, 2 investigadores, produce publicaciones |
| **total** | **0.810** | | | sin penalizaciones |

Relación inferida: `RELEVANT_ANTECEDENT` (`relation_origin: INFERRED`), porque es
un `Project` con estado `COMPLETED`. Si estuviera `ACTIVE` sería
`SEMANTICALLY_RELATED`: un trabajo en curso no es todavía un antecedente.

## 6. Por qué A aparece antes que B

`PRJ-002` (0.810) frente a `PRJ-004` (0.793): ambos hablan de *student
attrition* con semántica casi idéntica (0.974 vs 0.990). La diferencia está en
`domain` (0.544 vs 0.45) —`PRJ-002` comparte más vocabulario declarado con la
necesidad— y en que su estado `COMPLETED` lo convierte en antecedente utilizable.
Ese razonamiento está en `components_detail`, no hay que reconstruirlo.

## 7. Límites conocidos y honestos

- **Los pesos son una hipótesis.** Están en configuración y versionados
  precisamente para poder ajustarlos con evaluación humana.
- **`method` no discrimina cuando la consulta no declara metodología.** En modo
  de respaldo casi todos los proyectos con metodología completa obtienen 0.75:
  esa señal aporta un offset, no un orden.
- **La expansión léxica reordena, no descubre.** Con
  `use_lexicon_expansion: false`, `PRJ-002` sigue apareciendo entre los cinco
  proyectos mejor rankeados: el puente español–inglés lo aporta el modelo. Lo que
  cambia es el orden frente a `PRJ-001`, `PRJ-004` y `PRJ-006`, que repiten
  literalmente las palabras de la necesidad y son igual de pertinentes.
  Hay una prueba dedicada a esto (`tests/test_retrieval.py`).
- **`precision@5` del conjunto de revisión es una cota inferior**: lo no
  etiquetado se trata como desconocido, no como irrelevante.
