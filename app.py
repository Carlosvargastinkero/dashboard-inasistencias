import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import io
import os
import re

st.set_page_config(page_title="La Tinka - Control de Inasistencias", layout="wide", initial_sidebar_state="collapsed")

# --- INYECCIÓN CSS: MODO CLARO Y PALETA LA TINKA ---
st.markdown("""
<style>
    /* 1. Fondo General Beige */
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #F5F0D4 !important;
        color: #000000 !important;
    }
    
    /* 2. Textos y Etiquetados Generales */
    p, label, span, div {
        color: #000000 !important;
    }
    
    /* 3. Encabezados en Verde Oscuro Tinka */
    h1, h2, h3, h4, h5, h6 {
        color: #096045 !important;
        font-weight: 800 !important;
    }
    
    /* 4. Etiqueta sobre los Listados Desplegables (Contraste) */
    label[data-testid="stWidgetLabel"] p {
        color: #096045 !important;
        font-weight: bold !important;
        font-size: 1.05rem !important;
    }
    
    /* 5. Cajas de Selección (Selectbox) en Fondo Blanco y Texto Oscuro */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 2px solid #096045 !important;
        border-radius: 8px !important;
        color: #000000 !important;
    }
    div[data-baseweb="select"] * {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }
    
    /* 6. Tarjetas de Métricas (KPIs) */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        padding: 12px 16px !important;
        border-radius: 10px !important;
        border-left: 6px solid #096045 !important;
        box-shadow: 0px 2px 6px rgba(0,0,0,0.08);
    }
    [data-testid="stMetricLabel"] p {
        color: #096045 !important;
        font-weight: bold !important;
    }
    [data-testid="stMetricValue"] div {
        color: #000000 !important;
        font-weight: 800 !important;
    }

    /* 7. Desplegables / Acordeones ("Recibe un consejo experto") */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 2px solid #096045 !important;
        border-radius: 10px !important;
    }
    div[data-testid="stExpander"] summary p {
        color: #096045 !important;
        font-weight: bold !important;
        font-size: 1.05rem !important;
    }

    /* 8. Botones en Verde Tinka con Hover Naranja Te Apuesto */
    div.stButton > button, div.stDownloadButton > button {
        background-color: #096045 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: bold !important;
        width: 100% !important;
        padding: 10px 16px !important;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
        background-color: #FF6700 !important;
        color: #FFFFFF !important;
    }

    /* 9. Tabla / Dataframe en Fondo Claro */
    [data-testid="stDataFrame"] {
        background-color: #FFFFFF !important;
        border: 1px solid #096045 !important;
        border-radius: 8px !important;
    }

    /* Menú lateral */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

# --- ENCABEZADO CON LOGO OPTIMIZADO PARA MÓVIL ---
if os.path.exists("logo.png"):
    st.image("logo.png", width=220)
else:
    st.markdown("<h2 style='color:#096045;'>🎯 La Tinka Agente</h2>", unsafe_allow_html=True)

st.title("Control de Inasistencia Conferencia Carlos Mazzetti")

# Autenticación de API Key
api_key = st.secrets.get("GEMINI_API_KEY", None)

st.sidebar.header("⚙️ Administración")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")

uploaded_file = st.sidebar.file_uploader("Actualizar Base Excel (.xlsx)", type=["xlsx"])

file_to_load = None
if uploaded_file:
    file_to_load = uploaded_file
elif os.path.exists("data.xlsx"):
    file_to_load = "data.xlsx"

if file_to_load:
    xls = pd.ExcelFile(file_to_load)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1) if len(xls.sheet_names) > 1 else pd.DataFrame()

    def extraer_fecha_orden(titulo):
        match = re.search(r'(\d{2}/\d{2})', str(titulo))
        if match:
            dia, mes = map(int, match.group(1).split('/'))
            return (mes, dia)
        return (0, 0)

    def acortar_titulo(titulo):
        return str(titulo).split(':')[0].strip() if ':' in str(titulo) else str(titulo)

    agentes_col = 'AGENTE' if 'AGENTE' in data_df.columns else data_df.columns[0]
    conteo_agentes_global = data_df[agentes_col].value_counts()
    agentes_recurrentes_set = set(conteo_agentes_global[conteo_agentes_global > 1].index)

    # --- FILTROS PRINCIPALES ---
    col_conf, col_terr = st.columns([1, 1])

    if 'post_titulo' in data_df.columns:
        conferencias_raw = data_df['post_titulo'].dropna().unique().tolist()
        conferencias_ordenadas = sorted(conferencias_raw, key=extraer_fecha_orden, reverse=True)
        opciones_conf = conferencias_ordenadas + ["Todas las Conferencias (Histórico)"]
    else:
        opciones_conf = ["Todas"]

    with col_conf:
        selected_conf = st.selectbox("📅 Seleccionar Conferencia:", opciones_conf, index=0)

    if selected_conf != "Todas las Conferencias (Histórico)" and 'post_titulo' in data_df.columns:
        df_conf = data_df[data_df['post_titulo'] == selected_conf].copy()
    else:
        df_conf = data_df.copy()

    territoriales = data_df['TERRITORIAL'].dropna().unique()
    with col_terr:
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", territoriales)

    df_terr = df_conf[df_conf['TERRITORIAL'] == selected_terr].copy()
    df_terr_historico = data_df[data_df['TERRITORIAL'] == selected_terr].copy()

    # Ranking
    ranking_terr_df = df_conf.groupby('TERRITORIAL').size().reset_index(name='Inasistencias').sort_values(by='Inasistencias', ascending=True).reset_index(drop=True)
    try:
        rank_terr = ranking_terr_df[ranking_terr_df['TERRITORIAL'] == selected_terr].index[0] + 1
    except IndexError:
        rank_terr = 99

    if rank_terr == 1:
        encabezado_terr = f"Felicidades {selected_terr} estás ocupando el 1er lugar. Para mantenerte cómo el líder de los territoriales deberás mejorar las siguientes oportunidades:"
    elif rank_terr in [2, 3]:
        encabezado_terr = f"Felicidades {selected_terr} estás ocupando el {rank_terr}º lugar. Para seguir escalando al primer lugar, deberás tener en cuenta los siguientes puntos:"
    else:
        encabezado_terr = f"Líder {selected_terr}, actualmente te ubicas en la posición {rank_terr}º entre los territoriales. Analicemos las oportunidades clave de mejora:"

    with st.expander("💡 Recibe un consejo experto (Líder Territorial)", expanded=False):
        if st.button("🚀 Generar Diagnóstico Territorial", type="primary", key="btn_terr"):
            if not api_key:
                st.error("API Key no configurada en los Secrets.")
            else:
                client = genai.Client(api_key=api_key)
                total_inasistencias_terr = len(df_terr)
                pareto_str = "\n".join([f"- {sup}: {cant} ausencias" for sup, cant in df_terr['Jerarquia_Dinamica'].value_counts().items()]) if 'Jerarquia_Dinamica' in df_terr.columns else "No disponible"
                tendencia_str = df_terr_historico.groupby(['post_titulo', 'Jerarquia_Dinamica']).size().unstack(fill_value=0).to_string() if 'post_titulo' in df_terr_historico.columns and 'Jerarquia_Dinamica' in df_terr_historico.columns else "No disponible"

                prompt_1 = f"""
                Inicia tu respuesta OBLIGATORIAMENTE con esta oración exacta:
                "{encabezado_terr}"

                Luego analiza ESTRICTAMENTE los siguientes 3 puntos numerados (sin incluir conclusiones generales ni consejos adicionales fuera de ellos):
                1. Total de inasistencias que tiene el líder territorial ({total_inasistencias_terr} inasistencias).
                2. Pareto de cuáles son sus supervisores/regionales críticos según estas ausencias:
                {pareto_str}
                3. Análisis de tendencia histórica de sus supervisores a lo largo de las conferencias:
                {tendencia_str}
                """
                with st.spinner("Analizando desempeño territorial..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt_1)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    st.divider()

    # --- MÉTRICAS ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Inasistencias", len(df_terr))
    col2.metric("Supervisores Afectados", df_terr['Jerarquia_Dinamica'].nunique() if 'Jerarquia_Dinamica' in df_terr.columns else 0)
    col3.metric("Conferencias Analizadas", df_terr_historico['post_titulo'].nunique() if 'post_titulo' in df_terr_historico.columns else 1)
    col4.metric("Comercios Únicos", df_terr[agentes_col].nunique())

    st.divider()

    # --- GRÁFICOS CON TEXTOS EN VERDE OSCURO ---
    col_hist, col_sup = st.columns([1, 1])

    with col_hist:
        st.subheader("📈 Inasistencias por Conferencia")
        if 'post_titulo' in df_terr_historico.columns:
            hist_df = df_terr_historico['post_titulo'].value_counts().reset_index()
            hist_df.columns = ['Conferencia', 'Inasistencias']
            hist_df['Conferencia_Corta'] = hist_df['Conferencia'].apply(acortar_titulo)
            hist_df['Orden'] = hist_df['Conferencia'].apply(extraer_fecha_orden)
            hist_df = hist_df.sort_values(by='Orden', ascending=True)

            fig_hist = px.bar(
                hist_df, x='Conferencia_Corta', y='Inasistencias', text='Inasistencias',
                color='Inasistencias', color_continuous_scale=['#3CC666', '#096045']
            )
            # Ajuste explícito de color de texto en ejes a Verde Oscuro (#096045)
            fig_hist.update_layout(
                yaxis={'fixedrange': True, 'tickfont': {'color': '#096045', 'size': 12, 'family': 'Arial'}, 'title': {'text': ''}}, 
                xaxis={'fixedrange': True, 'tickfont': {'color': '#096045', 'size': 11, 'family': 'Arial'}, 'title': {'text': ''}},
                showlegend=False, coloraxis_showscale=False, height=300,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font={'color': '#096045'}
            )
            fig_hist.update_traces(textposition='inside', textfont={'color': 'white', 'weight': 'bold'})
            st.plotly_chart(fig_hist, use_container_width=True, config={'displayModeBar': False})

    with col_sup:
        st.subheader("📌 Ausencias por Supervisor")
        if 'Jerarquia_Dinamica' in df_terr.columns:
            top_sup = df_terr['Jerarquia_Dinamica'].value_counts().reset_index()
            top_sup.columns = ['Supervisor', 'Casos']
            fig_sup = px.bar(
                top_sup.head(6), x='Casos', y='Supervisor', orientation='h', text='Casos',
                color='Casos', color_continuous_scale=['#FF6700', '#096045']
            )
            fig_sup.update_layout(
                yaxis={'categoryorder':'total ascending', 'fixedrange': True, 'tickfont': {'color': '#096045', 'size': 11, 'family': 'Arial'}, 'title': {'text': ''}}, 
                xaxis={'fixedrange': True, 'tickfont': {'color': '#096045', 'size': 11, 'family': 'Arial'}, 'title': {'text': ''}},
                showlegend=False, coloraxis_showscale=False, height=300,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font={'color': '#096045'}
            )
            fig_sup.update_traces(textposition='inside', textfont={'color': 'white', 'weight': 'bold'})
            st.plotly_chart(fig_sup, use_container_width=True, config={'displayModeBar': False})

    st.divider()

    # --- TABLA Y DIAGNÓSTICO SUPERVISOR ---
    st.subheader("📋 Agentes Pendientes & Gestión de Supervisor")

    if 'Jerarquia_Dinamica' in df_terr.columns:
        supervisores_unicos = list(df_terr['Jerarquia_Dinamica'].dropna().unique())
        ranking_sup_df = df_terr.groupby('Jerarquia_Dinamica').size().reset_index(name='Inasistencias').sort_values(by='Inasistencias', ascending=True).reset_index(drop=True)

        col_select_sup, col_expert_sup = st.columns([1, 1.2])

        with col_select_sup:
            selected_sup = st.selectbox("Filtrar Tabla por Supervisor:", ["Todos"] + supervisores_unicos)

        sup_evaluado = selected_sup if selected_sup != "Todos" else (supervisores_unicos[0] if supervisores_unicos else "Sin Supervisor")

        try:
            rank_sup = ranking_sup_df[ranking_sup_df['Jerarquia_Dinamica'] == sup_evaluado].index[0] + 1
        except IndexError:
            rank_sup = 99

        if rank_sup == 1:
            encabezado_sup = f"Felicidades {sup_evaluado} estás ocupando el 1er lugar. Para mantenerte cómo el líder deberás mejorar las siguientes oportunidades:"
        elif rank_sup in [2, 3]:
            encabezado_sup = f"Felicidades {sup_evaluado} estás ocupando el {rank_sup}º lugar. Para seguir escalando al primer lugar, deberás tener en cuenta los siguientes puntos:"
        else:
            encabezado_sup = f"Supervisor {sup_evaluado}, te ubicas en el lugar {rank_sup}º del territorio. Analicemos tus oportunidades de mejora:"

        with col_expert_sup:
            with st.expander(f"💡 Recibe un consejo experto ({sup_evaluado})", expanded=False):
                if st.button("🚀 Generar Diagnóstico Supervisor", type="primary", key="btn_sup"):
                    if not api_key:
                        st.error("API Key no configurada en los Secrets.")
                    else:
                        client = genai.Client(api_key=api_key)
                        df_sup_actual = df_terr[df_terr['Jerarquia_Dinamica'] == sup_evaluado]
                        total_ausencias_sup = len(df_sup_actual)
                        df_sup_hist = df_terr_historico[df_terr_historico['Jerarquia_Dinamica'] == sup_evaluado]
                        tendencia_sup = df_sup_hist.groupby('post_titulo').size().to_dict() if 'post_titulo' in df_sup_hist.columns else {}

                        agentes_sup = df_sup_actual[agentes_col].dropna().unique()
                        recurrentes_cant = sum(1 for ag in agentes_sup if ag in agentes_recurrentes_set)
                        nuevos_cant = len(agentes_sup) - recurrentes_cant

                        prompt_2 = f"""
                        Inicia tu respuesta OBLIGATORIAMENTE con esta oración exacta:
                        "{encabezado_sup}"

                        Luego analiza ESTRICTAMENTE los siguientes 3 puntos numerados (sin incluir conclusiones generales ni consejos adicionales fuera de ellos):
                        1. Total de inasistencias en su zona ({total_ausencias_sup} inasistencias).
                        2. Análisis de si viene mejorando o empeorando en inasistencia según sus datos históricos por conferencia:
                        {tendencia_sup}
                        3. Composición de sus agentes pendientes: {recurrentes_cant} son recurrentes y {nuevos_cant} son nuevos faltantes.
                        """
                        with st.spinner("Analizando desempeño del supervisor..."):
                            try:
                                res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt_2)
                                st.markdown(res.text)
                            except Exception as e:
                                st.error(f"Error al conectar con la IA: {e}")

        df_disp = df_terr[df_terr['Jerarquia_Dinamica'] == selected_sup] if selected_sup != "Todos" else df_terr
    else:
        df_disp = df_terr

    st.dataframe(df_disp, use_container_width=True, height=250)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_disp.to_excel(writer, index=False, sheet_name='Pendientes')
    excel_data = output.getvalue()

    st.download_button(
        label=f"📥 Descargar Excel Filtrado ({len(df_disp)} registros)",
        data=excel_data,
        file_name=f"Inasistencias_{selected_terr}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("⚠️ Sube o actualiza la base 'data.xlsx' para visualizar el dashboard.")
