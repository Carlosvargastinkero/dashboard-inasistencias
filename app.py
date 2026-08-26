import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import io

st.set_page_config(page_title="Dashboard Operativo", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Control de Inasistencias & Coaching Operativo")

st.sidebar.header("⚙️ Configuración")
api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")
uploaded_file = st.sidebar.file_uploader("Cargar Base Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1)

    territoriales = data_df['TERRITORIAL'].unique()
    selected_terr = st.sidebar.selectbox("Seleccionar Líder Territorial", territoriales)

    # Filtrar datos por territorio
    df_terr = data_df[data_df['TERRITORIAL'] == selected_terr].copy()
    
    correo_match = dir_df[dir_df['TERRITORIAL'] == selected_terr]['CORREO'].values if 'CORREO' in dir_df.columns else []
    correo_leader = correo_match[0] if len(correo_match) > 0 else "Sin correo registrado"

    # Clasificación de Historial (Si existe la columna 'Inasistencias_Previas')
    if 'Inasistencias_Previas' in df_terr.columns:
        recurrentes = df_terr[df_terr['Inasistencias_Previas'] > 1]
        nuevos = df_terr[df_terr['Inasistencias_Previas'] <= 1]
    else:
        recurrentes = pd.DataFrame()
        nuevos = df_terr

    # Métricas clave (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Inasistencias", len(df_terr))
    col2.metric("Supervisores Afectados", df_terr['Jerarquia_Dinamica'].nunique() if 'Jerarquia_Dinamica' in df_terr.columns else 0)
    col3.metric("Faltantes Recurrentes", len(recurrentes) if not recurrentes.empty else "N/A")
    col4.metric("Nuevos Faltantes", len(nuevos))

    st.divider()

    # Gráfico y Gestión de IA
    col_graph, col_action = st.columns([1, 1])

    with col_graph:
        st.subheader("📌 Ausencias por Supervisor")
        if 'Jerarquia_Dinamica' in df_terr.columns:
            top_sup = df_terr['Jerarquia_Dinamica'].value_counts().reset_index()
            top_sup.columns = ['Supervisor', 'Casos']
            fig = px.bar(top_sup.head(6), x='Casos', y='Supervisor', orientation='h', 
                         text='Casos', color='Casos', color_continuous_scale='Reds')
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, height=320)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No se encontró la columna 'Jerarquia_Dinamica'.")

    with col_action:
        st.subheader("💬 Generador de Mensajes IA")
        canal = st.radio("Formato de Salida:", ["WhatsApp (Directo y Corto)", "Correo Ejecutivo"], horizontal=True)
        
        if st.button("🚀 Generar Plan con IA", type="primary"):
            if not api_key:
                st.warning("Ingresa tu API Key en la barra lateral.")
            else:
                client = genai.Client(api_key=api_key)
                
                if 'Jerarquia_Dinamica' in df_terr.columns:
                    top_3_sup = "\n".join([f"- {row['Supervisor']}: {row['Casos']} ausencias" for _, row in top_sup.head(3).iterrows()])
                else:
                    top_3_sup = "Información de supervisores no disponible."

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
                
                with st.spinner("Analizando variables con Gemini..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                        st.text_area("Resultado para copiar/pegar:", res.text, height=220)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    st.divider()

    # SECCIÓN DE DESCARGA Y CONSULTA 100%
    st.subheader(f"📋 Lista Completa de Agentes Pendientes - {selected_terr}")
    st.caption("Visualiza y descarga la base completa para la asignación de llamadas 1 a 1 por supervisor.")

    if 'Jerarquia_Dinamica' in df_terr.columns:
        supervisores_list = ["Todos"] + list(df_terr['Jerarquia_Dinamica'].dropna().unique())
        selected_sup = st.selectbox("Filtrar por Supervisor:", supervisores_list)

        if selected_sup != "Todos":
            df_display = df_terr[df_terr['Jerarquia_Dinamica'] == selected_sup]
        else:
            df_display = df_terr
    else:
        df_display = df_terr

    st.dataframe(df_display, use_container_width=True, height=250)

    # Botón de Descarga Excel
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
    st.info("👈 Sube tu archivo Excel en el menú lateral para cargar el Dashboard.")
