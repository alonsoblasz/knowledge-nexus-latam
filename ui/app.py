"""Knowledge Nexus LATAM — interfaz de demostración.

Consume la API del motor híbrido o, si no está disponible, el fixture del
equipo. El cambio entre ambos orígenes se hace por configuración: la interfaz
no conoce Neo4j ni credenciales.

    KNOWLEDGE_NEXUS_DATA_SOURCE=api|fixture
    KNOWLEDGE_NEXUS_API_URL=http://localhost:8000
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SEARCH = ROOT / "artifacts" / "generated" / "team_fixture_search_response.json"
FIXTURE_GRAPH = ROOT / "artifacts" / "generated" / "team_fixture_graph.json"

DEFAULT_QUERY = "¿Qué nueva investigación puede ayudar a prevenir la deserción estudiantil?"
DEFAULT_API_URL = os.environ.get("KNOWLEDGE_NEXUS_API_URL", "http://localhost:8000")
DEFAULT_SOURCE = os.environ.get("KNOWLEDGE_NEXUS_DATA_SOURCE", "api").strip().lower()

TARGET_TYPES = [
    "Project",
    "Thesis",
    "Publication",
    "Researcher",
    "ResearchGroup",
    "Capability",
    "Subject",
]

TYPE_LABELS = {
    "InstitutionalNeed": "Necesidad",
    "Project": "Proyecto",
    "Thesis": "Tesis",
    "Publication": "Publicación",
    "Researcher": "Investigador",
    "ResearchGroup": "Grupo",
    "Capability": "Capacidad",
    "Subject": "Asignatura",
    "Program": "Programa",
    "Faculty": "Facultad",
    "Competency": "Competencia",
    "LearningOutcome": "Resultado de aprendizaje",
    "ResearchLine": "Línea",
    "Expertise": "Expertise",
    "Document": "Documento",
    "FreeTextQuery": "Consulta libre",
}

# Colores por familia de entidad. Siempre acompañados de etiqueta de texto:
# el color nunca es el único portador de la información.
TYPE_COLORS = {
    "InstitutionalNeed": "#E11D48",
    "Project": "#2563EB",
    "Thesis": "#2563EB",
    "Publication": "#2563EB",
    "Researcher": "#059669",
    "ResearchGroup": "#059669",
    "Capability": "#7C3AED",
    "Subject": "#7C3AED",
    "Competency": "#7C3AED",
    "LearningOutcome": "#7C3AED",
    "Program": "#7C3AED",
}
DEFAULT_COLOR = "#64748B"

SIGNAL_LABELS = {
    "semantic": "Semántica",
    "domain": "Dominio",
    "method": "Método",
    "graph": "Grafo",
    "evidence": "Evidencia",
    "actionable": "Accionable",
}

RELATION_LABELS = {
    "RELEVANT_ANTECEDENT": "Antecedente relevante",
    "SEMANTICALLY_RELATED": "Relacionado semánticamente",
    "METHODOLOGICALLY_COMPATIBLE": "Compatible metodológicamente",
    "COMPLEMENTS": "Complementa",
    "CAN_SUPPORT": "Puede dar soporte",
    "CURRICULAR_ALIGNMENT": "Alineación curricular",
    "POTENTIAL_COLLABORATOR": "Colaborador potencial",
}

OPPORTUNITY_LABELS = {
    "NEW_RESEARCH": "Nueva investigación",
    "RESEARCH_CONTINUITY": "Continuidad de investigación",
    "THESIS_TOPIC": "Tema de trabajo de grado",
    "COLLABORATION": "Colaboración",
    "CAPABILITY_ACTIVATION": "Activación de capacidad",
    "CURRICULAR_INTEGRATION": "Integración curricular",
    "KNOWLEDGE_TRANSFER": "Transferencia de conocimiento",
}

st.set_page_config(
    page_title="Knowledge Nexus LATAM",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .kn-title { font-size: 2.1rem; font-weight: 800; margin-bottom: .1rem; }
      .kn-sub { font-size: 1.02rem; color: #64748B; margin-bottom: 1.2rem; }
      .kn-badge { display:inline-block; padding: 3px 9px; border-radius: 5px;
                  font-size: .78rem; font-weight: 700; margin-right: 6px; }
      .kn-explicit { background:#DBEAFE; color:#1E3A8A; border:1px solid #1E3A8A; }
      .kn-inferred { background:#F3E8FF; color:#5B21B6; border:1px dashed #5B21B6; }
      /* Color de texto explícito: el contenedor tiene fondo claro fijo y el
         tema del usuario puede ser oscuro. Sin esto el texto quedaría ilegible. */
      .kn-evidence { background:#FFFBEB; color:#1F2937; border-left:4px solid #D97706;
                     padding:10px 12px; border-radius:4px; margin-bottom:8px; }
      .kn-evidence code { background:#FEF3C7; color:#7C2D12; padding:1px 4px;
                          border-radius:3px; }
      .kn-evidence .kn-quote { font-style: italic; }
      .kn-evidence .kn-prov { font-size:.86rem; color:#57534E; }
      .kn-demo { background:#FEF3C7; border:1px solid #D97706; color:#92400E;
                 padding:8px 12px; border-radius:6px; font-weight:600; }
      .kn-live { background:#DCFCE7; border:1px solid #15803D; color:#14532D;
                 padding:8px 12px; border-radius:6px; font-weight:600; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Cliente: fixture o API, misma forma de respuesta
# --------------------------------------------------------------------------
class ApiError(RuntimeError):
    """Error legible de comunicación con el motor."""


def _post(url: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body
        raise ApiError(f"El motor respondió {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise ApiError(
            f"No se pudo conectar con el motor en {url}. ¿Está levantado? ({error.reason})"
        ) from error
    except TimeoutError as error:
        raise ApiError("El motor tardó demasiado en responder.") from error


def _get(url: str, timeout: int = 15) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001 - se muestra al usuario tal cual
        raise ApiError(f"No se pudo consultar {url}: {error}") from error


def load_fixture() -> dict[str, Any]:
    """Respuesta simulada del equipo, con su subgrafo real de desarrollo."""

    payload = json.loads(FIXTURE_SEARCH.read_text(encoding="utf-8"))
    if FIXTURE_GRAPH.is_file():
        payload["graph"] = json.loads(FIXTURE_GRAPH.read_text(encoding="utf-8"))
    payload.setdefault("meta", {})["source"] = "fixture"
    return payload


def search_api(
    api_url: str, query: str, source_entity_id: str | None, types: list[str], limit: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "target_types": types or None,
        "limit": limit,
        "include_graph": True,
        "include_discarded": True,
    }
    if source_entity_id:
        payload["source_entity_id"] = source_entity_id
    payload = {key: value for key, value in payload.items() if value is not None}
    return _post(f"{api_url.rstrip('/')}/v1/search", payload)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_needs(api_url: str) -> list[dict[str, Any]]:
    return _get(f"{api_url.rstrip('/')}/v1/needs?limit=60").get("needs", [])


# --------------------------------------------------------------------------
# Subgrafo
# --------------------------------------------------------------------------
def render_graph(graph: dict[str, Any], highlight: str | None = None) -> str:
    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    vis_nodes = []
    for node in nodes:
        entity_type = str(node.get("label") or "")
        readable = TYPE_LABELS.get(entity_type, entity_type or "Entidad")
        title = str(node.get("title") or node.get("id"))
        vis_nodes.append(
            {
                "id": node.get("id"),
                "label": f"{node.get('id')}\n{readable}",
                "title": (
                    f"{node.get('id')} · {readable}\n{title}\n"
                    f"Fuente: {node.get('source_file') or 's/d'}"
                    f" fila {node.get('source_row') if node.get('source_row') is not None else 's/d'}"
                ),
                "color": {
                    "background": TYPE_COLORS.get(entity_type, DEFAULT_COLOR),
                    "border": "#0F172A" if node.get("id") == highlight else "#1E293B",
                },
                "borderWidth": 4 if node.get("id") == highlight else 1,
                "shape": "box",
                "font": {"color": "#FFFFFF", "size": 13, "face": "Helvetica"},
            }
        )
    vis_edges = []
    for edge in edges:
        origin = str(edge.get("relation_origin") or "EXPLICIT")
        inferred = origin.startswith("INFERRED")
        vis_edges.append(
            {
                "from": edge.get("source_id"),
                "to": edge.get("target_id"),
                "label": str(edge.get("relationship") or ""),
                "color": {"color": "#7C3AED" if inferred else "#1D4ED8"},
                "dashes": inferred,
                "width": 3 if inferred else 2,
                "arrows": "to",
                "font": {"size": 10, "align": "middle", "color": "#334155"},
                "title": f"{edge.get('relationship')} · {origin}",
            }
        )
    return f"""
    <html><head>
      <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <style>#net {{ width:100%; height:460px; border:1px solid #E2E8F0;
                     border-radius:8px; background:#FFFFFF; }}</style>
    </head><body>
      <div id="net"></div>
      <script>
        var data = {{
          nodes: new vis.DataSet({json.dumps(vis_nodes)}),
          edges: new vis.DataSet({json.dumps(vis_edges)})
        }};
        var network = new vis.Network(document.getElementById('net'), data, {{
          physics: {{ solver: 'forceAtlas2Based',
                      stabilization: {{ iterations: 220 }},
                      forceAtlas2Based: {{ gravitationalConstant: -70,
                                           centralGravity: 0.02, springLength: 120 }} }},
          interaction: {{ hover: true, tooltipDelay: 150, zoomView: true }}
        }});
        // Encuadra el subgrafo completo: si un nodo queda fuera del lienzo el
        // usuario no sabe que existe. Al terminar se apaga la física para que
        // el grafo deje de moverse solo.
        function encuadrar() {{ network.fit({{ animation: false }}); }}
        network.once('stabilizationIterationsDone', function () {{
          network.setOptions({{ physics: false }});
          encuadrar();
        }});
        setTimeout(encuadrar, 900);
        setTimeout(encuadrar, 2000);
        window.addEventListener('resize', encuadrar);
      </script>
    </body></html>
    """


# --------------------------------------------------------------------------
# Barra lateral
# --------------------------------------------------------------------------
st.sidebar.title("Knowledge Nexus")
st.sidebar.caption("LATAM · Conectar el conocimiento institucional")
st.sidebar.divider()

st.sidebar.subheader("Origen de datos")
source_mode = st.sidebar.radio(
    "¿De dónde vienen los resultados?",
    ["API del motor (datos reales)", "Fixture del equipo (simulado)"],
    index=0 if DEFAULT_SOURCE == "api" else 1,
    help="El fixture sirve para desarrollar la interfaz sin depender del motor.",
)
using_api = source_mode.startswith("API")
api_url = DEFAULT_API_URL
if using_api:
    api_url = st.sidebar.text_input("URL del motor", value=DEFAULT_API_URL)
    if st.sidebar.button("Probar conexión", use_container_width=True):
        try:
            health = _get(f"{api_url.rstrip('/')}/health")
            st.sidebar.success(
                f"Conectado · {health['embedding_model']} "
                f"({health['embedding_dimension']}d) · ranking {health['ranking_version']}"
            )
        except ApiError as error:
            st.sidebar.error(str(error))

st.sidebar.divider()
st.sidebar.subheader("Filtros")
selected_types = st.sidebar.multiselect(
    "Tipos de entidad a buscar",
    TARGET_TYPES,
    default=TARGET_TYPES,
    format_func=lambda value: TYPE_LABELS.get(value, value),
    disabled=not using_api,
)
limit = st.sidebar.slider("Número de conexiones", 3, 15, 6, disabled=not using_api)

st.sidebar.divider()
st.sidebar.subheader("Cómo leer los resultados")
st.sidebar.markdown(
    """
