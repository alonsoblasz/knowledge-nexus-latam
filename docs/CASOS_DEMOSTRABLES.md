# Casos demostrables

> Generado por `scripts/build_demo_cases.py` con salida real del motor.
> Los scores expresan **relevancia para la consulta**: no son verdad
> científica ni aprobación institucional.

Cada caso recorre la cadena completa que pide la evaluación:
**entidad → relación → evidencia → pertinencia → oportunidad → explicación**.

## CASO-1 — Conexión no literal entre idiomas

**Consulta:** «¿Qué nueva investigación puede ayudar a prevenir la deserción estudiantil?»

**Entidad de origen:** `NEED-001` — Predicción y prevención de deserción estudiantil

**Por qué importa:** La consulta dice «deserción estudiantil». El registro que mejor responde nunca usa esa palabra: dice «student attrition». Una búsqueda por palabras clave no los conecta.

| # | Entidad | Tipo | Relación inferida | Relevancia |
|---|---|---|---|---|
| 1 | `PRJ-002` Modelo institucional para riesgo académico y su relación con student attrition | Project | `RELEVANT_ANTECEDENT` | 0.810 |
| 2 | `PRJ-004` Estrategia basada en clasificación supervisada para estudiar student attrition | Project | `SEMANTICALLY_RELATED` | 0.793 |
| 3 | `THS-016` Análisis de patrones asociados con riesgo académico | Thesis | `RELEVANT_ANTECEDENT` | 0.728 |
| 4 | `INV-124` Adriana Mendoza Moreno | Researcher | `POTENTIAL_COLLABORATOR` | 0.708 |
| 5 | `THS-018` Evaluación de clasificación supervisada para analizar trayectorias educativas | Thesis | `RELEVANT_ANTECEDENT` | 0.706 |

**Desglose del primer resultado (`PRJ-002`):** semantic 0.97 · domain 0.54 · method 0.75 · graph 0.60 · evidence 1.00 · actionable 0.88 → total 0.810

**Explicación del motor:** Project PRJ-002: coincide con la consulta en «attrition», «student», «student attrition» (similitud vectorial 0.6628); comparte la unidad institucional FAC-004; declara metodología de análisis comparativo, integración de fuentes; comparte vecinos en el grafo (FAC-004); su estado registrado es COMPLETED y tiene 2 investigador(es) identificable(s). La señal que más aporta es «semantic» (42% de la puntuación antes de penalizaciones).

**Evidencia (archivo, fila, campo, fragmento):**

- `projects.csv` fila 3, campo `title` (PRJ-002): «Modelo institucional para riesgo académico y su relación con student attrition»
- `projects.csv` fila 3, campo `problem_statement` (PRJ-002): «La información sobre riesgo académico se encuentra distribuida y existen dificultades para relacionarla con student attrition de manera verificable.»
- `projects.csv` fila 3, campo `abstract` (PRJ-002): «Proyecto orientado a estudiar riesgo académico y su relación con student attrition, integrando evidencia institucional y un enfoque de analítica educativa.»

**Oportunidad generada:** `RESEARCH_CONTINUITY` — Continuidad de investigación sobre predicción y prevención de deserción estudiantil (prioridad HIGH)

Existen antecedentes terminados (PRJ-002, THS-016, THS-018) que pueden continuarse para atender la necesidad NEED-001. Respaldo recuperado: PRJ-002 (Project), THS-016 (Thesis), INV-124 (Researcher).

Entidades referenciadas: `NEED-001`, `PRJ-002`, `THS-016`, `INV-124`

Incertidumbre declarada:

- Las conexiones que sustentan esta oportunidad son inferidas por similitud y estructura del grafo; no existen como relación explícita en Data V1.0.
- No se recuperó una capacidad con nivel de madurez declarado.

**Candidatos descartados y por qué:**

- `PRJ-006` (0.79) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `PRJ-001` (0.79) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `PUB-074` (0.29) — Penalizada por: No comparte unidad, área ni vocabulario con el dominio consultado.

---

## CASO-2 — Consulta libre en otro dominio, sin necesidad seleccionada

**Consulta:** «¿Cómo podemos monitorear la calidad del agua en cuencas con sensores?»

**Entidad de origen:** ninguna (consulta libre)

**Por qué importa:** Demuestra que el prototipo responde a preguntas nuevas y no a un guion precargado, y que funciona fuera del dominio educativo.

