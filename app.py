import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import io
import os

st.set_page_config(page_title="Control de Inasistencia", layout="wide", initial_sidebar_state="collapsed")

# 1. Título actualizado
st.title("📊 Control de Inasistencia Conferencia Carlos Mazzetti")

# Autenticación automática de API Key
api_key = st.secrets.get("GEMINI_API_KEY", None)

# Menú lateral opcional para administradores
st.sidebar.header("⚙️ Administración")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")

uploaded_file = st.sidebar.file_uploader("Actualizar Base Excel (.xlsx)", type=["xlsx"])

# Determinar fuente de datos
file_to_load = None
if uploaded_file:
    file_to_load = uploaded_file
elif os.path.exists("data.xlsx"):
    file_to_load = "data.xlsx"

if file_to_load:
    xls = pd.ExcelFile(file_to_load)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1) if len(xls.sheet_names) > 1 else pd.DataFrame()

    territoriales = data_df['TERRITORIAL'].dropna().unique()
    
    col_sel, col_empty = st.columns([1, 2])
    with col_sel:
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", territoriales)

    # Filtrar datos por territorio
    df_terr = data_df[data_df['TERRITORIAL'] == selected_terr].copy()
    
    correo_match = dir_df[dir_df['TERRITORIAL'] == selected_terr]['CORREO'].values if 'CORREO' in dir_df.columns else []
    correo_leader = correo_match[0] if len(correo_match) > 0 else "Sin correo registrado"

    if 'Inasistencias_Previas' in df_terr.columns:
        recurrentes = df_terr[df_terr['Inasistencias_Previas'] > 1]
        nuevos = df_terr[df_terr['Inasistencias_Previas'] <= 1]
    else:
        recurrentes = pd.DataFrame()
        nuevos = df_terr

    # Métricas clave
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Inasistencias", len(df_terr))
    col2.metric("Supervisores Afectados", df_terr['Jerarquia_Dinamica'].nunique() if 'Jerarquia_Dinamica' in df_terr.columns else 0)
    col3.metric("Faltantes Recurrentes", len(recurrentes) if not recurrentes.empty else "N/A")
    col4.metric("Nuevos Faltantes", len(nuevos))

    st.divider()

    col_graph, col_action = st.columns([1, 1])

    with col_graph:
        st.subheader("📌 Ausencias por Supervisor")
        if 'Jerarquia_Dinamica' in df_terr.columns:
            top_sup = df_terr['Jerarquia_Dinamica'].value_counts().reset_index()
            top_sup.columns = ['Supervisor', 'Casos']
            fig = px.bar(top_sup.head(6), x='Casos', y='Supervisor', orientation='h', 
                         text='Casos', color='Casos', color_continuous_scale='Reds')
            
            # 2. Bloqueo de zoom/lupa y desactivación de barra flotante Plotly
            fig.update_layout(
                yaxis={'categoryorder':'total ascending', 'fixedrange': True}, 
                xaxis={'fixedrange': True},
                showlegend=False, 
                height=320
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.warning("No se encontró la columna 'Jerarquia_Dinamica'.")

    with col_action:
        st.subheader("💬 Generador de Mensajes IA")
        canal = st.radio("Formato de Salida:", ["WhatsApp (Directo)", "Correo Ejecutivo"], horizontal=True)
        
        if st.button("🚀 Generar Plan con IA", type="primary"):
            if not api_key:
                st.error("API Key no configurada en los Secrets de Streamlit.")
            else:
                client = genai.Client(api_key=api_key)
                top_3_sup = "\n".join([f"- {row['Supervisor']}: {row['Casos']} ausencias" for _, row in top_sup.head(3).iterrows()]) if 'Jerarquia_Dinamica' in df_terr.columns else "Sin datos"
                agentes_col = 'AGENTE' if 'AGENTE' in df_terr.columns else df_terr.columns[0]
                agentes_sample = ", ".join(df_terr[agentes_col].dropna().head(5).astype(str).tolist())
                
                prompt = f"""
                Eres un Director de Operaciones y Coach Ejecutivo. Genera un mensaje para el líder {selected_terr} en formato {canal}.
                
                DATOS CLAVE DEL TERRITORIO:
                - Total ausencias: {len(df_terr)}
                - Muestra de comercios/agentes: {agentes_sample}
                - Supervisores críticos con mayor ausentismo:
                {top_3_sup}
                
                INSTRUCCIONES DE ESTILO:
                - Si es WhatsApp: Usa viñetas, emojis, un saludo directo y enfocado a la acción inmediata con sus supervisores. Máximo 90 palabras.
                - Si es Correo: Asunto directo, diagnóstico breve y 2 acciones tácticas concretas para los supervisores clave. Máximo 140 palabras.
                """
                
                with st.spinner("Analizando con Gemini..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                        st.text_area("Resultado para copiar/pegar:", res.text, height=200)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    st.divider()

    # Tabla 100% y Descarga
    st.subheader(f"📋 Lista Completa de Agentes Pendientes - {selected_terr}")
    
    if 'Jerarquia_Dinamica' in df_terr.columns:
        supervisores_list = ["Todos"] + list(df_terr['Jerarquia_Dinamica'].dropna().unique())
        selected_sup = st.selectbox("Filtrar por Supervisor:", supervisores_list)
        df_display = df_terr[df_terr['Jerarquia_Dinamica'] == selected_sup] if selected_sup != "Todos" else df_terr
    else:
        df_display = df_terr

    st.dataframe(df_display, use_container_width=True, height=250)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_display.to_excel(writer, index=False, sheet_name='Pendientes')
    excel_data = output.getvalue()

    st.download_button(
        label=f"📥 Descargar Excel de {selected_terr} ({len(df_display)} registros)",
        data=excel_data,
        file_name=f"Inasistencias_{selected_terr}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("⚠️ No se encontró la base 'data.xlsx' en el servidor. Sube un archivo desde la barra lateral.")
