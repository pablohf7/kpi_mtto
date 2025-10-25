import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from datetime import datetime, timedelta

# Configuración de la página
st.set_page_config(
    page_title="Dashboard de Indicadores de Mantenimiento",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Paleta de colores específicos para tipos de mantenimiento
COLOR_PALETTE = {
    'pastel': ['#AEC6CF', '#FFB3BA', '#FFDFBA', '#BAFFC9', '#BAE1FF', '#F0E6EF', '#C9C9FF', '#FFC9F0'],
    'tipo_mtto': {
        'PREVENTIVO': '#87CEEB',  # Azul claro
        'BASADO EN CONDICIÓN': '#00008B',  # Azul oscuro
        'CORRECTIVO PLANIFICADO Y PROGRAMADO': '#FFD700',  # Amarillo
        'CORRECTIVO DE EMERGENCIA': '#FF0000'  # Rojo
    }
}

# Función para cargar datos desde Google Sheets
@st.cache_data(ttl=300)  # Cache por 5 minutos para actualizaciones automáticas
def load_data_from_google_sheets():
    try:
        # ID del archivo de Google Sheets (extraído del enlace proporcionado)
        sheet_id = "1s6PZKB4RmTch2XasM8MdzWHGZa_nUKYc"
        
        # Construir URL para exportar como CSV
        gsheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        
        # Leer el archivo directamente desde Google Sheets
        df = pd.read_excel(gsheet_url, sheet_name='DATAMTTO')
        
        # Limpiar y preparar datos
        df = clean_and_prepare_data(df)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos desde Google Sheets: {e}")
        st.info("Asegúrate de que el archivo de Google Sheets sea público y accesible")
        return pd.DataFrame()

# Función para cargar desde archivo local (mantenida para compatibilidad)
@st.cache_data
def load_data_from_file(uploaded_file):
    try:
        # Leer el archivo Excel
        df = pd.read_excel(uploaded_file, sheet_name='DATAMTTO')
        
        # Limpiar y preparar datos
        df = clean_and_prepare_data(df)
        return df
    except Exception as e:
        st.error(f"Error al cargar el archivo: {e}")
        return pd.DataFrame()

def clean_and_prepare_data(df):
    # Hacer una copia para no modificar el original
    df_clean = df.copy()
    
    # Renombrar columnas para consistencia
    df_clean = df_clean.rename(columns={
        'FECHA EJECUCIÓN': 'FECHA_DE_EJECUCION',
        'Tiempo Prog (min)': 'TIEMPO_PROG_MIN',
        'PRODUCCIÓN AFECTADA (SI-NO)': 'PRODUCCION_AFECTADA',
        'TIEMPO ESTIMADO DIARIO (min)': 'TDISPONIBLE',
        'TR (min)': 'TR_MIN',
        'TFC (min)': 'TFC_MIN',
        'TFS (min)': 'TFS_MIN',
        'h normal (min)': 'H_NORMAL_MIN',
        'h extra (min)': 'H_EXTRA_MIN'
    })
    
    # Manejar la columna de ubicación técnica (mantener el nombre original si existe)
    if 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'UBICACION TECNICA' in df_clean.columns:
        df_clean = df_clean.rename(columns={'UBICACION TECNICA': 'UBICACIÓN TÉCNICA'})
    elif 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'Ubicación Técnica' in df_clean.columns:
        df_clean = df_clean.rename(columns={'Ubicación Técnica': 'UBICACIÓN TÉCNICA'})
    
    # Convertir fechas
    df_clean['FECHA_DE_EJECUCION'] = pd.to_datetime(df_clean['FECHA_DE_EJECUCION'])
    
    # Asegurar que las columnas numéricas sean numéricas
    numeric_columns = ['TR_MIN', 'TFC_MIN', 'TFS_MIN', 'TDISPONIBLE', 'TIEMPO_PROG_MIN']
    for col in numeric_columns:
        if col in df_clean.columns:
            # Reemplazar fórmulas y textos por valores numéricos
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
    
    # Filtrar solo registros culminados para análisis
    if 'STATUS' in df_clean.columns:
        df_clean = df_clean[df_clean['STATUS'] == 'CULMINADO']
    
    return df_clean

# Función para calcular métricas basadas en el dataset real
def calculate_metrics(df):
    if df.empty:
        return {}
    
    # Calcular métricas básicas
    m = {}
    
    # Tiempo Disponible (suma del tiempo estimado diario)
    m['td'] = df['TDISPONIBLE'].sum() if 'TDISPONIBLE' in df.columns else 0
    
    # TFS, TR, TFC - solo para actividades que afectan producción
    prod_afectada_mask = df['PRODUCCION_AFECTADA'] == 'SI'
    m['tfs'] = df[prod_afectada_mask]['TFS_MIN'].sum() if 'TFS_MIN' in df.columns else 0
    m['tr'] = df[prod_afectada_mask]['TR_MIN'].sum() if 'TR_MIN' in df.columns else 0
    m['tfc'] = df[prod_afectada_mask]['TFC_MIN'].sum() if 'TFC_MIN' in df.columns else 0
    
    # Tiempo Operativo
    m['to'] = max(m['td'] - m['tfs'], 0)
    
    # Disponibilidad e Indisponibilidad
    m['disponibilidad'] = (m['to'] / m['td']) * 100 if m['td'] > 0 else 0
    m['indisponibilidad'] = (m['tfs'] / m['td']) * 100 if m['td'] > 0 else 0
    
    # Total de fallas (actividades que afectan producción)
    m['total_fallas'] = len(df[prod_afectada_mask])
    
    # MTBF, MTTF, MTTR
    m['mtbf'] = m['td'] / m['total_fallas'] if m['total_fallas'] > 0 else 0
    m['mttf'] = m['to'] / m['total_fallas'] if m['total_fallas'] > 0 else 0
    m['mttr'] = m['tr'] / m['total_fallas'] if m['total_fallas'] > 0 else 0
    
    # Mantenibilidad
    landa = m['total_fallas'] / m['td'] if m['td'] > 0 else 0
    m['mantenibilidad'] = 1 - np.exp(-landa * m['td']) if landa > 0 else 0
    
    # Porcentajes de tipos de mantenimiento
    tipo_mtto_totals = df.groupby('TIPO DE MTTO')['TR_MIN'].sum()
    total_mtto = tipo_mtto_totals.sum()
    
    if total_mtto > 0:
        m['mp_pct'] = (tipo_mtto_totals.get('PREVENTIVO', 0) / total_mtto) * 100
        m['mbc_pct'] = (tipo_mtto_totals.get('BASADO EN CONDICIÓN', 0) / total_mtto) * 100
        m['mce_pct'] = (tipo_mtto_totals.get('CORRECTIVO DE EMERGENCIA', 0) / total_mtto) * 100
        m['mcp_pct'] = (tipo_mtto_totals.get('CORRECTIVO PLANIFICADO Y PROGRAMADO', 0) / total_mtto) * 100
    else:
        m['mp_pct'] = m['mbc_pct'] = m['mce_pct'] = m['mcp_pct'] = 0
    
    return m

# Función para obtener datos semanales
def get_weekly_data(df):
    if df.empty or 'FECHA_DE_EJECUCION' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_EJECUCION'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_EJECUCION'].dt.year
    df_weekly['SEMANA_STR'] = df_weekly['AÑO'].astype(str) + '-S' + df_weekly['SEMANA'].astype(str).str.zfill(2)
    
    # Agrupar por semana - FILTRAR SOLO CUANDO AFECTA PRODUCCIÓN
    weekly_data = df_weekly[df_weekly['PRODUCCION_AFECTADA'] == 'SI'].groupby(['SEMANA_STR', 'AÑO', 'SEMANA']).agg({
        'TFS_MIN': 'sum',
        'TR_MIN': 'sum',
        'TFC_MIN': 'sum',
        'TDISPONIBLE': 'sum',
        'PRODUCCION_AFECTADA': lambda x: (x == 'SI').sum()
    }).reset_index()
    
    # Calcular disponibilidad semanal
    weekly_data['DISPO_SEMANAL'] = ((weekly_data['TDISPONIBLE'] - weekly_data['TFS_MIN']) / weekly_data['TDISPONIBLE']) * 100
    
    # Crear columna numérica para ordenar correctamente las semanas
    weekly_data['SEMANA_NUM'] = weekly_data['AÑO'].astype(str) + weekly_data['SEMANA'].astype(str).str.zfill(2)
    weekly_data = weekly_data.sort_values('SEMANA_NUM')
    
    return weekly_data