| # | Entidad | Tipo | Relación inferida | Relevancia |
|---|---|---|---|---|
| 1 | `PRJ-065` Análisis aplicado de calidad del agua para fortalecer cuencas | Project | `RELEVANT_ANTECEDENT` | 0.795 |
| 2 | `PRJ-070` Modelo institucional para calidad del agua y su relación con cuencas | Project | `RELEVANT_ANTECEDENT` | 0.789 |
| 3 | `INV-128` Mónica Montoya Mejía | Researcher | `POTENTIAL_COLLABORATOR` | 0.678 |
| 4 | `INV-135` Sebastián Cardona Quintero | Researcher | `POTENTIAL_COLLABORATOR` | 0.666 |
| 5 | `THS-175` Modelo aplicado para el estudio de contaminación hídrica | Thesis | `RELEVANT_ANTECEDENT` | 0.651 |

**Desglose del primer resultado (`PRJ-065`):** semantic 1.00 · domain 0.40 · method 0.75 · graph 0.78 · evidence 0.90 · actionable 0.85 → total 0.795

**Explicación del motor:** Project PRJ-065: coincide con la consulta en «cuencas», «calidad agua», «agua» (similitud vectorial 0.6545); comparte vocabulario de dominio (agua, calidad, calidad agua); declara metodología de análisis comparativo, integración de fuentes; su estado registrado es COMPLETED y tiene 2 investigador(es) identificable(s). La señal que más aporta es «semantic» (44% de la puntuación antes de penalizaciones).

**Evidencia (archivo, fila, campo, fragmento):**

- `projects.csv` fila 66, campo `title` (PRJ-065): «Análisis aplicado de calidad del agua para fortalecer cuencas»
- `projects.csv` fila 66, campo `problem_statement` (PRJ-065): «La información sobre calidad del agua se encuentra distribuida y existen dificultades para relacionarla con cuencas de manera verificable.»
- `projects.csv` fila 66, campo `abstract` (PRJ-065): «Proyecto orientado a estudiar calidad del agua y su relación con cuencas, integrando evidencia institucional y un enfoque de IoT.»

**Oportunidad generada:** `RESEARCH_CONTINUITY` — Continuidad de investigación sobre Análisis aplicado de calidad del agua para fortalecer cuencas (prioridad HIGH)

Existen antecedentes terminados (PRJ-065, PRJ-070, THS-175) que pueden continuarse para atender la consulta recibida. Respaldo recuperado: PRJ-065 (Project), THS-175 (Thesis), INV-128 (Researcher).

Entidades referenciadas: `PRJ-065`, `THS-175`, `INV-128`

Incertidumbre declarada:

- Las conexiones que sustentan esta oportunidad son inferidas por similitud y estructura del grafo; no existen como relación explícita en Data V1.0.
- La consulta no indicó una necesidad institucional: el foco se derivó del texto.
- No se recuperó una capacidad con nivel de madurez declarado.

**Candidatos descartados y por qué:**

- `PRJ-068` (0.70) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `INV-149` (0.66) — Ya se mostraban 2 entidades de tipo Researcher; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `GRP-022` (0.11) — Penalizada por: Coincidencia débil y sin soporte estructural en el grafo.

---

## CASO-3 — De la necesidad a las personas y el currículo

**Consulta:** «¿Quién y con qué capacidades puede trabajar en riesgo crediticio explicable?»

**Entidad de origen:** `NEED-014` — Riesgo crediticio explicable

**Por qué importa:** Muestra conexiones con investigación, personas y capacidades en la misma respuesta, no solo documentos parecidos.

| # | Entidad | Tipo | Relación inferida | Relevancia |
|---|---|---|---|---|
| 1 | `PRJ-105` Análisis aplicado de riesgo crediticio para fortalecer credit scoring | Project | `RELEVANT_ANTECEDENT` | 0.835 |
| 2 | `PRJ-108` Estrategia basada en IA explicable para estudiar decisiones explicables | Project | `SEMANTICALLY_RELATED` | 0.783 |
| 3 | `THS-266` Evaluación de IA explicable para analizar riesgo crediticio | Thesis | `RELEVANT_ANTECEDENT` | 0.674 |
| 4 | `THS-275` Modelo aplicado para el estudio de incumplimiento | Thesis | `RELEVANT_ANTECEDENT` | 0.666 |
| 5 | `INV-081` Nicolás Arias Gómez | Researcher | `POTENTIAL_COLLABORATOR` | 0.639 |

**Desglose del primer resultado (`PRJ-105`):** semantic 1.00 · domain 0.52 · method 0.75 · graph 0.84 · evidence 0.90 · actionable 0.94 → total 0.835

