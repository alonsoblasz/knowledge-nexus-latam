import os
import json
import urllib.parse
import urllib.request
import urllib.error
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

# ==========================================
# 1. CONFIGURACIÓN INICIAL DE STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Knowledge Nexus LATAM - UI Persona 3",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para mejorar legibilidad y acabado profesional
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .card-metric {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
    }
    .badge-explicit {
        background-color: #DBEAFE;
        color: #1E40AF;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-inferred {
        background-color: #F3E8FF;
        color: #6B21A8;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .evidence-box {
        background-color: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.9rem;
        margin-top: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. CARGA DE FIXTURES Y CONEXIÓN CON API
# ==========================================
FIXTURE_SEARCH_PATH = "persona_3_interfaz/team_fixture_search_response.json"
FIXTURE_GRAPH_PATH = "persona_3_interfaz/team_fixture_graph.json"

@st.cache_data
def load_fixture(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def fetch_api_data(endpoint, params=None, api_url="http://127.0.0.1:5000"):
    """Petición limpia utilizando urllib nativo de Python para evitar dependencias externas."""
    try:
        url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"
            
        req = urllib.request.Request(url, headers={"User-Agent": "Streamlit-Persona3"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = response.read().decode('utf-8')
                return json.loads(data), True
    except Exception as e:
        return str(e), False
    return "Error desconocido al conectar a la API", False


# ==========================================
# 3. MOTOR DE RENDERING DE GRAFOS (Pyvis HTML)
# ==========================================
def render_pyvis_subgraph(graph_data, highlight_target_id=None):
    """
    Construye un grafo visual interactivo en Vis.js a partir del JSON de subgrafo.
    Diferencia nodos objetivo y distingue aristas Explícitas vs Inferidas.
    """
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    
    vis_nodes = []
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type", "entity").upper()
        label = f"{node.get('label', node_id)}\n({node_type})"
        
        # Color por tipo de entidad o foco
        color = "#94A3B8" # Gris por defecto
        if node_id == graph_data.get("center_node"):
            color = "#EF4444" # Rojo para el origen
        elif node_id == highlight_target_id:
            color = "#10B981" # Verde para el destino seleccionado
        elif "NEED" in node_id:
            color = "#F59E0B"
        elif "PRJ" in node_id or "PROJECT" in node_type:
            color = "#3B82F6"
        elif "INV" in node_id or "RESEARCHER" in node_type:
            color = "#8B5CF6"
            
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "color": color,
            "shape": "box",
            "font": {"color": "#FFFFFF", "face": "Arial"}
        })
        
    vis_edges = []
    for edge in edges:
        is_explicit = edge.get("nature") == "explicit" or edge.get("is_explicit", True)
        
        # Estilo según naturaleza de la relación
        edge_color = "#3B82F6" if is_explicit else "#8B5CF6"
        dashes = False if is_explicit else True
        width = 2 if is_explicit else 3
        
        vis_edges.append({
            "from": edge.get("source") or edge.get("from"),
            "to": edge.get("target") or edge.get("to"),
            "label": edge.get("relation", edge.get("label", "")),
            "color": {"color": edge_color},
            "dashes": dashes,
            "width": width,
            "font": {"size": 10, "align": "middle"}
        })
        
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <style type="text/css">
        #network {{
          width: 100%;
          height: 420px;
          border: 1px solid #E2E8F0;
          background-color: #FAFAFA;
          border-radius: 8px;
        }}
      </style>
    </head>
    <body>
    <div id="network"></div>
    <script type="text/javascript">
      var container = document.getElementById('network');
      var data = {{
        nodes: new vis.DataSet({json.dumps(vis_nodes)}),
        edges: new vis.DataSet({json.dumps(vis_edges)})
      }};
      var options = {{
        physics: {{
          enabled: true,
          solver: 'forceAtlas2Based',
          forceAtlas2Based: {{ gravitationalConstant: -50, centralGravity: 0.01, springLength: 100 }}
        }},
        interaction: {{ hover: true, tooltipDelay: 200 }}
      }};
      var network = new vis.Network(container, data, options);
    </script>
    </body>
    </html>
    """
    return html_code


# ==========================================
# 4. BARRA LATERAL (SIDEBAR DE CONTROL)
# ==========================================
st.sidebar.image("https://img.icons8.com/fluency/96/network.png", width=60)
st.sidebar.title("Knowledge Nexus")
st.sidebar.caption("LATAM | Conectar el Conocimiento")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Configuración de Origen")

data_source = st.sidebar.radio(
    "Fuente de Datos:",
    ["Fixtures / Mocks Locales", "API REST Persona 2"],
    help="Elige si deseas probar con datos estáticos de desarrollo o conectarte a la API en vivo de la Persona 2."
)

api_base_url = "http://127.0.0.1:5000"
if data_source == "API REST Persona 2":
    api_base_url = st.sidebar.text_input("URL base API Flask:", value="http://127.0.0.1:5000")
    if st.sidebar.button("🔌 Probar Conexión API"):
        res, ok = fetch_api_data("health", api_url=api_base_url)
        if ok:
            st.sidebar.success("Conexión exitosa con API Persona 2")
        else:
            st.sidebar.error(f"Falló conexión: {res}")

st.sidebar.markdown("---")
st.sidebar.info("""
**Leyenda de Relaciones:**
- 🔵 **Sólida / Azul:** Relación Explícita (IDs / Tablas directas)
- 🟣 **Punteada / Púrpura:** Relación Inferida (Descubrimiento Semántico / NLP)
""")


# ==========================================
# 5. ENCABEZADO PRINCIPAL
# ==========================================
st.markdown('<div class="main-title">Knowledge Nexus LATAM</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Motor Inteligente de Gestión y Descubrimiento de Conocimiento Institucional</div>', unsafe_allow_html=True)


# ==========================================
# 6. MÓDULO DE BÚSQUEDA Y SELECCIÓN DE ORIGEN
# ==========================================
col_search, col_type = st.columns([3, 1])

with col_search:
    search_query = st.text_input(
        "🔎 Ingrese ID de origen (ej. NEED-001, PRJ-002) o consulta temática:",
        value="NEED-001",
        placeholder="Ej: NEED-001 o 'optimización de energía en laboratorios'"
    )

with col_type:
    entity_filter = st.selectbox(
        "Filtrar Entidad:",
        ["Todas", "Necesidad (NEED)", "Proyecto (PRJ)", "Tesis (THS)", "Investigador (INV)"]
    )

btn_buscar = st.button("🚀 Ejecutar Descubrimiento de Conexiones", type="primary", use_container_width=True)

# Lógica para obtener los datos de la búsqueda
search_results = None
graph_data = None

if btn_buscar or "search_results" in st.session_state:
    if data_source == "Fixtures / Mocks Locales":
        search_results = load_fixture(FIXTURE_SEARCH_PATH)
        graph_data = load_fixture(FIXTURE_GRAPH_PATH)
        st.session_state["search_results"] = search_results
        st.session_state["graph_data"] = graph_data
    else:
        with st.spinner("Consultando API de Persona 2 y calculando re-ranking..."):
            res_search, ok_search = fetch_api_data("search", params={"q": search_query}, api_url=api_base_url)
            res_graph, ok_graph = fetch_api_data("graph", params={"id": search_query}, api_url=api_base_url)
            
            if ok_search and ok_graph:
                search_results = res_search
                graph_data = res_graph
                st.session_state["search_results"] = search_results
                st.session_state["graph_data"] = graph_data
            else:
                st.error("⚠️ No se pudo obtener respuesta de la API. Se cargarán fixtures de contingencia.")
                search_results = load_fixture(FIXTURE_SEARCH_PATH)
                graph_data = load_fixture(FIXTURE_GRAPH_PATH)


# ==========================================
# 7. DESPLEGABLE Y PRESENTACIÓN DE RESULTADOS
# ==========================================
if search_results and "results" in search_results:
    st.markdown("---")
    
    # Metadatos generales de la consulta
    origin_info = search_results.get("source_entity", {})
    results_list = search_results.get("results", [])
    
    st.subheader(f"📌 Entidad Origen Analizada: `{origin_info.get('id', search_query)}`")
    st.caption(f"**Descripción/Título:** {origin_info.get('title', 'Sin título registrado')}")

    # Métricas de la búsqueda
    m1, m2, m3 = st.columns(3)
    m1.metric("Conexiones Identificadas", len(results_list))
    m2.metric("Puntaje Máximo de Pertinencia", f"{results_list[0].get('priority_score', 0):.2f}" if results_list else "0.00")
    m3.metric("Oportunidades Generadas", len([r for r in results_list if r.get('opportunity')]))

    # PESTAÑAS PRINCIPALES DE NAVEGACIÓN
    tab_ranking, tab_graph, tab_opportunities = st.tabs([
        "🏆 Ranking y Desglose de Conexiones", 
        "🕸️ Subgrafo Interactivo de Red", 
        "💡 Oportunidades Propuestas"
    ])

    # ----------------------------------------------------
    # PESTAÑA 1: RANKING Y DESGLOSE DE CONEXIONES
    # ----------------------------------------------------
    with tab_ranking:
        st.write("##### Conexiones Priorizadas por Re-ranking y Relevancia Semántica")
        
        for idx, item in enumerate(results_list, start=1):
            target = item.get("target", {})
            score = item.get("priority_score", 0.0)
            nature = item.get("nature", "inferred") # explicit | inferred
            explanation = item.get("explanation", "Sin explicación disponible")
            evidence = item.get("evidence", {})
            provenance = item.get("provenance", {})
            
            is_explicit = nature == "explicit"
            badge_html = '<span class="badge-explicit">🔗 Explícita</span>' if is_explicit else '<span class="badge-inferred">🧠 Inferida (NLP)</span>'
            
            with st.expander(f"#{idx} | [{target.get('id')}] {target.get('title')} — Score: {score:.2f}", expanded=(idx == 1)):
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    st.markdown(f"**Relación:** `{item.get('relation_type', 'Relacionado')}` | {badge_html}", unsafe_allow_html=True)
                    st.write(f"**Tipo Entidad Destino:** {target.get('type', 'Desconocido').upper()}")
                with c_head2:
                    st.progress(min(float(score), 1.0), text=f"Prioridad: {score:.0%}")
                
                st.markdown("#### 💬 Explicación del Motor:")
                st.write(explanation)
                
                st.markdown("#### 🔍 Inspección de Evidencia y Trazabilidad (Contrato de Datos):")
                st.markdown(f"""
                <div class="evidence-box">
                    <b>Texto Literal Extraído:</b> "{evidence.get('text', 'Evidencia no provista')}"<br><br>
                    <b>📌 Trazabilidad Fuente:</b><br>
                    - <b>Archivo:</b> <code>{provenance.get('file', 'N/A')}</code><br>
                    - <b>Registro ID:</b> <code>{provenance.get('record_id', 'N/A')}</code><br>
                    - <b>Campo:</b> <code>{provenance.get('field', 'N/A')}</code>
                </div>
                """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # PESTAÑA 2: VISUALIZACIÓN DEL SUBGRAFO INTERACTIVO
    # ----------------------------------------------------
    with tab_graph:
        st.write("##### Representación de Red de Conocimiento Local")
        st.caption("Los nodos representan entidades. Las aristas sólidas son relaciones explícitas (tablas/IDs); las punteadas son inferidas mediante Inteligencia Artificial.")
        
        if graph_data:
            # Selector para destacar una conexión en el grafo
            target_ids = [r.get("target", {}).get("id") for r in results_list if r.get("target", {}).get("id")]
            selected_highlight = st.selectbox("🎯 Enfocar Entidad Destino en el Grafo:", ["Ninguno"] + target_ids)
            
            highlight_id = None if selected_highlight == "Ninguno" else selected_highlight
            graph_html = render_pyvis_subgraph(graph_data, highlight_target_id=highlight_id)
            components.html(graph_html, height=450)
        else:
            st.warning("No se encontró estructura de subgrafo para esta consulta.")

    # ----------------------------------------------------
    # PESTAÑA 3: OPORTUNIDADES PROPUESTAS Y ACCIONABLES
    # ----------------------------------------------------
    with tab_opportunities:
        st.write("##### Oportunidades Estratégicas Institucionales Generadas")
        st.caption("Propuestas concretas derivadas del cruce de antecedentes, capacidades, docentes y componentes curriculares.")
        
        has_opps = False
        for item in results_list:
            opp = item.get("opportunity")
            if opp:
                has_opps = True
                target = item.get("target", {})
                
                with st.container():
                    st.success(f"💡 **Oportunidad:** {opp.get('title', 'Propuesta de Colaboración')}")
                    
                    o_col1, o_col2 = st.columns([2, 1])
                    with o_col1:
                        st.write(f"**Categoría:** `{opp.get('category', 'Acción Institucional')}`")
                        st.write(f"**Descripción:** {opp.get('description', 'Sin detalle')}")
                    with o_col2:
                        st.write(f"**Entidades Vinculadas:** `{search_query}` ↔ `{target.get('id')}`")
                        st.write(f"**Impacto Esperado:** {opp.get('expected_impact', 'Alto valor académico')}")
                    st.markdown("---")
                    
        if not has_opps:
            st.info("No se formularon oportunidades automáticas para los resultados de menor relevancia.")

else:
    # Estado inicial cuando no se ha ejecutado una búsqueda
    st.info("👈 Ingrese un código de origen (como `NEED-001`) y presione **'Ejecutar Descubrimiento de Conexiones'** para comenzar el análisis.")