# Función para aplicar filtros
def apply_filters(df, equipo_filter, componente_filter, ubicacion_filter, fecha_inicio, fecha_fin):
    filtered_df = df.copy()
    
    if equipo_filter != "Todos":
        filtered_df = filtered_df[filtered_df['EQUIPO'] == equipo_filter]
    
    if componente_filter != "Todos":
        filtered_df = filtered_df[filtered_df['COMPONENTE'] == componente_filter]
    
    if ubicacion_filter != "Todos":
        if 'UBICACIÓN TÉCNICA' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['UBICACIÓN TÉCNICA'] == ubicacion_filter]
    
    # Aplicar filtro de fechas
    if fecha_inicio is not None and fecha_fin is not None:
        filtered_df = filtered_df[
            (filtered_df['FECHA_DE_EJECUCION'].dt.date >= fecha_inicio) &
            (filtered_df['FECHA_DE_EJECUCION'].dt.date <= fecha_fin)
        ]
    
    return filtered_df

# Interfaz principal
def main():
    st.title("📊 Dashboard de Indicadores de Mantenimiento")
    
    # Inicializar datos en session_state si no existen
    if 'data' not in st.session_state:
        st.session_state.data = pd.DataFrame()
    
    # Sidebar
    st.sidebar.title("Opciones")
    
    # Cargar datos
    st.sidebar.subheader("Fuente de Datos")
    
    # Opción para usar Google Sheets o archivo local
    data_source = st.sidebar.radio(
        "Selecciona la fuente de datos:",
        ["Google Sheets (Recomendado)", "Archivo Local"]
    )
    
    if data_source == "Google Sheets (Recomendado)":
        # Botón para cargar/actualizar datos desde Google Sheets
        if st.sidebar.button("🔄 Cargar/Actualizar desde Google Sheets"):
            with st.spinner("Cargando datos desde Google Sheets..."):
                df = load_data_from_google_sheets()
                if not df.empty:
                    st.session_state.data = df
                    st.sidebar.success("✅ Datos cargados correctamente desde Google Sheets")
                else:
                    st.sidebar.error("❌ Error al cargar datos desde Google Sheets")
        
        # Mostrar estado de la carga automática
        if not st.session_state.data.empty:
            st.sidebar.info("📊 Datos cargados desde Google Sheets")
            st.sidebar.write(f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.sidebar.write(f"Registros totales: {len(st.session_state.data)}")
    
    else:  # Archivo Local
        uploaded_file = st.sidebar.file_uploader("Cargar archivo Excel", type=["xlsx", "xls"])
        
        if uploaded_file is not None:
            df = load_data_from_file(uploaded_file)
            if not df.empty:
                st.session_state.data = df
                st.sidebar.success("✅ Archivo cargado correctamente")
    
    # Botón para forzar actualización de cache
    if st.sidebar.button("🔄 Forzar Actualización de Datos"):
        st.cache_data.clear()
        if data_source == "Google Sheets (Recomendado)":
            with st.spinner("Actualizando datos desde Google Sheets..."):
                df = load_data_from_google_sheets()
                if not df.empty:
                    st.session_state.data = df
                    st.sidebar.success("✅ Datos actualizados correctamente")
        st.rerun()
    
    # Filtros
    st.sidebar.subheader("Filtros")
    
    if not st.session_state.data.empty:
        # 1. FILTRO DE FECHA
        # Obtener rango de fechas del dataset
        min_date = st.session_state.data['FECHA_DE_EJECUCION'].min().date()
        max_date = st.session_state.data['FECHA_DE_EJECUCION'].max().date()
        
        st.sidebar.write("**Rango de Fechas**")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            fecha_inicio = st.date_input(
                "Fecha Inicio",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="fecha_inicio"
            )
        with col2:
            fecha_fin = st.date_input(
                "Fecha Fin",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
                key="fecha_fin"
            )
        
        # 2. FILTRO DE UBICACIÓN TÉCNICA
        # Verificar si existe la columna UBICACIÓN TÉCNICA
        if 'UBICACIÓN TÉCNICA' in st.session_state.data.columns:
            ubicaciones = ["Todos"] + sorted(st.session_state.data['UBICACIÓN TÉCNICA'].dropna().unique().tolist())
        else:
            ubicaciones = ["Todos"]
        
        ubicacion_filter = st.sidebar.selectbox("Ubicación Técnica", ubicaciones)
        
        # 3. FILTRO DE EQUIPOS
        equipos = ["Todos"] + sorted(st.session_state.data['EQUIPO'].unique().tolist())
        equipo_filter = st.sidebar.selectbox("Equipo", equipos)
        
        # 4. FILTRO DE COMPONENTES
        componentes = ["Todos"] + sorted(st.session_state.data['COMPONENTE'].unique().tolist())
        componente_filter = st.sidebar.selectbox("Componente", componentes)
        
        # Aplicar filtros
        filtered_data = apply_filters(st.session_state.data, equipo_filter, componente_filter, 
                                      ubicacion_filter, fecha_inicio, fecha_fin)
        
        # Mostrar información de estado
        st.sidebar.subheader("Estado")
        st.sidebar.write(f"Registros: {len(filtered_data)}")
        st.sidebar.write(f"Equipos: {len(filtered_data['EQUIPO'].unique())}")
        if not filtered_data.empty and 'FECHA_DE_EJECUCION' in filtered_data.columns:
            min_date_filtered = filtered_data['FECHA_DE_EJECUCION'].min()
            max_date_filtered = filtered_data['FECHA_DE_EJECUCION'].max()
            st.sidebar.write(f"Período: {min_date_filtered.strftime('%Y-%m-%d')} a {max_date_filtered.strftime('%Y-%m-%d')}")
        
        # CSS personalizado para pestañas más grandes
        st.markdown("""
        <style>
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            font-size: 1.2rem;
            font-weight: 600;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab-list"] button {
            padding: 12px 24px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Pestañas
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Planta", "TFS", "TR", "TFC", "Tipo de Mtto", "Confiabilidad"])
        
        # Calcular métricas
        metrics = calculate_metrics(filtered_data)
        weekly_data = get_weekly_data(filtered_data)
        
        # Pestaña Planta
        with tab1:
            st.header("📈 Indicadores de Planta")
            
            if not filtered_data.empty:
                # Métricas principales
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric("Tiempo Disponible", f"{metrics.get('td', 0):,.0f}", "minutos")
                
                with col2:
                    st.metric("Tiempo Operativo", f"{metrics.get('to', 0):,.0f}", "minutos")
                
                with col3:
                    st.metric("Tiempo Fuera de Servicio", f"{metrics.get('tfs', 0):,.0f}", "minutos")
                
                with col4:
                    disponibilidad = metrics.get('disponibilidad', 0)
                    status = "🟢" if disponibilidad >= 80 else "🟡" if disponibilidad >= 20 else "🔴"
                    st.metric("Disponibilidad", f"{disponibilidad:.1f}%", delta=None, delta_color="normal")
                    st.write(status)
                
                with col5:
                    indisponibilidad = metrics.get('indisponibilidad', 0)
                    status = "🟢" if indisponibilidad <= 20 else "🟡" if indisponibilidad <= 80 else "🔴"
                    st.metric("Indisponibilidad", f"{indisponibilidad:.1f}%", delta=None, delta_color="normal")
                    st.write(status)
                
                with col6:
                    total_downtime = metrics.get('tr', 0) + metrics.get('tfc', 0)
                    st.metric("TR + TFC", f"{total_downtime:,.0f}", "minutos")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='DISPO_SEMANAL', 
                                     title='Disponibilidad por Semana (%)',
                                     labels={'SEMANA_STR': 'Semana', 'DISPO_SEMANAL': 'Disponibilidad (%)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][0], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    if not weekly_data.empty:
                        fig = go.Figure()
                        # Solo agregamos TR y TFC, eliminamos TFS
                        # TR en amarillo pastel y TFC en rojo pastel
                        fig.add_trace(go.Bar(x=weekly_data['SEMANA_STR'], y=weekly_data['TR_MIN'], name='TR', 
                                            marker_color='#FFD700'))  # Amarillo pastel
                        fig.add_trace(go.Bar(x=weekly_data['SEMANA_STR'], y=weekly_data['TFC_MIN'], name='TFC', 
                                            marker_color='#FFB3BA'))  # Rojo pastel
                        # Cambiamos a modo apilado
                        fig.update_layout(title='TR y TFC por Semana', barmode='stack')
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TFS
        with tab2:
            st.header("Análisis de TFS")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # TFS por semana
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TFS_MIN',
                                     title='TFS por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TFS_MIN': 'TFS (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][1], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # TFS por equipo
                    tfs_por_equipo = filtered_afecta.groupby('EQUIPO')['TFS_MIN'].sum().reset_index()
                    tfs_por_equipo = tfs_por_equipo.sort_values('TFS_MIN', ascending=False).head(10)
                    
                    fig = px.bar(tfs_por_equipo, x='EQUIPO', y='TFS_MIN',
                                title='TFS por Equipo',
                                labels={'EQUIPO': 'Equipo', 'TFS_MIN': 'TFS (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][1])
                    st.plotly_chart(fig, use_container_width=True)
                
                # TFS por componente
                tfs_por_componente = filtered_afecta.groupby('COMPONENTE')['TFS_MIN'].sum().reset_index()
                tfs_por_componente = tfs_por_componente.sort_values('TFS_MIN', ascending=False).head(10)
                
                fig = px.bar(tfs_por_componente, x='COMPONENTE', y='TFS_MIN',
                            title='TFS por Componente',
                            labels={'COMPONENTE': 'Componente', 'TFS_MIN': 'TFS (min)'})
                fig.update_traces(marker_color=COLOR_PALETTE['pastel'][1])
                st.plotly_chart(fig, use_container_width=True)
                
                # Tablas de resumen
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Resumen TFS por Equipo")
                    resumen_equipo = filtered_afecta.groupby('EQUIPO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_equipo, use_container_width=True)
                
                with col2:
                    st.subheader("Resumen TFS por Componente")
                    resumen_componente = filtered_afecta.groupby('COMPONENTE').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_componente.head(10), use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TR
        with tab3:
            st.header("Análisis de TR")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # TR por semana
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TR_MIN',
                                     title='TR por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TR_MIN': 'TR (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][2], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # TR por equipo
                    tr_por_equipo = filtered_afecta.groupby('EQUIPO')['TR_MIN'].sum().reset_index()
                    tr_por_equipo = tr_por_equipo.sort_values('TR_MIN', ascending=False).head(10)
                    
                    fig = px.bar(tr_por_equipo, x='EQUIPO', y='TR_MIN',
                                title='TR por Equipo',
                                labels={'EQUIPO': 'Equipo', 'TR_MIN': 'TR (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][2])
                    st.plotly_chart(fig, use_container_width=True)
                
                # Pareto TR por componente
                tr_por_componente = filtered_afecta.groupby('COMPONENTE')['TR_MIN'].sum().reset_index()
                tr_por_componente = tr_por_componente.sort_values('TR_MIN', ascending=False).head(15)
                
                fig = px.bar(tr_por_componente, x='COMPONENTE', y='TR_MIN',
                            title='Pareto TR por Componente',
                            labels={'COMPONENTE': 'Componente', 'TR_MIN': 'TR (min)'})
                fig.update_traces(marker_color=COLOR_PALETTE['pastel'][2])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TFC
        with tab4:
            st.header("Análisis de TFC")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # TFC por semana
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TFC_MIN',
                                     title='TFC por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TFC_MIN': 'TFC (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][3], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # TFC por equipo
                    tfc_por_equipo = filtered_afecta.groupby('EQUIPO')['TFC_MIN'].sum().reset_index()
                    tfc_por_equipo = tfc_por_equipo.sort_values('TFC_MIN', ascending=False).head(10)
                    
                    fig = px.bar(tfc_por_equipo, x='EQUIPO', y='TFC_MIN',
                                title='TFC por Equipo',
                                labels={'EQUIPO': 'Equipo', 'TFC_MIN': 'TFC (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][3])
                    st.plotly_chart(fig, use_container_width=True)
                
                # Pareto TFC por componente
                tfc_por_componente = filtered_afecta.groupby('COMPONENTE')['TFC_MIN'].sum().reset_index()
                tfc_por_componente = tfc_por_componente.sort_values('TFC_MIN', ascending=False).head(15)
                
                fig = px.bar(tfc_por_componente, x='COMPONENTE', y='TFC_MIN',
                            title='Pareto TFC por Componente',
                            labels={'COMPONENTE': 'Componente', 'TFC_MIN': 'TFC (min)'})
                fig.update_traces(marker_color=COLOR_PALETTE['pastel'][3])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Tipo de Mantenimiento
        with tab5:
            st.header("Análisis por Tipo de Mantenimiento")
            
            if not filtered_data.empty:
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Mantenimiento Preventivo", f"{metrics.get('mp_pct', 0):.1f}%")
                
                with col2:
                    st.metric("Mant. Basado en Condición", f"{metrics.get('mbc_pct', 0):.1f}%")
                
                with col3:
                    st.metric("Correctivo Planificado", f"{metrics.get('mcp_pct', 0):.1f}%")
                
                with col4:
                    st.metric("Correctivo de Emergencia", f"{metrics.get('mce_pct', 0):.1f}%")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    # Tipo de mantenimiento por semana - BARRAS APILADAS
                    if not weekly_data.empty:
                        # Primero necesitamos obtener los datos semanales por tipo de mantenimiento
                        df_weekly_mtto = filtered_data.copy()
                        df_weekly_mtto['SEMANA'] = df_weekly_mtto['FECHA_DE_EJECUCION'].dt.isocalendar().week
                        df_weekly_mtto['AÑO'] = df_weekly_mtto['FECHA_DE_EJECUCION'].dt.year
                        df_weekly_mtto['SEMANA_STR'] = df_weekly_mtto['AÑO'].astype(str) + '-S' + df_weekly_mtto['SEMANA'].astype(str).str.zfill(2)
                        
                        # Agrupar por semana y tipo de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO (sin filtrar por producción afectada)
                        tipo_mtto_semana = df_weekly_mtto.groupby(['SEMANA_STR', 'TIPO DE MTTO'])['TR_MIN'].sum().reset_index()
                        
                        # Ordenar por semana
                        tipo_mtto_semana = tipo_mtto_semana.sort_values('SEMANA_STR')
                        
                        # Obtener todos los tipos de mantenimiento únicos
                        tipos_mtto_unicos = filtered_data['TIPO DE MTTO'].unique()
                        orden_categorias = sorted(tipos_mtto_unicos)
                        
                        # Si hay tipos específicos conocidos, podemos ordenarlos de manera específica
                        tipos_ordenados = []
                        for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PLANIFICADO Y PROGRAMADO', 'CORRECTIVO DE EMERGENCIA']:
                            if tipo in tipos_mtto_unicos:
                                tipos_ordenados.append(tipo)
                        
                        # Agregar cualquier otro tipo que no esté en la lista ordenada
                        for tipo in tipos_mtto_unicos:
                            if tipo not in tipos_ordenados:
                                tipos_ordenados.append(tipo)
                        
                        tipo_mtto_semana['TIPO DE MTTO'] = pd.Categorical(tipo_mtto_semana['TIPO DE MTTO'], categories=tipos_ordenados, ordered=True)
                        tipo_mtto_semana = tipo_mtto_semana.sort_values(['SEMANA_STR', 'TIPO DE MTTO'])
                        
                        # Crear gráfico de barras apiladas con colores específicos
                        fig = px.bar(tipo_mtto_semana, x='SEMANA_STR', y='TR_MIN', color='TIPO DE MTTO',
                                    title='Tipo de Mantenimiento por Semana (Barras Apiladas) - Todos los Tipos',
                                    labels={'SEMANA_STR': 'Semana', 'TR_MIN': 'Tiempo (min)'},
                                    color_discrete_map=COLOR_PALETTE['tipo_mtto'],
                                    category_orders={'TIPO DE MTTO': tipos_ordenados})
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Distribución de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO (sin filtrar por producción afectada)
                    tipo_mtto_totals = filtered_data.groupby('TIPO DE MTTO')['TR_MIN'].sum().reset_index()
                    
                    # Obtener todos los tipos de mantenimiento únicos
                    tipos_mtto_unicos = filtered_data['TIPO DE MTTO'].unique()
                    tipos_ordenados = sorted(tipos_mtto_unicos)
                    
                    # Si hay tipos específicos conocidos, podemos ordenarlos de manera específica
                    tipos_ordenados = []
                    for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PLANIFICADO Y PROGRAMADO', 'CORRECTIVO DE EMERGENCIA']:
                        if tipo in tipos_mtto_unicos:
                            tipos_ordenados.append(tipo)
                    
                    # Agregar cualquier otro tipo que no esté en la lista ordenada
                    for tipo in tipos_mtto_unicos:
                        if tipo not in tipos_ordenados:
                            tipos_ordenados.append(tipo)
                    
                    tipo_mtto_totals['TIPO DE MTTO'] = pd.Categorical(tipo_mtto_totals['TIPO DE MTTO'], categories=tipos_ordenados, ordered=True)
                    tipo_mtto_totals = tipo_mtto_totals.sort_values('TIPO DE MTTO')
                    
                    # Crear un mapa de colores extendido para incluir todos los tipos
                    color_map_extendido = COLOR_PALETTE['tipo_mtto'].copy()
                    colores_adicionales = ['#FFA500', '#800080', '#008000', '#FF69B4', '#00CED1']  # Colores para tipos adicionales
                    
                    for i, tipo in enumerate(tipos_ordenados):
                        if tipo not in color_map_extendido:
                            # Asignar un color de la lista de colores adicionales
                            color_map_extendido[tipo] = colores_adicionales[i % len(colores_adicionales)]
                    
                    fig = px.pie(tipo_mtto_totals, values='TR_MIN', names='TIPO DE MTTO',
                                title='Distribución de Mantenimiento - Todos los Tipos',
                                color='TIPO DE MTTO',
                                color_discrete_map=color_map_extendido,
                                category_orders={'TIPO DE MTTO': tipos_ordenados})
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Confiabilidad
        with tab6:
            st.header("Indicadores de Confiabilidad")
            
            if not filtered_data.empty:
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Total Fallas", f"{metrics.get('total_fallas', 0):,.0f}")
                
                with col2:
                    st.metric("MTBF", f"{metrics.get('mtbf', 0):,.1f}", "minutos")
                
                with col3:
                    st.metric("MTTF", f"{metrics.get('mttf', 0):,.1f}", "minutos")
                
                with col4:
                    st.metric("MTTR", f"{metrics.get('mttr', 0):,.1f}", "minutos")
                
                with col5:
                    st.metric("Mantenibilidad", f"{metrics.get('mantenibilidad', 0)*100:.1f}%")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    # Total de fallas por semana
                    if not weekly_data.empty:
                        fig = px.bar(weekly_data, x='SEMANA_STR', y='PRODUCCION_AFECTADA',
                                    title='Total de Fallas por Semana',
                                    labels={'SEMANA_STR': 'Semana', 'PRODUCCION_AFECTADA': 'Fallas'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][4])
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # MTBF por semana
                    if not weekly_data.empty:
                        weekly_data['MTBF_SEMANAL'] = weekly_data['TDISPONIBLE'] / weekly_data['PRODUCCION_AFECTADA']
                        weekly_data['MTBF_SEMANAL'] = weekly_data['MTBF_SEMANAL'].replace([np.inf, -np.inf], 0)
                        
                        fig = px.line(weekly_data, x='SEMANA_STR', y='MTBF_SEMANAL',
                                     title='MTBF por Semana',
                                     labels={'SEMANA_STR': 'Semana', 'MTBF_SEMANAL': 'MTBF (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][5], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
    
    else:
        st.info("Por favor, carga datos para comenzar.")
        
        # Mostrar instrucciones
        st.subheader("Instrucciones:")
        st.markdown("""
        1. **Para usar Google Sheets (Recomendado):**
           - Asegúrate de que el archivo de Google Sheets sea público
           - Selecciona "Google Sheets (Recomendado)" en la barra lateral
           - Haz clic en "Cargar/Actualizar desde Google Sheets"
        
        2. **Para usar archivo local:**
           - Selecciona "Archivo Local" en la barra lateral
           - Carga tu archivo Excel con los datos de mantenimiento
        
        3. **Estructura del archivo:**
           - Los datos deben estar en una hoja llamada 'DATAMTTO'
           - Incluir columnas como: FECHA EJECUCIÓN, EQUIPO, COMPONENTE, TIPO DE MTTO, etc.
        
        4. **Actualizaciones automáticas:**
           - Los datos de Google Sheets se actualizan automáticamente cada 5 minutos
           - Puedes forzar una actualización con el botón "Forzar Actualización de Datos"
        """)

if __name__ == "__main__":
    main()