**Explicación del motor:** Project PRJ-105: coincide con la consulta en «crediticio explicable», «crediticio», «riesgo crediticio» (similitud vectorial 0.7558); comparte la unidad institucional FAC-003; declara metodología de análisis comparativo, integración de fuentes; comparte vecinos en el grafo (FAC-003); su estado registrado es COMPLETED y tiene 3 investigador(es) identificable(s). La señal que más aporta es «semantic» (42% de la puntuación antes de penalizaciones).

**Evidencia (archivo, fila, campo, fragmento):**

- `projects.csv` fila 106, campo `abstract` (PRJ-105): «Proyecto orientado a estudiar riesgo crediticio y su relación con credit scoring, integrando evidencia institucional y un enfoque de IA explicable.»
- `projects.csv` fila 106, campo `title` (PRJ-105): «Análisis aplicado de riesgo crediticio para fortalecer credit scoring»
- `projects.csv` fila 106, campo `problem_statement` (PRJ-105): «La información sobre riesgo crediticio se encuentra distribuida y existen dificultades para relacionarla con credit scoring de manera verificable.»

**Oportunidad generada:** `RESEARCH_CONTINUITY` — Continuidad de investigación sobre riesgo crediticio explicable (prioridad HIGH)

Existen antecedentes terminados (PRJ-105, THS-266, THS-275) que pueden continuarse para atender la necesidad NEED-014. Respaldo recuperado: PRJ-105 (Project), THS-266 (Thesis), INV-081 (Researcher).

Entidades referenciadas: `NEED-014`, `PRJ-105`, `THS-266`, `INV-081`

Incertidumbre declarada:

- Las conexiones que sustentan esta oportunidad son inferidas por similitud y estructura del grafo; no existen como relación explícita en Data V1.0.
- No se recuperó una capacidad con nivel de madurez declarado.

**Candidatos descartados y por qué:**

- `PRJ-110` (0.78) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `PRJ-107` (0.70) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `PUB-100` (0.17) — Penalizada por: Coincidencia débil y sin soporte estructural en el grafo.; No comparte unidad, área ni vocabulario con el dominio consultado.

---

## CASO-4 — Prueba negativa: dominio incompatible

**Consulta:** «¿Qué investigación existe sobre deserción estudiantil?»

**Entidad de origen:** `NEED-009` — Monitoreo inteligente de calidad del agua

**Por qué importa:** La necesidad es de calidad del agua y la pregunta de educación. El motor debe priorizar el dominio de la necesidad y no arrastrar los proyectos educativos al primer puesto.

| # | Entidad | Tipo | Relación inferida | Relevancia |
|---|---|---|---|---|
| 1 | `INV-133` Carlos Suárez Mendoza | Researcher | `POTENTIAL_COLLABORATOR` | 0.733 |
| 2 | `PRJ-070` Modelo institucional para calidad del agua y su relación con cuencas | Project | `RELEVANT_ANTECEDENT` | 0.731 |
| 3 | `PRJ-065` Análisis aplicado de calidad del agua para fortalecer cuencas | Project | `RELEVANT_ANTECEDENT` | 0.724 |
| 4 | `INV-135` Sebastián Cardona Quintero | Researcher | `POTENTIAL_COLLABORATOR` | 0.712 |
| 5 | `THS-161` Caracterización de calidad del agua en relación con variables fisicoquímicas | Thesis | `RELEVANT_ANTECEDENT` | 0.677 |

**Desglose del primer resultado (`INV-133`):** semantic 0.78 · domain 0.45 · method 0.75 · graph 0.65 · evidence 0.90 · actionable 1.00 → total 0.733

**Explicación del motor:** Researcher INV-133: coincide con la consulta en «inteligente calidad», «inteligente», «calidad agua» (similitud vectorial 0.5824); comparte la unidad institucional FAC-005; declara metodología de series temporales, simulación; comparte vecinos en el grafo (FAC-005); su estado registrado es True. La señal que más aporta es «semantic» (37% de la puntuación antes de penalizaciones).

**Evidencia (archivo, fila, campo, fragmento):**

- `researchers.csv` fila 134, campo `profile_summary` (INV-133): «Investigador con experiencia en infraestructura inteligente y calidad del agua, orientada a resolver problemas aplicados mediante enfoques interdisciplinarios.»
- `researchers.csv` fila 134, campo `research_interests` (INV-133): «infraestructura inteligente; calidad del agua»
- `researchers.csv` fila 134, campo `application_domains` (INV-133): «calidad del agua; infraestructura inteligente»

**Oportunidad generada:** `RESEARCH_CONTINUITY` — Continuidad de investigación sobre monitoreo inteligente de calidad del agua (prioridad HIGH)

