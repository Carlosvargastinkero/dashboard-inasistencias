import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import io
import os
import re

st.set_page_config(page_title="Control de Inasistencias", layout="wide", initial_sidebar_state="collapsed")

st.title("📊 Control de Inasistencias & Histórico de Conferencias")

# Autenticación automática de API Key
api_key = st.secrets.get("GEMINI_API_KEY", None)

# Menú lateral para administración
st.sidebar.header("⚙️ Administración")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")

uploaded_file = st.sidebar.file_uploader("Actualizar Base Excel (.xlsx)", type=["xlsx"])

# Cargador de datos
file_to_load = None
if uploaded_file:
    file_to_load = uploaded_file
elif os.path.exists("data.xlsx"):
    file_to_load = "data.xlsx"

if file_to_load:
    xls = pd.ExcelFile(file_to_load)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1) if len(xls.sheet_names) > 1 else pd.DataFrame()

    # --- FILTROS PRINCIPALES ---
    col_terr, col_conf = st.columns([1, 1])

    # 1. Filtro por Territorial
    territoriales = data_df['TERRITORIAL'].dropna().unique()
    with col_terr:
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", territoriales)

    df_terr = data_df[data_df['TERRITORIAL'] == selected_terr].copy()

    # 2. Ordenamiento inteligente de conferencias por fecha (DD/MM) de mayor a menor
    def extraer_fecha_orden(titulo):
        match = re.search(r'(\d{2}/\d{2})', str(titulo))
        if match:
            dia, mes = map(int, match.group(1).split('/'))
            return (mes, dia)
        return (0, 0)

    if 'post_titulo' in df_terr.columns:
        conferencias_raw = df_terr['post_titulo'].dropna().unique().tolist()
        conferencias_ordenadas = sorted(conferencias_raw, key=extraer_fecha_orden, reverse=True)
        opciones_conf = ["Todas las Conferencias (Histórico)"] + conferencias_ordenadas
    else:
        opciones_conf = ["Todas"]

    with col_conf:
        selected_conf = st.selectbox("📅 Seleccionar Conferencia:", opciones_conf)

    # Filtrar dataframe según la conferencia seleccionada
    if selected_conf != "Todas las Conferencias (Histórico)" and 'post_titulo' in df_terr.columns:
        df_filtered = df_terr[df_terr['post_titulo'] == selected_conf].copy()
    else:
        df_filtered = df_terr.copy()

    # --- METRICAS CLAVE ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Inasistencias (Filtro)", len(df_filtered))
    col2.metric("Supervisores Afectados", df_filtered['Jerarquia_Dinamica'].nunique() if 'Jerarquia_Dinamica' in df_filtered.columns else 0)
    
    if 'post_titulo' in df_terr.columns:
        col3.metric("Conferencias Analizadas", df_terr['post_titulo'].nunique())
    else:
        col3.metric("Conferencias", "1")
        
    agentes_col = 'AGENTE' if 'AGENTE' in df_filtered.columns else df_filtered.columns[0]
    col4.metric("Comercios Únicos", df_filtered[agentes_col].nunique())

    st.divider()

    # --- GRÁFICOS VISUALES ---
    col_hist, col_sup = st.columns([1, 1])

    # Gráfico 1: Evolución Histórica por Conferencia
    with col_hist:
        st.subheader("📈 Inasistencias por Conferencia")
        if 'post_titulo' in df_terr.columns:
            hist_df = df_terr['post_titulo'].value_counts().reset_index()
            hist_df.columns = ['Conferencia', 'Inasistencias']
            hist_df['Orden'] = hist_df['Conferencia'].apply(extraer_fecha_orden)
            hist_df = hist_df.sort_values(by='Orden', ascending=True)

            fig_hist = px.bar(
                hist_df, x='Conferencia', y='Inasistencias',
                text='Inasistencias', color='Inasistencias',
                color_continuous_scale='Blues'
            )
            fig_hist.update_layout(
                yaxis={'fixedrange': True}, xaxis={'fixedrange': True},
                showlegend=False, height=320, xaxis_title=None
            )
            st.plotly_chart(fig_hist, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("Sin datos de histórico de conferencias.")

    # Gráfico 2: Ausencias por Supervisor (Periodo seleccionado)
    with col_sup:
        st.subheader("📌 Ausencias por Supervisor")
        if 'Jerarquia_Dinamica' in df_filtered.columns:
            top_sup = df_filtered['Jerarquia_Dinamica'].value_counts().reset_index()
            top_sup.columns = ['Supervisor', 'Casos']
            
            fig_sup = px.bar(
                top_sup.head(6), x='Casos', y='Supervisor', orientation='h',
                text='Casos', color='Casos', color_continuous_scale='Reds'
            )
            fig_sup.update_layout(
                yaxis={'categoryorder':'total ascending', 'fixedrange': True}, 
                xaxis={'fixedrange': True}, showlegend=False, height=320
            )
            st.plotly_chart(fig_sup, use_container_width=True, config={'displayModeBar': False})

    st.divider()

    # --- GENERADOR DE MENSAJES Y TABLA ---
    col_action, col_table = st.columns([1, 1.2])

    with col_action:
        st.subheader("💬 Generador de Mensajes IA")
        canal = st.radio("Formato de Salida:", ["WhatsApp (Directo)", "Correo Ejecutivo"], horizontal=True)
        
        if st.button("🚀 Generar Plan de Acción", type="primary"):
            if not api_key:
                st.error("API Key no configurada en los Secrets de Streamlit.")
            else:
                client = genai.Client(api_key=api_key)
                top_3_str = "\n".join([f"- {row['Supervisor']}: {row['Casos']} ausencias" for _, row in top_sup.head(3).iterrows()]) if 'Jerarquia_Dinamica' in df_filtered.columns else "N/A"
                agentes_sample = ", ".join(df_filtered[agentes_col].dropna().head(5).astype(str).tolist())
                
                prompt = f"""
                Actúa como Director de Operaciones. Redacta un mensaje para el líder territorial {selected_terr}.
                Contexto: {selected_conf}.
                
                DATOS DEL PERIODO:
                - Inasistencias en este corte: {len(df_filtered)}
                - Comercios destacados afectados: {agentes_sample}
                - Supervisores más críticos:
                {top_3_str}
                
                INSTRUCCIONES:
                - Formato {canal}.
                - Si es WhatsApp: Usa viñetas, emojis y enfoque directo a 2 acciones inmediatas para sus supervisores. Máximo 90 palabras.
                - Si es Correo: Asunto formal, diagnóstico rápido y compromisos tácticos para hoy. Máximo 140 palabras.
                """
                
                with st.spinner("Analizando con Gemini..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                        st.text_area("Resultado listo para enviar:", res.text, height=220)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    with col_table:
        st.subheader(f"📋 Agentes Pendientes ({len(df_filtered)})")
        
        if 'Jerarquia_Dinamica' in df_filtered.columns:
            sups = ["Todos"] + list(df_filtered['Jerarquia_Dinamica'].dropna().unique())
            sel_sup_tab = st.selectbox("Filtrar Tabla por Supervisor:", sups)
            df_disp = df_filtered[df_filtered['Jerarquia_Dinamica'] == sel_sup_tab] if sel_sup_tab != "Todos" else df_filtered
        else:
            df_disp = df_filtered

        st.dataframe(df_disp, use_container_width=True, height=220)

        # Botón de Descarga
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
    st.warning("⚠️ Sube o actualiza la base 'data.xlsx' para visualizar el histórico.")
