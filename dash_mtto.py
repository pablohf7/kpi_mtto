import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from datetime import datetime, timedelta

# Configuración de la página - BARRA LATERAL RECOGIDA POR DEFECTO
st.set_page_config(
    page_title="Dashboard de Indicadores de Mantenimiento",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Paleta de colores específicos para tipos de mantenimiento
COLOR_PALETTE = {
    'pastel': ['#AEC6CF', '#FFB3BA', '#FFDFBA', '#BAFFC9', '#BAE1FF', '#F0E6EF', '#C9C9FF', '#FFC9F0'],
    'tipo_mtto': {
        'PREVENTIVO': '#87CEEB',
        'BASADO EN CONDICIÓN': '#00008B',
        'CORRECTIVO PROGRAMADO': '#FFD700',
        'CORRECTIVO DE EMERGENCIA': '#FF0000',
        'MEJORA DE SISTEMA': '#32CD32'
    }
}

# Función para calcular la duración en minutos entre dos fechas y horas
def calcular_duracion_minutos(fecha_inicio, hora_inicio, fecha_fin, hora_fin):
    try:
        # Combinar fecha y hora
        datetime_inicio = pd.to_datetime(fecha_inicio.strftime('%Y-%m-%d') + ' ' + str(hora_inicio))
        datetime_fin = pd.to_datetime(fecha_fin.strftime('%Y-%m-%d') + ' ' + str(hora_fin))
        
        # Calcular diferencia en minutos
        duracion = (datetime_fin - datetime_inicio).total_seconds() / 60
        return max(duracion, 0)  # Asegurar que no sea negativo
    except:
        return 0

# Función para cargar datos desde Google Sheets
@st.cache_data(ttl=300)
def load_data_from_google_sheets():
    try:
        # ID del archivo de Google Sheets
        sheet_id = "1X3xgXkeyoei0WkgoNV54zx83XkIKhDlOVEo93lsaFB0"
        
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

def clean_and_prepare_data(df):
    # Hacer una copia para no modificar el original
    df_clean = df.copy()
    
    # Renombrar columnas para consistencia
    df_clean = df_clean.rename(columns={
        'FECHA DE INICIO': 'FECHA_DE_INICIO',
        'FECHA DE FIN': 'FECHA_DE_FIN',
        'Tiempo Prog (min)': 'TIEMPO_PROG_MIN',
        'PRODUCCIÓN AFECTADA (SI-NO)': 'PRODUCCION_AFECTADA',
        'TIEMPO ESTIMADO DIARIO (min)': 'TDISPONIBLE',
        'TR (min)': 'TR_MIN',
        'TFC (min)': 'TFC_MIN',
        'TFS (min)': 'TFS_MIN',
        'h normal (min)': 'H_NORMAL_MIN',
        'h extra (min)': 'H_EXTRA_MIN',
        'HORA PARADA DE MÁQUINA': 'HORA_PARADA',
        'HORA INICIO': 'HORA_INICIO',
        'HORA FINAL': 'HORA_FINAL',
        'HORA DE ARRANQUE': 'HORA_ARRANQUE'
    })
    
    # Manejar la columna de ubicación técnica
    if 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'UBICACION TECNICA' in df_clean.columns:
        df_clean = df_clean.rename(columns={'UBICACION TECNICA': 'UBICACIÓN TÉCNICA'})
    elif 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'Ubicación Técnica' in df_clean.columns:
        df_clean = df_clean.rename(columns={'Ubicación Técnica': 'UBICACIÓN TÉCNICA'})
    
    # Convertir fechas
    df_clean['FECHA_DE_INICIO'] = pd.to_datetime(df_clean['FECHA_DE_INICIO'])
    df_clean['FECHA_DE_FIN'] = pd.to_datetime(df_clean['FECHA_DE_FIN'])
    
    # Calcular TR_MIN (Tiempo Real) basado en fecha/hora de inicio y fin
    df_clean['TR_MIN_CALCULADO'] = df_clean.apply(
        lambda x: calcular_duracion_minutos(
            x['FECHA_DE_INICIO'], x['HORA_INICIO'], 
            x['FECHA_DE_FIN'], x['HORA_FINAL']
        ), axis=1
    )
    
    # Usar TR calculado si la columna original está vacía o es cero
    if 'TR_MIN' in df_clean.columns:
        df_clean['TR_MIN'] = df_clean.apply(
            lambda x: x['TR_MIN_CALCULADO'] if pd.isna(x['TR_MIN']) or x['TR_MIN'] == 0 else x['TR_MIN'], 
            axis=1
        )
    else:
        df_clean['TR_MIN'] = df_clean['TR_MIN_CALCULADO']
    
    # Asegurar que las columnas numéricas sean numéricas
    numeric_columns = ['TR_MIN', 'TFC_MIN', 'TFS_MIN', 'TDISPONIBLE', 'TIEMPO_PROG_MIN', 'H_EXTRA_MIN']
    for col in numeric_columns:
        if col in df_clean.columns:
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
        m['mcp_pct'] = (tipo_mtto_totals.get('CORRECTIVO PROGRAMADO', 0) / total_mtto) * 100
        m['mms_pct'] = (tipo_mtto_totals.get('MEJORA DE SISTEMA', 0) / total_mtto) * 100
    else:
        m['mp_pct'] = m['mbc_pct'] = m['mce_pct'] = m['mcp_pct'] = m['mms_pct'] = 0
    
    # Horas extras acumuladas
    m['horas_extras_acumuladas'] = df['H_EXTRA_MIN'].sum() if 'H_EXTRA_MIN' in df.columns else 0
    
    return m

# Función para calcular métricas de confiabilidad basadas en correctivos de emergencia
def calculate_reliability_metrics(df):
    if df.empty:
        return {}
    
    # Filtrar solo correctivos de emergencia (independientemente de producción afectada)
    emergency_mask = df['TIPO DE MTTO'] == 'CORRECTIVO DE EMERGENCIA'
    df_emergency = df[emergency_mask].copy()
    
    if df_emergency.empty:
        return {}
    
    # Calcular métricas de confiabilidad
    m = {}
    
    # Tiempo Disponible (suma del tiempo estimado diario)
    m['td'] = df['TDISPONIBLE'].sum() if 'TDISPONIBLE' in df.columns else 0
    
    # Calcular TR, TFC, TFS para correctivos de emergencia
    m['tr_emergency'] = df_emergency['TR_MIN'].sum() if 'TR_MIN' in df_emergency.columns else 0
    m['tfc_emergency'] = df_emergency['TFC_MIN'].sum() if 'TFC_MIN' in df_emergency.columns else 0
    m['tfs_emergency'] = df_emergency['TFS_MIN'].sum() if 'TFS_MIN' in df_emergency.columns else 0
    
    # Total de fallas (todas las órdenes de correctivo de emergencia)
    m['total_fallas_emergency'] = len(df_emergency)
    
    # Total de fallas con parada (emergencias que afectan producción)
    m['total_fallas_emergency_con_parada'] = len(df_emergency[df_emergency['PRODUCCION_AFECTADA'] == 'SI'])
    
    # Calcular MTBF, MTTF, MTTR basados en correctivos de emergencia
    if m['total_fallas_emergency'] > 0:
        m['mtbf_emergency'] = m['td'] / m['total_fallas_emergency'] if m['td'] > 0 else 0
        m['mttr_emergency'] = m['tr_emergency'] / m['total_fallas_emergency'] if m['total_fallas_emergency'] > 0 else 0
        
        # Tiempo Operativo basado en correctivos de emergencia que afectan producción
        emergency_prod_mask = (df_emergency['PRODUCCION_AFECTADA'] == 'SI')
        tfs_emergency_prod = df_emergency[emergency_prod_mask]['TFS_MIN'].sum() if 'TFS_MIN' in df_emergency.columns else 0
        to_emergency = max(m['td'] - tfs_emergency_prod, 0)
        m['mttf_emergency'] = to_emergency / m['total_fallas_emergency'] if m['total_fallas_emergency'] > 0 else 0
    else:
        m['mtbf_emergency'] = 0
        m['mttr_emergency'] = 0
        m['mttf_emergency'] = 0
    
    # Mantenibilidad basada en correctivos de emergencia
    landa_emergency = m['total_fallas_emergency'] / m['td'] if m['td'] > 0 else 0
    m['mantenibilidad_emergency'] = 1 - np.exp(-landa_emergency * m['td']) if landa_emergency > 0 else 0
    
    # Mantenibilidad en porcentaje
    m['mantenibilidad_pct'] = m['mantenibilidad_emergency'] * 100
    
    return m

# Función para obtener datos semanales
def get_weekly_data(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
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

# Función para obtener datos semanales de horas extras
def get_weekly_extra_hours(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
    df_weekly['SEMANA_STR'] = df_weekly['AÑO'].astype(str) + '-S' + df_weekly['SEMANA'].astype(str).str.zfill(2)
    
    # Agrupar por semana - TODOS LOS REGISTROS
    weekly_extra_data = df_weekly.groupby(['SEMANA_STR', 'AÑO', 'SEMANA']).agg({
        'H_EXTRA_MIN': 'sum'
    }).reset_index()
    
    # Crear columna numérica para ordenar correctamente las semanas
    weekly_extra_data['SEMANA_NUM'] = weekly_extra_data['AÑO'].astype(str) + weekly_extra_data['SEMANA'].astype(str).str.zfill(2)
    weekly_extra_data = weekly_extra_data.sort_values('SEMANA_NUM')
    
    return weekly_extra_data

# Función para obtener datos semanales de correctivos de emergencia (con MTTR)
def get_weekly_emergency_data(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
    df_weekly['SEMANA_STR'] = df_weekly['AÑO'].astype(str) + '-S' + df_weekly['SEMANA'].astype(str).str.zfill(2)
    
    # Filtrar solo correctivos de emergencia (independientemente de producción afectada)
    df_emergency = df_weekly[df_weekly['TIPO DE MTTO'] == 'CORRECTIVO DE EMERGENCIA'].copy()
    
    if df_emergency.empty:
        return pd.DataFrame()
    
    # Agrupar por semana para calcular MTTR semanal
    weekly_emergency_data = df_emergency.groupby(['SEMANA_STR', 'AÑO', 'SEMANA']).agg({
        'TR_MIN': 'sum',
        'TFC_MIN': 'sum',
        'TFS_MIN': 'sum',
        'TDISPONIBLE': 'first'  # Tomar el primer valor como referencia
    }).reset_index()
    
    # Contar número de órdenes de correctivo de emergencia por semana
    weekly_emergency_counts = df_emergency.groupby(['SEMANA_STR', 'AÑO', 'SEMANA']).size().reset_index(name='NUM_ORDENES_EMERGENCIA')
    
    # Contar número de órdenes de correctivo de emergencia CON PARADA por semana
    weekly_emergency_parada_counts = df_emergency[df_emergency['PRODUCCION_AFECTADA'] == 'SI'].groupby(['SEMANA_STR', 'AÑO', 'SEMANA']).size().reset_index(name='NUM_ORDENES_EMERGENCIA_PARADA')
    
    # Combinar los datos
    weekly_emergency_data = weekly_emergency_data.merge(weekly_emergency_counts, on=['SEMANA_STR', 'AÑO', 'SEMANA'], how='left')
    weekly_emergency_data = weekly_emergency_data.merge(weekly_emergency_parada_counts, on=['SEMANA_STR', 'AÑO', 'SEMANA'], how='left')
    
    # Rellenar NaN con 0 para las órdenes con parada
    weekly_emergency_data['NUM_ORDENES_EMERGENCIA_PARADA'] = weekly_emergency_data['NUM_ORDENES_EMERGENCIA_PARADA'].fillna(0)
    
    # Calcular MTTR semanal (Tiempo de Reparación / Número de órdenes)
    weekly_emergency_data['MTTR_SEMANAL'] = weekly_emergency_data.apply(
        lambda row: row['TR_MIN'] / row['NUM_ORDENES_EMERGENCIA'] if row['NUM_ORDENES_EMERGENCIA'] > 0 else 0, 
        axis=1
    )
    
    # Crear columna numérica para ordenar correctamente las semanas
    weekly_emergency_data['SEMANA_NUM'] = weekly_emergency_data['AÑO'].astype(str) + weekly_emergency_data['SEMANA'].astype(str).str.zfill(2)
    weekly_emergency_data = weekly_emergency_data.sort_values('SEMANA_NUM')
    
    return weekly_emergency_data

# Función para aplicar filtros - ACTUALIZADA
def apply_filters(df, equipo_filter, conjunto_filter, ubicacion_filter, fecha_inicio, fecha_fin):
    filtered_df = df.copy()
    
    if equipo_filter != "Todos":
        # Convertir a string para comparación
        filtered_df = filtered_df[filtered_df['EQUIPO'].astype(str) == equipo_filter]
    
    if conjunto_filter != "Todos":
        # Convertir a string para comparación
        filtered_df = filtered_df[filtered_df['CONJUNTO'].astype(str) == conjunto_filter]
    
    if ubicacion_filter != "Todos":
        if 'UBICACIÓN TÉCNICA' in filtered_df.columns:
            # Convertir a string para comparación
            filtered_df = filtered_df[filtered_df['UBICACIÓN TÉCNICA'].astype(str) == ubicacion_filter]
    
    # Aplicar filtro de fechas - USAR FECHA_DE_INICIO
    if fecha_inicio is not None and fecha_fin is not None:
        filtered_df = filtered_df[
            (filtered_df['FECHA_DE_INICIO'].dt.date >= fecha_inicio) &
            (filtered_df['FECHA_DE_INICIO'].dt.date <= fecha_fin)
        ]
    
    return filtered_df

# Función para obtener la fecha y hora actual en formato español
def get_current_datetime_spanish():
    now = datetime.now()
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    day = now.day
    month = months[now.month - 1]
    year = now.year
    time_str = now.strftime("%H:%M:%S")
    
    return f"{day} de {month} de {year}, {time_str}"

# Función para formatear fecha en formato DD/MM/AAAA
def format_date_dd_mm_aaaa(date):
    """Formatea una fecha en formato DD/MM/AAAA"""
    if isinstance(date, (datetime, pd.Timestamp)):
        return date.strftime('%d/%m/%Y')
    elif isinstance(date, str):
        try:
            return pd.to_datetime(date).strftime('%d/%m/%Y')
        except:
            return date
    else:
        return str(date)

# Interfaz principal
def main():
    st.title("📊 Dashboard de Indicadores de Mantenimiento Mecánico Fortidex")
    
    # Inicializar datos en session_state si no existen
    if 'data' not in st.session_state:
        st.session_state.data = pd.DataFrame()
    
    if 'last_update' not in st.session_state:
        st.session_state.last_update = None
    
    # CARGA AUTOMÁTICA DESDE GOOGLE SHEETS AL INICIAR
    if st.session_state.data.empty:
        with st.spinner("Cargando datos desde Google Sheets..."):
            df = load_data_from_google_sheets()
            if not df.empty:
                st.session_state.data = df
                st.session_state.last_update = get_current_datetime_spanish()
                st.success("✅ Datos cargados correctamente desde Google Sheets")
            else:
                st.error("❌ No se pudieron cargar los datos desde Google Sheets")
    
    # Sidebar
    st.sidebar.title("Opciones")
    
    # MOSTRAR ESTADO DE LA CARGA AUTOMÁTICA
    if not st.session_state.data.empty and st.session_state.last_update:
        st.sidebar.markdown(f"**📅Última actualización:**")
        st.sidebar.markdown(f"`{st.session_state.last_update}`")
        st.sidebar.write(f"**Registros totales:** {len(st.session_state.data)}")
    
    # Filtros
    st.sidebar.subheader("Filtros")
    
    if not st.session_state.data.empty:
        # 1. FILTRO DE FECHA - USAR FECHA_DE_INICIO
        min_date = st.session_state.data['FECHA_DE_INICIO'].min().date()
        max_date = st.session_state.data['FECHA_DE_INICIO'].max().date()
        
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
        
        # Mostrar las fechas seleccionadas en formato DD/MM/AAAA
        fecha_inicio_str = format_date_dd_mm_aaaa(fecha_inicio)
        fecha_fin_str = format_date_dd_mm_aaaa(fecha_fin)
        st.sidebar.write(f"**Período seleccionado:**")
        st.sidebar.write(f"**Desde:** {fecha_inicio_str}")
        st.sidebar.write(f"**Hasta:** {fecha_fin_str}")
        
        # 2. FILTRO DE UBICACIÓN TÉCNICA
        if 'UBICACIÓN TÉCNICA' in st.session_state.data.columns:
            ubicaciones_unique = st.session_state.data['UBICACIÓN TÉCNICA'].dropna().unique().tolist()
            ubicaciones_str = [str(x) for x in ubicaciones_unique]
            ubicaciones = ["Todos"] + sorted(ubicaciones_str)
        else:
            ubicaciones = ["Todos"]
        
        ubicacion_filter = st.sidebar.selectbox("Ubicación Técnica", ubicaciones)
        
        # 3. FILTRO DE EQUIPOS - CORREGIDO
        equipos_unique = st.session_state.data['EQUIPO'].unique().tolist()
        equipos_str = [str(x) for x in equipos_unique]
        equipos = ["Todos"] + sorted(equipos_str)
        equipo_filter = st.sidebar.selectbox("Equipo", equipos)
        
        # 4. FILTRO DE CONJUNTOS - CORREGIDO
        conjuntos_unique = st.session_state.data['CONJUNTO'].unique().tolist()
        conjuntos_str = [str(x) for x in conjuntos_unique]
        conjuntos = ["Todos"] + sorted(conjuntos_str)
        conjunto_filter = st.sidebar.selectbox("Conjunto", conjuntos)
        
        # Aplicar filtros
        filtered_data = apply_filters(st.session_state.data, equipo_filter, conjunto_filter, 
                                      ubicacion_filter, fecha_inicio, fecha_fin)
        
        # Mostrar información de estado
        st.sidebar.subheader("Estado")
        st.sidebar.write(f"**Registros filtrados:** {len(filtered_data)}")
        st.sidebar.write(f"**Equipos únicos:** {len(filtered_data['EQUIPO'].unique())}")
        if not filtered_data.empty and 'FECHA_DE_INICIO' in filtered_data.columns:
            min_date_filtered = filtered_data['FECHA_DE_INICIO'].min()
            max_date_filtered = filtered_data['FECHA_DE_INICIO'].max()
            
            # Formatear las fechas en DD/MM/AAAA
            min_date_str = format_date_dd_mm_aaaa(min_date_filtered)
            max_date_str = format_date_dd_mm_aaaa(max_date_filtered)
            
            st.sidebar.write(f"**Período:** {min_date_str} a {max_date_str}")
        
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
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Planta", "TFS", "TR", "TFC", "Tipo de Mtto", "Confiabilidad", "Horas Extras"])
        
        # Calcular métricas
        metrics = calculate_metrics(filtered_data)
        weekly_data = get_weekly_data(filtered_data)
        weekly_extra_data = get_weekly_extra_hours(filtered_data)
        
        # Calcular métricas de confiabilidad específicas para correctivos de emergencia
        reliability_metrics = calculate_reliability_metrics(filtered_data)
        
        # Obtener datos semanales de correctivos de emergencia
        weekly_emergency_data = get_weekly_emergency_data(filtered_data)
        
        # Pestaña Planta - CORREGIDA
        with tab1:
            st.header("📈 Indicadores de Planta")
            
            if not filtered_data.empty:
                # Métricas principales
                col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
                
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
                    tr = metrics.get('tr', 0)
                    st.metric("TR", f"{tr:,.0f}", "minutos")
                
                with col7:
                    tfc = metrics.get('tfc', 0)
                    st.metric("TFC", f"{tfc:,.0f}", "minutos")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='DISPO_SEMANAL', 
                                     title='Disponibilidad por Semana (%)',
                                     labels={'SEMANA_STR': 'Semana', 'DISPO_SEMANAL': 'Disponibilidad (%)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][0], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para mostrar")
                
                with col2:
                    if not weekly_data.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Bar(x=weekly_data['SEMANA_STR'], y=weekly_data['TR_MIN'], name='TR', 
                                            marker_color='#FFD700'))
                        fig.add_trace(go.Bar(x=weekly_data['SEMANA_STR'], y=weekly_data['TFC_MIN'], name='TFC', 
                                            marker_color='#FFB3BA'))
                        fig.update_layout(title='TR y TFC por Semana', barmode='stack')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para mostrar")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TFS - COMPLETA
        with tab2:
            st.header("Análisis de TFS")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TFS_MIN',
                                     title='TFS por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TFS_MIN': 'TFS (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][1], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para mostrar")
                
                with col2:
                    tfs_por_equipo = filtered_afecta.groupby('EQUIPO')['TFS_MIN'].sum().reset_index()
                    tfs_por_equipo = tfs_por_equipo.sort_values('TFS_MIN', ascending=False).head(10)
                    
                    if not tfs_por_equipo.empty:
                        fig = px.bar(tfs_por_equipo, x='EQUIPO', y='TFS_MIN',
                                    title='TFS por Equipo',
                                    labels={'EQUIPO': 'Equipo', 'TFS_MIN': 'TFS (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][1])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TFS por equipo")
                
                # TFS por conjunto
                tfs_por_conjunto = filtered_afecta.groupby('CONJUNTO')['TFS_MIN'].sum().reset_index()
                tfs_por_conjunto = tfs_por_conjunto.sort_values('TFS_MIN', ascending=False).head(10)
                
                if not tfs_por_conjunto.empty:
                    fig = px.bar(tfs_por_conjunto, x='CONJUNTO', y='TFS_MIN',
                                title='TFS por Conjunto',
                                labels={'CONJUNTO': 'Conjunto', 'TFS_MIN': 'TFS (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][1])
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de TFS por conjunto")
                
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
                    st.subheader("Resumen TFS por Conjunto")
                    resumen_conjunto = filtered_afecta.groupby('CONJUNTO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_conjunto.head(10), use_container_width=True)
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TR - COMPLETA
        with tab3:
            st.header("Análisis de TR")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TR_MIN',
                                     title='TR por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TR_MIN': 'TR (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][2], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para mostrar")
                
                with col2:
                    tr_por_equipo = filtered_afecta.groupby('EQUIPO')['TR_MIN'].sum().reset_index()
                    tr_por_equipo = tr_por_equipo.sort_values('TR_MIN', ascending=False).head(10)
                    
                    if not tr_por_equipo.empty:
                        fig = px.bar(tr_por_equipo, x='EQUIPO', y='TR_MIN',
                                    title='TR por Equipo',
                                    labels={'EQUIPO': 'Equipo', 'TR_MIN': 'TR (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][2])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TR por equipo")
                
                # Pareto TR por conjunto
                tr_por_conjunto = filtered_afecta.groupby('CONJUNTO')['TR_MIN'].sum().reset_index()
                tr_por_conjunto = tr_por_conjunto.sort_values('TR_MIN', ascending=False).head(15)
                
                if not tr_por_conjunto.empty:
                    fig = px.bar(tr_por_conjunto, x='CONJUNTO', y='TR_MIN',
                                title='Pareto TR por Conjunto',
                                labels={'CONJUNTO': 'Conjunto', 'TR_MIN': 'TR (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][2])
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de TR por conjunto")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TFC - COMPLETA
        with tab4:
            st.header("Análisis de TFC")
            
            if not filtered_data.empty:
                # Filtrar solo registros que afectan producción
                filtered_afecta = filtered_data[filtered_data['PRODUCCION_AFECTADA'] == 'SI']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if not weekly_data.empty:
                        fig = px.line(weekly_data, x='SEMANA_STR', y='TFC_MIN',
                                     title='TFC por Semana (Minutos)',
                                     labels={'SEMANA_STR': 'Semana', 'TFC_MIN': 'TFC (min)'})
                        fig.update_traces(line_color=COLOR_PALETTE['pastel'][3], mode='lines+markers')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para mostrar")
                
                with col2:
                    tfc_por_equipo = filtered_afecta.groupby('EQUIPO')['TFC_MIN'].sum().reset_index()
                    tfc_por_equipo = tfc_por_equipo.sort_values('TFC_MIN', ascending=False).head(10)
                    
                    if not tfc_por_equipo.empty:
                        fig = px.bar(tfc_por_equipo, x='EQUIPO', y='TFC_MIN',
                                    title='TFC por Equipo',
                                    labels={'EQUIPO': 'Equipo', 'TFC_MIN': 'TFC (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][3])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TFC por equipo")
                
                # Pareto TFC por conjunto
                tfc_por_conjunto = filtered_afecta.groupby('CONJUNTO')['TFC_MIN'].sum().reset_index()
                tfc_por_conjunto = tfc_por_conjunto.sort_values('TFC_MIN', ascending=False).head(15)
                
                if not tfc_por_conjunto.empty:
                    fig = px.bar(tfc_por_conjunto, x='CONJUNTO', y='TFC_MIN',
                                title='Pareto TFC por Conjunto',
                                labels={'CONJUNTO': 'Conjunto', 'TFC_MIN': 'TFC (min)'})
                    fig.update_traces(marker_color=COLOR_PALETTE['pastel'][3])
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de TFC por conjunto")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Tipo de Mantenimiento - COMPLETA
        with tab5:
            st.header("Análisis por Tipo de Mantenimiento")
            
            if not filtered_data.empty:
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Mantenimiento Preventivo", f"{metrics.get('mp_pct', 0):.1f}%")
                
                with col2:
                    st.metric("Mant. Basado en Condición", f"{metrics.get('mbc_pct', 0):.1f}%")
                
                with col3:
                    st.metric("Correctivo Programado", f"{metrics.get('mcp_pct', 0):.1f}%")
                
                with col4:
                    st.metric("Correctivo de Emergencia", f"{metrics.get('mce_pct', 0):.1f}%")
                
                with col5:
                    st.metric("Mejora de Sistema", f"{metrics.get('mms_pct', 0):.1f}%")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    # Tipo de mantenimiento por semana - BARRAS APILADAS
                    df_weekly_mtto = filtered_data.copy()
                    df_weekly_mtto['SEMANA'] = df_weekly_mtto['FECHA_DE_INICIO'].dt.isocalendar().week
                    df_weekly_mtto['AÑO'] = df_weekly_mtto['FECHA_DE_INICIO'].dt.year
                    df_weekly_mtto['SEMANA_STR'] = df_weekly_mtto['AÑO'].astype(str) + '-S' + df_weekly_mtto['SEMANA'].astype(str).str.zfill(2)
                    
                    # Agrupar por semana y tipo de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO
                    tipo_mtto_semana = df_weekly_mtto.groupby(['SEMANA_STR', 'TIPO DE MTTO'])['TR_MIN'].sum().reset_index()
                    
                    # Ordenar por semana
                    tipo_mtto_semana = tipo_mtto_semana.sort_values('SEMANA_STR')
                    
                    # Obtener todos los tipos de mantenimiento únicos
                    tipos_mtto_unicos = filtered_data['TIPO DE MTTO'].unique()
                    
                    # Ordenar los tipos de mantenimiento
                    tipos_ordenados = []
                    for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PROGRAMADO', 'CORRECTIVO DE EMERGENCIA', 'MEJORA DE SISTEMA']:
                        if tipo in tipos_mtto_unicos:
                            tipos_ordenados.append(tipo)
                    
                    # Agregar cualquier otro tipo que no esté en la lista ordenada
                    for tipo in tipos_mtto_unicos:
                        if tipo not in tipos_ordenados:
                            tipos_ordenados.append(tipo)
                    
                    tipo_mtto_semana['TIPO DE MTTO'] = pd.Categorical(tipo_mtto_semana['TIPO DE MTTO'], categories=tipos_ordenados, ordered=True)
                    tipo_mtto_semana = tipo_mtto_semana.sort_values(['SEMANA_STR', 'TIPO DE MTTO'])
                    
                    if not tipo_mtto_semana.empty:
                        # Crear gráfico de barras apiladas con colores específicos
                        fig = px.bar(tipo_mtto_semana, x='SEMANA_STR', y='TR_MIN', color='TIPO DE MTTO',
                                    title='Tipo de Mantenimiento por Semana (Barras Apiladas) - Todos los Tipos',
                                    labels={'SEMANA_STR': 'Semana', 'TR_MIN': 'Tiempo (min)'},
                                    color_discrete_map=COLOR_PALETTE['tipo_mtto'],
                                    category_orders={'TIPO DE MTTO': tipos_ordenados})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de tipo de mantenimiento por semana")
                
                with col2:
                    # Distribución de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO
                    tipo_mtto_totals = filtered_data.groupby('TIPO DE MTTO')['TR_MIN'].sum().reset_index()
                    
                    # Obtener todos los tipos de mantenimiento únicos
                    tipos_mtto_unicos = filtered_data['TIPO DE MTTO'].unique()
                    
                    # Ordenar los tipos de mantenimiento
                    tipos_ordenados = []
                    for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PROGRAMADO', 'CORRECTIVO DE EMERGENCIA', 'MEJORA DE SISTEMA']:
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
                    
                    if not tipo_mtto_totals.empty:
                        fig = px.pie(tipo_mtto_totals, values='TR_MIN', names='TIPO DE MTTO',
                                    title='Distribución de Mantenimiento - Todos los Tipos',
                                    color='TIPO DE MTTO',
                                    color_discrete_map=color_map_extendido,
                                    category_orders={'TIPO DE MTTO': tipos_ordenados})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de distribución de mantenimiento")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Confiabilidad - MODIFICADA con columnas específicas
        with tab6:
            st.header("Indicadores de Confiabilidad")
            
            if not filtered_data.empty:
                # Mostrar métricas específicas para correctivos de emergencia
                if reliability_metrics:
                    # Usamos 6 columnas para incluir el nuevo indicador
                    col1, col2, col3, col4, col5, col6 = st.columns(6)
                    
                    with col1:
                        st.metric("Total Fallas", f"{reliability_metrics.get('total_fallas_emergency', 0):,.0f}",
                                help="Número total de órdenes de correctivo de emergencia")
                    
                    with col2:
                        st.metric("Total Fallas con parada", 
                                f"{reliability_metrics.get('total_fallas_emergency_con_parada', 0):,.0f}",
                                help="Número de órdenes de correctivo de emergencia que detuvieron producción")
                    
                    with col3:
                        st.metric("MTBF", f"{reliability_metrics.get('mtbf_emergency', 0):,.1f}", "minutos",
                                help="MTBF basado en correctivos de emergencia")
                    
                    with col4:
                        st.metric("MTTF", f"{reliability_metrics.get('mttf_emergency', 0):,.1f}", "minutos",
                                help="MTTF basado en correctivos de emergencia")
                    
                    with col5:
                        st.metric("MTTR", f"{reliability_metrics.get('mttr_emergency', 0):,.1f}", "minutos",
                                help="MTTR basado en correctivos de emergencia")
                    
                    with col6:
                        mantenibilidad_pct = reliability_metrics.get('mantenibilidad_pct', 0)
                        st.metric("Mantenibilidad", f"{mantenibilidad_pct:.1f}%",
                                help="Mantenibilidad basada en correctivos de emergencia")
                else:
                    st.info("No hay datos de correctivos de emergencia para calcular las métricas")
                
                # Gráficos
                col1, col2 = st.columns(2)
                
                with col1:
                    # Total de fallas por semana (correctivos de emergencia)
                    if not weekly_emergency_data.empty:
                        # Crear gradiente de rojos: más fallas = rojo más oscuro, menos fallas = rojo más claro
                        fig = px.bar(weekly_emergency_data, x='SEMANA_STR', y='NUM_ORDENES_EMERGENCIA',
                                    title='Total de Fallas por Semana (Correctivos de Emergencia)',
                                    labels={'SEMANA_STR': 'Semana', 'NUM_ORDENES_EMERGENCIA': 'N° de Órdenes de Emergencia'},
                                    color='NUM_ORDENES_EMERGENCIA',
                                    color_continuous_scale='Reds')
                        fig.update_layout(showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales de correctivos de emergencia")
                
                with col2:
                    # MTTR por semana (reemplaza Mantenibilidad por Semana)
                    if not weekly_emergency_data.empty:
                        fig = px.line(weekly_emergency_data, x='SEMANA_STR', y='MTTR_SEMANAL',
                                     title='MTTR por Semana (Correctivos de Emergencia)',
                                     labels={'SEMANA_STR': 'Semana', 'MTTR_SEMANAL': 'MTTR (min)'},
                                     markers=True)
                        fig.update_traces(line_color='#FFA500', mode='lines+markers', line_width=3)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos semanales para calcular MTTR")
                
                # Información adicional - Distribución por Equipo y Conjunto (Top 10) CON RANKING Y COLUMNAS ESPECÍFICAS
                st.subheader("Distribución de Correctivos de Emergencia")
                
                # Filtrar correctivos de emergencia
                emergency_data = filtered_data[filtered_data['TIPO DE MTTO'] == 'CORRECTIVO DE EMERGENCIA']
                
                if not emergency_data.empty:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Distribución por Equipo (Top 10)**")
                        # Agrupar por equipo y contar
                        emergencia_por_equipo = emergency_data.groupby('EQUIPO').size().reset_index(name='CANTIDAD')
                        # Ordenar por cantidad descendente
                        emergencia_por_equipo = emergencia_por_equipo.sort_values('CANTIDAD', ascending=False).head(10)
                        # Agregar columna de ranking (lugar)
                        emergencia_por_equipo = emergencia_por_equipo.reset_index(drop=True)
                        emergencia_por_equipo.insert(0, 'LUGAR', range(1, len(emergencia_por_equipo) + 1))
                        # Formatear la columna LUGAR
                        emergencia_por_equipo['LUGAR'] = emergencia_por_equipo['LUGAR'].astype(str) + '°'
                        # Renombrar columnas según especificación
                        emergencia_por_equipo = emergencia_por_equipo.rename(columns={
                            'EQUIPO': 'EQUIPO',
                            'CANTIDAD': 'CANTIDAD DE FALLA'
                        })
                        # Seleccionar solo las columnas requeridas
                        emergencia_por_equipo = emergencia_por_equipo[['LUGAR', 'EQUIPO', 'CANTIDAD DE FALLA']]
                        st.dataframe(emergencia_por_equipo, use_container_width=True)
                    
                    with col2:
                        st.write("**Distribución por Conjunto (Top 10)**")
                        # Agrupar por conjunto y contar
                        emergencia_por_conjunto = emergency_data.groupby('CONJUNTO').size().reset_index(name='CANTIDAD')
                        # Ordenar por cantidad descendente
                        emergencia_por_conjunto = emergencia_por_conjunto.sort_values('CANTIDAD', ascending=False).head(10)
                        # Agregar columna de ranking (lugar)
                        emergencia_por_conjunto = emergencia_por_conjunto.reset_index(drop=True)
                        emergencia_por_conjunto.insert(0, 'LUGAR', range(1, len(emergencia_por_conjunto) + 1))
                        # Formatear la columna LUGAR
                        emergencia_por_conjunto['LUGAR'] = emergencia_por_conjunto['LUGAR'].astype(str) + '°'
                        # Renombrar columnas según especificación
                        emergencia_por_conjunto = emergencia_por_conjunto.rename(columns={
                            'CONJUNTO': 'CONJUNTO',
                            'CANTIDAD': 'CANTIDAD DE FALLA'
                        })
                        # Seleccionar solo las columnas requeridas
                        emergencia_por_conjunto = emergencia_por_conjunto[['LUGAR', 'CONJUNTO', 'CANTIDAD DE FALLA']]
                        st.dataframe(emergencia_por_conjunto, use_container_width=True)
                else:
                    st.info("No hay registros de correctivos de emergencia en el período seleccionado")
                
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Horas Extras - COMPLETA
        with tab7:
            st.header("⏰ Análisis de Horas Extras")
            
            if not filtered_data.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    horas_extras_acumuladas = metrics.get('horas_extras_acumuladas', 0)
                    horas_extras_acumuladas_horas = horas_extras_acumuladas / 60
                    st.metric(
                        "Horas Extras Acumuladas", 
                        f"{horas_extras_acumuladas_horas:.1f}", 
                        "horas"
                    )
                
                with col2:
                    pass
                
                st.subheader("Horas Extras Semanales")
                
                if not weekly_extra_data.empty:
                    weekly_extra_data_horas = weekly_extra_data.copy()
                    weekly_extra_data_horas['H_EXTRA_HORAS'] = weekly_extra_data_horas['H_EXTRA_MIN'] / 60
                    
                    fig = px.bar(
                        weekly_extra_data_horas, 
                        x='SEMANA_STR', 
                        y='H_EXTRA_HORAS',
                        title='Horas Extras por Semana',
                        labels={'SEMANA_STR': 'Semana', 'H_EXTRA_HORAS': 'Horas Extras'},
                        color='H_EXTRA_HORAS',
                        color_continuous_scale='Viridis'
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de horas extras para mostrar")
                
                # Tabla detallada de horas extras por semana
                st.subheader("Detalle de Horas Extras por Semana")
                if not weekly_extra_data.empty:
                    resumen_semanal = weekly_extra_data.copy()
                    resumen_semanal['HORAS_EXTRAS'] = resumen_semanal['H_EXTRA_MIN'] / 60
                    resumen_semanal = resumen_semanal[['SEMANA_STR', 'HORAS_EXTRAS']]
                    resumen_semanal = resumen_semanal.rename(columns={
                        'SEMANA_STR': 'Semana',
                        'HORAS_EXTRAS': 'Horas Extras'
                    })
                    st.dataframe(resumen_semanal, use_container_width=True)
                else:
                    st.info("No hay datos detallados de horas extras para mostrar")
                
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
    
    else:
        st.info("Por favor, carga datos para comenzar.")
        
        st.subheader("Instrucciones:")
        st.markdown("""
        1. **Carga automática desde Google Sheets:**
           - Los datos se cargan automáticamente desde Google Sheets al abrir la aplicación
           - Asegúrate de que el archivo de Google Sheets sea público y accesible
        
        2. **Estructura del archivo:**
           - Los datos deben estar en una hoja llamada 'DATAMTTO'
           - Incluir columnas como: FECHA DE INICIO, FECHA DE FIN, EQUIPO, CONJUNTO, TIPO DE MTTO, etc.
        
        3. **Actualizaciones automáticas:**
           - Los datos de Google Sheets se actualizan automáticamente cada 5 minutos
           - Recarga la página para obtener los datos más recientes
        """)

if __name__ == "__main__":
    main()
