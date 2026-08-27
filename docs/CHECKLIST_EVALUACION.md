# Checklist previo a la evaluación

Dónde se cumple cada punto y **cómo comprobarlo**. Cada fila remite a algo
ejecutable o a una línea concreta del repositorio, no a una afirmación.

## Checklist

| # | Pregunta | Estado | Dónde verificarlo |
|---|---|---|---|
| 1 | ¿Procesa realmente Data V1.0 y no solo ejemplos manuales? | ✅ | Los 22 CSV originales están en `data/`. De ahí salen 3.327 nodos, 6.353 aristas y 3.292 documentos con embeddings. `make embeddings` lo reconstruye. Ninguna respuesta está precargada. |
| 2 | ¿Al menos una conexión no trivial entre fuentes diferentes? | ✅ | `NEED-001` («deserción estudiantil», `institutional_needs.csv`) → `PRJ-002` («student attrition», `projects.csv`). Sin una palabra en común. Caso 1 de `docs/CASOS_DEMOSTRABLES.md`; prueba `test_conexion_no_literal_encontrada`. |
| 3 | ¿Podemos explicar por qué una conexión es relevante y por qué otra no? | ✅ | Cada conexión trae el desglose de las 6 señales, los pesos y las penalizaciones. Cada respuesta trae además `discarded`: candidatos descartados con el motivo. Pestaña «Por qué otras no» de la interfaz. |
| 4 | ¿Existe un mecanismo de priorización o valoración? | ✅ | Ranking versionado de seis señales con penalizaciones, en `config/ranking.yaml` y `src/knowledge_nexus_retrieval/ranking/`. Documentado en `docs/RANKING.md`. |
| 5 | ¿Podemos llegar de una recomendación al archivo y registro que la sustenta? | ✅ | Cada elemento de evidencia lleva archivo, fila, campo y fragmento; por ejemplo `projects.csv` fila 3, campo `problem_statement`. Trazabilidad completa medida: **1.000**. |
| 6 | ¿Las oportunidades se derivan de la evidencia institucional? | ✅ | Se generan por reglas deterministas sobre las entidades recuperadas y se validan con `IdentifierGuard`: una oportunidad que cite un ID inexistente lanza error. Prueba `test_oportunidades_validas_y_trazables`. |
| 7 | ¿Conexiones con investigación, capacidades y currículo? | ✅ | Los tipos por defecto incluyen proyecto, tesis, publicación, investigador, grupo, capacidad y asignatura, con cuota por tipo para que no domine uno solo. Caso 3 de `docs/CASOS_DEMOSTRABLES.md`. |
| 8 | ¿Funciona end-to-end con una consulta nueva? | ✅ | La interfaz acepta texto libre. Probado en vivo con calidad del agua, fraude financiero y mantenimiento predictivo, dominios distintos al de la demostración. |
| 9 | ¿La arquitectura mostrada corresponde a lo implementado? | ✅ | `docs/ARQUITECTURA.md` mapea cada caja del diagrama a su módulo real e incluye una tabla explícita de **diferencias con el diseño original**. |
| 10 | ¿El README permite comprender y ejecutar la solución? | ✅ | `README.md`: descripción, arquitectura, tecnologías, instalación, reproducción de la demo, mecanismo de descubrimiento y priorización, y limitaciones. Comandos en un `Makefile`. |
| 11 | ¿Declaramos modelos, APIs y componentes externos? | ✅ | `docs/COMPONENTES_EXTERNOS.md`, con versiones, licencias, dónde se ejecuta cada cosa y las herramientas generativas usadas en el desarrollo. |
| 12 | ¿Explicamos limitaciones sin afirmar más de lo que los datos permiten? | ✅ | Sección «Limitaciones» del README; disclaimer en cada score y cada oportunidad; incertidumbre declarada; y un nivel de **confianza** que marca la respuesta como poco fiable cuando la consulta no tiene respuesta real. |

## Errores que reducen el valor de una propuesta

| Error a evitar | Cómo lo evitamos |
|---|---|
| Solo un buscador por palabras clave, sin relacionar ni priorizar | BM25 es únicamente uno de tres canales. Sobre él hay expansión de grafo y un ranking de seis señales. La conexión estrella es precisamente la que las palabras clave **no** encuentran. |
| Recomendaciones con IA sin evidencia rastreable | El paquete de evidencia se cierra **antes** de redactar. Una conexión sin evidencia no se muestra. El LLM está desactivado por defecto y, si se activa, su texto se descarta cuando cita un ID inexistente. |
| Muchas coincidencias sin distinguir relevancia | Cuota por tipo, umbral de calidad, penalización por redundancia y desglose visible. Se muestran 5–6 resultados de entre ~400 candidatos evaluados. |
| Arquitectura ideal que no corresponde al prototipo | El diagrama es *as-built* y las diferencias con el diseño original están listadas una a una. |
| Un score sin explicar su significado ni su origen | Cada respuesta trae pesos, contribución de cada señal, penalizaciones, versión del ranking y la frase de interpretación. La calibración del coseno se midió sobre este corpus y está documentada. |
| Depender de ejemplos precargados | No hay respuestas precargadas: solo embeddings precalculados. Cualquier pregunta nueva se codifica y recorre el mismo camino. |
| Confundir una visualización atractiva con la solución | La interfaz consume la API real; una prueba automatizada verifica que no vuelva a atarse a un contrato inventado. El motor funciona sin interfaz, por CLI y por HTTP. |

## Comprobación rápida antes de presentar

```bash
make test        # 74 pruebas en ~15 s
make evaluate    # métricas del conjunto de revisión
make demo        # regenera los casos con salida real
make api         # terminal 1
make ui          # terminal 2
```

Si las cuatro primeras terminan sin error y la interfaz responde a una pregunta
inventada en el momento, el prototipo está listo.
