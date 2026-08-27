import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import io
import os
import re

st.set_page_config(page_title="Control de Inasistencias", layout="wide", initial_sidebar_state="collapsed")

st.title("📊 Control de Inasistencia Conferencia Carlos Mazzetti")

# Autenticación automática de API Key desde Secrets
api_key = st.secrets.get("GEMINI_API_KEY", None)

# Menú lateral para administración
st.sidebar.header("⚙️ Administración")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")

uploaded_file = st.sidebar.file_uploader("Actualizar Base Excel (.xlsx)", type=["xlsx"])

# Cargar base de datos
file_to_load = None
if uploaded_file:
    file_to_load = uploaded_file
elif os.path.exists("data.xlsx"):
    file_to_load = "data.xlsx"

if file_to_load:
    xls = pd.ExcelFile(file_to_load)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1) if len(xls.sheet_names) > 1 else pd.DataFrame()

    # --- FUNCIONES AUXILIARES ---
    def extraer_fecha_orden(titulo):
        match = re.search(r'(\d{2}/\d{2})', str(titulo))
        if match:
            dia, mes = map(int, match.group(1).split('/'))
            return (mes, dia)
        return (0, 0)

    def acortar_titulo(titulo):
        return str(titulo).split(':')[0].strip() if ':' in str(titulo) else str(titulo)

    # Identificación de agentes recurrentes a nivel global
    agentes_col = 'AGENTE' if 'AGENTE' in data_df.columns else data_df.columns[0]
    conteo_agentes_global = data_df[agentes_col].value_counts()
    agentes_recurrentes_set = set(conteo_agentes_global[conteo_agentes_global > 1].index)

    # --- REORDENAMIENTO DE FILTROS PRINCIPALES ---
    col_conf, col_terr = st.columns([1, 1])

    # 1. Filtro Seleccionar Conferencia (Primero)
    if 'post_titulo' in data_df.columns:
        conferencias_raw = data_df['post_titulo'].dropna().unique().tolist()
        conferencias_ordenadas = sorted(conferencias_raw, key=extraer_fecha_orden, reverse=True)
        opciones_conf = conferencias_ordenadas + ["Todas las Conferencias (Histórico)"]
    else:
        opciones_conf = ["Todas"]

    with col_conf:
        selected_conf = st.selectbox("📅 Seleccionar Conferencia:", opciones_conf, index=0)

    # Base filtrada por conferencia
    if selected_conf != "Todas las Conferencias (Histórico)" and 'post_titulo' in data_df.columns:
        df_conf = data_df[data_df['post_titulo'] == selected_conf].copy()
    else:
        df_conf = data_df.copy()

    # 2. Filtro Seleccionar Líder Territorial (Segundo)
    territoriales = data_df['TERRITORIAL'].dropna().unique()
    with col_terr:
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", territoriales)

    df_terr = df_conf[df_conf['TERRITORIAL'] == selected_terr].copy()
    df_terr_historico = data_df[data_df['TERRITORIAL'] == selected_terr].copy()

    # --- CÁLCULO DE RANKING TERRITORIAL ---
    ranking_terr_df = df_conf.groupby('TERRITORIAL').size().reset_index(name='Inasistencias')
    ranking_terr_df = ranking_terr_df.sort_values(by='Inasistencias', ascending=True).reset_index(drop=True)
    
    try:
        rank_terr = ranking_terr_df[ranking_terr_df['TERRITORIAL'] == selected_terr].index[0] + 1
    except IndexError:
        rank_terr = 99

    # Apertura personalizada según ranking
    if rank_terr == 1:
        encabezado_terr = f"Felicidades {selected_terr} estás ocupando el 1er lugar. Para mantenerte cómo el líder de los territoriales deberás mejorar las siguientes oportunidades:"
    elif rank_terr in [2, 3]:
        encabezado_terr = f"Felicidades {selected_terr} estás ocupando el {rank_terr}º lugar. Para seguir escalando al primer lugar, deberás tener en cuenta los siguientes puntos:"
    else:
        encabezado_terr = f"Líder {selected_terr}, actualmente te ubicas en la posición {rank_terr}º entre los territoriales. Analicemos las oportunidades clave de mejora:"

    # --- SECCIÓN: CONSEJO EXPERTO TERRITORIAL ---
    with st.expander("💡 Recibe un consejo experto (Líder Territorial)", expanded=False):
        if st.button("🚀 Generar Diagnóstico Territorial", type="primary", key="btn_terr"):
            if not api_key:
                st.error("API Key no configurada en los Secrets.")
            else:
                client = genai.Client(api_key=api_key)
                
                # Datos de entrada para Prompt 1
                total_inasistencias_terr = len(df_terr)
                
                # Pareto de supervisores
                if 'Jerarquia_Dinamica' in df_terr.columns:
                    pareto_sup = df_terr['Jerarquia_Dinamica'].value_counts()
                    pareto_str = "\n".join([f"- {sup}: {cant} ausencias" for sup, cant in pareto_sup.items()])
                else:
                    pareto_str = "No disponible"

                # Tendencia por conferencia de sus supervisores
                if 'post_titulo' in df_terr_historico.columns and 'Jerarquia_Dinamica' in df_terr_historico.columns:
                    tendencia_df = df_terr_historico.groupby(['post_titulo', 'Jerarquia_Dinamica']).size().unstack(fill_value=0)
                    tendencia_str = tendencia_df.to_string()
                else:
                    tendencia_str = "No disponible"

                prompt_1 = f"""
                Inicia tu respuesta OBLIGATORIAMENTE con esta oración exacta:
                "{encabezado_terr}"

                Luego analiza ESTRICTAMENTE los siguientes 3 puntos numerados (no agregues conclusiones generales ni consejos adicionales fuera de ellos):
                1. Total de inasistencias que tiene el líder territorial ({total_inasistencias_terr} inasistencias).
                2. Pareto de cuáles son sus supervisores/regionales críticos según estas ausencias:
                {pareto_str}
                3. Análisis de tendencia histórica de sus supervisores a lo largo de las conferencias (¿están subiendo o bajando en ausencias y en quiénes enfocarse para lograr el mayor impacto de reducción?):
                {tendencia_str}
                """

                with st.spinner("Analizando desempeño territorial..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt_1)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    st.divider()

    # --- METRICAS CLAVE ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Inasistencias", len(df_terr))
    col2.metric("Supervisores Afectados", df_terr['Jerarquia_Dinamica'].nunique() if 'Jerarquia_Dinamica' in df_terr.columns else 0)
    col3.metric("Conferencias Analizadas", df_terr_historico['post_titulo'].nunique() if 'post_titulo' in df_terr_historico.columns else 1)
    col4.metric("Comercios Únicos", df_terr[agentes_col].nunique())

    st.divider()

    # --- GRÁFICOS VISUALES ---
    col_hist, col_sup = st.columns([1, 1])

    with col_hist:
        st.subheader("📈 Inasistencias por Conferencia")
        if 'post_titulo' in df_terr_historico.columns:
            hist_df = df_terr_historico['post_titulo'].value_counts().reset_index()
            hist_df.columns = ['Conferencia', 'Inasistencias']
            hist_df['Conferencia_Corta'] = hist_df['Conferencia'].apply(acortar_titulo)
            hist_df['Orden'] = hist_df['Conferencia'].apply(extraer_fecha_orden)
            hist_df = hist_df.sort_values(by='Orden', ascending=True)

            fig_hist = px.bar(hist_df, x='Conferencia_Corta', y='Inasistencias', text='Inasistencias', color='Inasistencias', color_continuous_scale='Blues')
            fig_hist.update_layout(yaxis={'fixedrange': True}, xaxis={'fixedrange': True}, showlegend=False, coloraxis_showscale=False, height=300, xaxis_title=None)
            st.plotly_chart(fig_hist, use_container_width=True, config={'displayModeBar': False})

    with col_sup:
        st.subheader("📌 Ausencias por Supervisor")
        if 'Jerarquia_Dinamica' in df_terr.columns:
            top_sup = df_terr['Jerarquia_Dinamica'].value_counts().reset_index()
            top_sup.columns = ['Supervisor', 'Casos']
            fig_sup = px.bar(top_sup.head(6), x='Casos', y='Supervisor', orientation='h', text='Casos', color='Casos', color_continuous_scale='Reds')
            fig_sup.update_layout(yaxis={'categoryorder':'total ascending', 'fixedrange': True}, xaxis={'fixedrange': True}, showlegend=False, coloraxis_showscale=False, height=300)
            st.plotly_chart(fig_sup, use_container_width=True, config={'displayModeBar': False})

    st.divider()

    # --- SECCIÓN: AGENTES PENDIENTES & CONSEJO SUPERVISOR ---
    st.subheader("📋 Agentes Pendientes & Gestión de Supervisor")

    if 'Jerarquia_Dinamica' in df_terr.columns:
        supervisores_unicos = list(df_terr['Jerarquia_Dinamica'].dropna().unique())
        
        # Ranking de supervisores dentro del territorio
        ranking_sup_df = df_terr.groupby('Jerarquia_Dinamica').size().reset_index(name='Inasistencias')
        ranking_sup_df = ranking_sup_df.sort_values(by='Inasistencias', ascending=True).reset_index(drop=True)

        col_select_sup, col_expert_sup = st.columns([1, 1.2])

        with col_select_sup:
            selected_sup = st.selectbox("Filtrar Tabla por Supervisor:", ["Todos"] + supervisores_unicos)

        # Determinar el supervisor a evaluar
        sup_evaluado = selected_sup if selected_sup != "Todos" else (supervisores_unicos[0] if supervisores_unicos else "Sin Supervisor")

        # Posición del supervisor
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
                        
                        # Histórico del supervisor
                        df_sup_hist = df_terr_historico[df_terr_historico['Jerarquia_Dinamica'] == sup_evaluado]
                        tendencia_sup = df_sup_hist.groupby('post_titulo').size().to_dict() if 'post_titulo' in df_sup_hist.columns else {}

                        # Análisis de recurrencia
                        agentes_sup = df_sup_actual[agentes_col].dropna().unique()
                        recurrentes_cant = sum(1 for ag in agentes_sup if ag in agentes_recurrentes_set)
                        nuevos_cant = len(agentes_sup) - recurrentes_cant

                        prompt_2 = f"""
                        Inicia tu respuesta OBLIGATORIAMENTE con esta oración exacta:
                        "{encabezado_sup}"

                        Luego analiza ESTRICTAMENTE los siguientes 3 puntos numerados (no agregues conclusiones generales ni consejos adicionales fuera de ellos):
                        1. Total de inasistencias en su zona ({total_ausencias_sup} inasistencias).
                        2. Análisis de si viene mejorando o empeorando en inasistencia según sus datos históricos por conferencia:
                        {tendencia_sup}
                        3. Composición de sus agentes pendientes: {recurrentes_cant} son recurrentes (faltan con frecuencia) y {nuevos_cant} son nuevos faltantes. Indica en cuál grupo enfocar la gestión inmediata.
                        """

                        with st.spinner("Analizando desempeño del supervisor..."):
                            try:
                                res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt_2)
                                st.markdown(res.text)
                            except Exception as e:
                                st.error(f"Error al conectar con la IA: {e}")

        # Filtrar tabla para mostrar
        df_disp = df_terr[df_terr['Jerarquia_Dinamica'] == selected_sup] if selected_sup != "Todos" else df_terr

    else:
        df_disp = df_terr

    st.dataframe(df_disp, use_container_width=True, height=250)

    # Botón de Descarga Excel
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