**Relevancia**: afinidad del resultado con *esta* consulta.
No mide verdad científica ni aprobación institucional.

**Relación explícita** (línea continua, azul): existe como dato en Data V1.0.

**Relación inferida** (línea discontinua, violeta): la calculó el motor por
similitud y estructura del grafo. Es una hipótesis con evidencia, no un hecho
administrativo.
"""
)
st.sidebar.caption(
    "Colores del grafo: rojo = necesidad · azul = proyecto, tesis o publicación · "
    "verde = investigador o grupo · violeta = capacidad o currículo · gris = otros. "
    "Cada nodo lleva además su tipo escrito."
)


# --------------------------------------------------------------------------
# Encabezado y buscador
# --------------------------------------------------------------------------
st.markdown('<div class="kn-title">Knowledge Nexus LATAM</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="kn-sub">Encuentra qué investigación, personas, capacidades y currículo '
    "de la universidad pueden responder a una necesidad institucional, y explica por qué.</div>",
    unsafe_allow_html=True,
)

needs: list[dict[str, Any]] = []
if using_api:
    try:
        needs = fetch_needs(api_url)
    except ApiError:
        needs = []

col_query, col_need = st.columns([3, 2])
with col_query:
    query = st.text_input(
        "Pregunta o necesidad en tus palabras",
        value=st.session_state.get("query", DEFAULT_QUERY),
        placeholder="Ej.: ¿qué capacidades tenemos para monitorear la calidad del agua?",
    )
with col_need:
    options = ["(ninguna)"] + [f"{item['id']} — {item['title']}" for item in needs]
    need_choice = st.selectbox(
        "Necesidad institucional (opcional)",
        options,
        index=1 if len(options) > 1 else 0,
        help="Aporta el contexto institucional de la necesidad a la búsqueda.",
    )
source_entity_id = None if need_choice == "(ninguna)" else need_choice.split(" — ")[0]

buscar = st.button("Buscar conexiones", type="primary", use_container_width=True)

if buscar:
    st.session_state["query"] = query
    if using_api:
        with st.spinner("Consultando el motor: embeddings, grafo y ranking…"):
            try:
                st.session_state["response"] = search_api(
                    api_url, query, source_entity_id, selected_types, limit
                )
                st.session_state["error"] = None
            except ApiError as error:
                # La consulta del usuario no se pierde ante un error del backend.
                st.session_state["error"] = str(error)
    else:
        st.session_state["response"] = load_fixture()
        st.session_state["error"] = None

response: dict[str, Any] | None = st.session_state.get("response")
error: str | None = st.session_state.get("error")

if error:
    st.error(error)
    st.info(
        "Tu consulta sigue escrita arriba. Puedes reintentar, o cambiar el origen de "
        "datos a «Fixture del equipo» en la barra lateral para seguir explorando la interfaz."
    )

if response is None:
    st.info(
        "Escribe una pregunta y pulsa **Buscar conexiones**. "
        "La consulta de ejemplo ya está cargada: la necesidad habla de «deserción "
        "estudiantil» y el proyecto que mejor responde habla de *student attrition*."
    )
    st.stop()


# --------------------------------------------------------------------------
# Resultados
# --------------------------------------------------------------------------
is_fixture = bool(response.get("fixture_only"))
if is_fixture:
    st.markdown(
        '<div class="kn-demo">⚠️ Resultado simulado: proviene del fixture de '
        "desarrollo, no del motor. Los scores son ilustrativos.</div>",
        unsafe_allow_html=True,
    )
else:
    meta = response.get("meta", {})
    st.markdown(
        f'<div class="kn-live">✅ Resultado real del motor · modelo '
        f'{meta.get("embedding_model", "s/d")} · ranking {meta.get("ranking_version", "s/d")} '
        f'· {meta.get("latency_ms", "?")} ms</div>',
        unsafe_allow_html=True,
    )

st.caption(response.get("warning", ""))

confidence = response.get("confidence") or {}
if confidence.get("level") == "baja":
    st.warning(f"**{confidence['label']}.** {confidence['message']}")
elif confidence.get("level") == "media":
    st.info(f"**{confidence['label']}.** {confidence['message']}")
elif confidence.get("level") == "alta":
    st.caption(f"✓ {confidence['label']}. {confidence['message']}")

query_entity = response.get("query_entity") or {}
connections = response.get("connections") or []
opportunities = response.get("opportunities") or []
discarded = response.get("discarded") or []

if not connections:
    st.warning("Sin resultados con evidencia verificable para esta consulta.")
    st.write(response.get("meta", {}).get("reason", ""))
    st.info(
        "Prueba con otros términos, amplía los tipos de entidad en la barra lateral "
        "o quita la necesidad seleccionada."
    )
    st.stop()

head_1, head_2, head_3 = st.columns(3)
head_1.metric("Conexiones mostradas", len(connections))
head_2.metric("Relevancia máxima", f"{connections[0]['relevance']['total']:.2f}")
head_3.metric("Oportunidades", len(opportunities))

if query_entity.get("id"):
    st.caption(
        f"Consulta anclada en **{query_entity['id']}** · "
        f"{TYPE_LABELS.get(query_entity.get('type'), query_entity.get('type'))} · "
        f"{query_entity.get('title')}"
    )

tab_rank, tab_graph, tab_opps, tab_why, tab_diag = st.tabs(
    ["Conexiones", "Subgrafo", "Oportunidades", "Por qué otras no", "Diagnóstico"]
)

# --- Conexiones ------------------------------------------------------------
with tab_rank:
    for position, connection in enumerate(connections, start=1):
        target = connection["target"]
        relevance = connection["relevance"]
        origin = str(connection.get("relation_origin", "INFERRED"))
        inferred = origin.startswith("INFERRED")
        badge = (
            '<span class="kn-badge kn-inferred">Inferida</span>'
            if inferred
            else '<span class="kn-badge kn-explicit">Explícita</span>'
        )
        readable_type = TYPE_LABELS.get(target.get("type"), target.get("type"))
        with st.expander(
            f"{position}. [{target['id']}] {target['title']}  ·  "
            f"{readable_type}  ·  relevancia {relevance['total']:.2f}",
            expanded=(position == 1),
        ):
            st.markdown(
                f"{badge}"
                f'<span class="kn-badge" style="background:#F1F5F9;color:#0F172A;">'
                f"{RELATION_LABELS.get(connection['relation'], connection['relation'])}</span>"
                f'<span class="kn-badge" style="background:#F1F5F9;color:#0F172A;">'
                f"{readable_type}</span>",
                unsafe_allow_html=True,
            )
            st.write(connection.get("explanation", ""))

            st.markdown("**Desglose de la relevancia**")
            signal_columns = st.columns(6)
            for column, name in zip(signal_columns, SIGNAL_LABELS, strict=False):
                value = relevance.get(name)
                if value is None:
                    column.caption(f"{SIGNAL_LABELS[name]}: s/d")
                    continue
                column.progress(min(float(value), 1.0), text=f"{SIGNAL_LABELS[name]} {value:.2f}")
            weights = relevance.get("weights")
            if weights:
                st.caption(
                    "Pesos: "
                    + " · ".join(
                        f"{SIGNAL_LABELS.get(key, key)} {value:g}" for key, value in weights.items()
                    )
                    + f" · versión {relevance.get('ranking_version', 's/d')}"
                )
            for penalty in relevance.get("penalties", []) or []:
                st.warning(f"Penalización −{penalty['value']:.2f}: {penalty['reason']}")

            st.markdown("**Evidencia y procedencia**")
            for item in connection.get("evidence", []):
                st.markdown(
                    f'<div class="kn-evidence">'
                    f'<span class="kn-quote">«{item.get("excerpt", "")}»</span><br><br>'
                    f'<span class="kn-prov">Archivo <code>{item.get("file")}</code> · '
                    f'fila <code>{item.get("row")}</code> · '
                    f'campo <code>{item.get("field")}</code> · '
                    f'registro <code>{item.get("record_id")}</code></span></div>',
                    unsafe_allow_html=True,
                )
            detail = connection.get("components_detail")
            if detail:
                with st.expander("Ver el cálculo señal por señal"):
                    st.json(detail, expanded=False)

# --- Subgrafo --------------------------------------------------------------
with tab_graph:
    graph = response.get("graph")
    if not graph or not graph.get("nodes"):
        st.info("Esta respuesta no incluye subgrafo.")
    else:
        st.caption(
            "Línea continua azul: relación explícita registrada en Data V1.0. "
            "Línea discontinua violeta: relación inferida por el motor. "
            "Pasa el cursor sobre un nodo para ver su ID, tipo y procedencia."
        )
        ids = [connection["target"]["id"] for connection in connections]
        highlight = st.selectbox("Destacar una entidad", ["(ninguna)"] + ids)
        components.html(
            render_graph(graph, None if highlight == "(ninguna)" else highlight),
            height=480,
        )
        explicit = sum(
            1 for edge in graph["edges"] if not str(edge.get("relation_origin", "")).startswith("INFERRED")
        )
        st.caption(
            f"{len(graph['nodes'])} nodos · {explicit} relaciones explícitas · "
            f"{len(graph['edges']) - explicit} inferidas."
        )
        with st.expander("Ver las relaciones en tabla (sin usar el grafo)"):
            st.dataframe(
                [
                    {
                        "Origen": edge["source_id"],
                        "Relación": edge["relationship"],
                        "Destino": edge["target_id"],
                        "Tipo de relación": edge.get("relation_origin"),
                    }
                    for edge in graph["edges"]
                ],
                use_container_width=True,
                hide_index=True,
            )

# --- Oportunidades ---------------------------------------------------------
with tab_opps:
    if not opportunities:
        st.info("No se generaron oportunidades con respaldo suficiente para esta consulta.")
    for opportunity in opportunities:
        st.success(
            f"**{opportunity['title']}** · "
            f"{OPPORTUNITY_LABELS.get(opportunity['type'], opportunity['type'])} · "
            f"prioridad {opportunity['priority']}"
        )
        st.write(opportunity["reason"])
        st.markdown("**Entidades que la sustentan**")
        st.dataframe(
            [
                {
                    "ID": entity["id"],
                    "Tipo": TYPE_LABELS.get(entity.get("type"), entity.get("type")),
                    "Título": entity.get("title"),
                }
                for entity in opportunity["related_entities"]
            ],
            use_container_width=True,
            hide_index=True,
        )
        for note in opportunity.get("uncertainty", []) or []:
            st.caption(f"Incertidumbre declarada: {note}")
        if opportunity.get("disclaimer"):
            st.caption(opportunity["disclaimer"])
        st.divider()

# --- Por qué otras no ------------------------------------------------------
with tab_why:
    if not discarded:
        st.info(
            "Este origen de datos no informa candidatos descartados. "
            "Cambia a la API del motor para verlos."
        )
    else:
        st.caption(
            "El motor evaluó muchos más candidatos de los que muestra. "
            "Estos quedaron fuera, y por qué."
        )
        for item in discarded:
            etiqueta = (
                "Quedó cerca"
                if item.get("kind") == "quedo_cerca"
                else "Descartado con claridad"
            )
            with st.expander(
                f"[{item['id']}] {item['title']} · {etiqueta} · relevancia {item['total']:.2f}"
            ):
                st.write(item["reason"])
                st.caption(
                    "Señal más débil: "
                    f"{SIGNAL_LABELS.get(item['weakest_signal']['name'], item['weakest_signal']['name'])}"
                    f" ({item['weakest_signal']['value']:.2f})"
                )
                st.dataframe(
                    [
                        {
                            SIGNAL_LABELS.get(key, key): f"{value:.2f}"
                            for key, value in item["relevance"].items()
                        }
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

# --- Diagnóstico -----------------------------------------------------------
with tab_diag:
    meta = response.get("meta", {})
    if not meta:
        st.info("El fixture no trae diagnóstico del motor.")
    else:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Latencia", f"{meta.get('latency_ms', '?')} ms")
        col_b.metric("Candidatos evaluados", meta.get("candidates_evaluated", "?"))
        col_c.metric("Modelo", meta.get("embedding_model", "s/d"))
        retrieval = meta.get("retrieval", {})
        if retrieval.get("by_channel"):
            st.markdown("**Candidatos aportados por cada canal de recuperación**")
            st.dataframe(
                [
                    {
                        "Canal vectorial": retrieval["by_channel"].get("vector"),
                        "Canal léxico (BM25)": retrieval["by_channel"].get("lexical"),
                        "Expansión de grafo": retrieval["by_channel"].get("graph"),
                    }
                ],
                use_container_width=True,
                hide_index=True,
            )
        query_info = response.get("query", {})
        if query_info:
            st.markdown("**Cómo interpretó el motor la consulta**")
            st.json(query_info, expanded=False)
        st.markdown("**Metadatos completos**")
        st.json(meta, expanded=False)