Existen antecedentes terminados (PRJ-070, PRJ-065, THS-161) que pueden continuarse para atender la necesidad NEED-009. Respaldo recuperado: PRJ-070 (Project), THS-161 (Thesis), INV-133 (Researcher).

Entidades referenciadas: `NEED-009`, `PRJ-070`, `THS-161`, `INV-133`

Incertidumbre declarada:

- Las conexiones que sustentan esta oportunidad son inferidas por similitud y estructura del grafo; no existen como relación explícita en Data V1.0.
- No se recuperó una capacidad con nivel de madurez declarado.

**Candidatos descartados y por qué:**

- `PRJ-068` (0.71) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `INV-128` (0.71) — Ya se mostraban 2 entidades de tipo Researcher; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `THS-591` (0.36) — Penalizada por: No comparte unidad, área ni vocabulario con el dominio consultado.

---

## CASO-5 — Prueba negativa: consulta sin respuesta en el dataset

**Consulta:** «recetas de cocina medieval italiana con fermentación natural»

**Entidad de origen:** ninguna (consulta libre)

**Por qué importa:** Ninguna entidad institucional responde a esto. El sistema debe mostrar relevancias bajas y penalizaciones en lugar de fabricar una conexión.

| # | Entidad | Tipo | Relación inferida | Relevancia |
|---|---|---|---|---|
| 1 | `PRJ-020` Estrategia basada en procesamiento de lenguaje natural para estudiar rubric analysis | Project | `RELEVANT_ANTECEDENT` | 0.491 |
| 2 | `PRJ-017` Análisis aplicado de competencias para fortalecer evaluación formativa | Project | `SEMANTICALLY_RELATED` | 0.484 |
| 3 | `SUB-119` Procesamiento de lenguaje natural | Subject | `CURRICULAR_ALIGNMENT` | 0.450 |
| 4 | `THS-046` Evaluación de procesamiento de lenguaje natural para analizar competencias | Thesis | `RELEVANT_ANTECEDENT` | 0.436 |
| 5 | `THS-055` Modelo aplicado para el estudio de resultados de aprendizaje | Thesis | `RELEVANT_ANTECEDENT` | 0.429 |

**Desglose del primer resultado (`PRJ-020`):** semantic 0.27 · domain 0.08 · method 0.75 · graph 0.78 · evidence 1.00 · actionable 0.91 → total 0.491

**Explicación del motor:** Project PRJ-020: coincide con la consulta en «natural» (similitud vectorial 0.3157); comparte vocabulario de dominio (natural); declara metodología de análisis comparativo, integración de fuentes; su estado registrado es COMPLETED y tiene 2 investigador(es) identificable(s). La señal que más aporta es «method» (23% de la puntuación antes de penalizaciones).

**Evidencia (archivo, fila, campo, fragmento):**

- `projects.csv` fila 21, campo `title` (PRJ-020): «Estrategia basada en procesamiento de lenguaje natural para estudiar rubric analysis»
- `projects.csv` fila 21, campo `abstract` (PRJ-020): «Proyecto orientado a estudiar rubric analysis y su relación con competencias, integrando evidencia institucional y un enfoque de procesamiento de lenguaje natural.»
- `projects.csv` fila 21, campo `general_objective` (PRJ-020): «Desarrollar y evaluar un enfoque de procesamiento de lenguaje natural que permita analizar rubric analysis y generar evidencia útil para competencias.»

**Oportunidad generada:** `RESEARCH_CONTINUITY` — Continuidad de investigación sobre Estrategia basada en procesamiento de lenguaje natural para estudiar rubric analysis (prioridad MEDIUM)

Existen antecedentes terminados (PRJ-020, THS-046, THS-055) que pueden continuarse para atender la consulta recibida. Respaldo recuperado: PRJ-020 (Project), THS-046 (Thesis).

Entidades referenciadas: `PRJ-020`, `THS-046`

Incertidumbre declarada:

- Las conexiones que sustentan esta oportunidad son inferidas por similitud y estructura del grafo; no existen como relación explícita en Data V1.0.
- La consulta no indicó una necesidad institucional: el foco se derivó del texto.
- No se recuperó una capacidad con nivel de madurez declarado.

**Candidatos descartados y por qué:**

- `PRJ-023` (0.45) — Ya se mostraban 2 entidades de tipo Project; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `THS-043` (0.42) — Ya se mostraban 2 entidades de tipo Thesis; la cuota por tipo evita que un solo tipo ocupe toda la respuesta.
- `CAP-088` (0.16) — Penalizada por: Coincidencia débil y sin soporte estructural en el grafo.

---

