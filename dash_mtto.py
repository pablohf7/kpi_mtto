import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from datetime import datetime, timedelta
import re

# Configuración de la página - BARRA LATERAL RECOGIDA POR DEFECTO
st.set_page_config(
    page_title="Dashboard de Indicadores de Mantenimiento Mecánico Fortidex",
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
    },
    'estado_orden': {
        'CULMINADAS': '#32CD32',  # Verde
        'EN EJECUCIÓN': '#FFD700',  # Amarillo
        'RETRASADAS': '#FFA500',  # Naranja
        'PROYECTADAS': '#52b3f3',  # Azul
        'TOTAL_PLANIFICADAS': "#02BFF8"  # Azul
    }
}

# Función para separar múltiples técnicos en el campo RESPONSABLE - MODIFICADA
def separar_tecnicos(df):
    """Separa múltiples técnicos en una sola celda y crea filas individuales
    CON HORAS COMPLETAS PARA CADA TÉCNICO"""
    if df.empty or 'RESPONSABLE' not in df.columns:
        return df
    
    # Crear copia para no modificar el original
    df_separado = df.copy()
    
    # Lista para almacenar las filas separadas
    filas_separadas = []
    
    # Delimitadores comunes para separar técnicos
    delimitadores = [',', ';', '|', '/', '\\', 'y', 'Y', '&']
    
    for idx, row in df_separado.iterrows():
        responsable = str(row['RESPONSABLE']).strip()
        
        # Si está vacío o es NaN, mantener como está
        if not responsable or responsable.lower() == 'nan':
            filas_separadas.append(row)
            continue
        
        # Intentar detectar si hay múltiples técnicos
        tecnicos_encontrados = []
        
        # Revisar si hay delimitadores comunes
        encontrado_delimitador = False
        for delim in delimitadores:
            if delim in responsable:
                # Separar por el delimitador
                partes = [p.strip() for p in responsable.split(delim) if p.strip()]
                if len(partes) > 1:
                    tecnicos_encontrados.extend(partes)
                    encontrado_delimitador = True
                    break
        
        # Si no se encontró delimitador, revisar si hay números (como "Técnico 1, Técnico 2")
        if not encontrado_delimitador:
            # Buscar patrones como "Técnico 1, Técnico 2" sin comas explícitas
            patrones = [
                r'(\w+\s+\d+\s*,\s*\w+\s+\d+)',  # "Técnico 1, Técnico 2"
                r'(\w+\s+y\s+\w+)',  # "Técnico A y Técnico B"
            ]
            
            for patron in patrones:
                coincidencias = re.findall(patron, responsable)
                if coincidencias:
                    # Intentar separar por coma o "y"
                    if ',' in responsable:
                        tecnicos_encontrados = [t.strip() for t in responsable.split(',') if t.strip()]
                    elif 'y' in responsable.lower():
                        partes = re.split(r'\s+y\s+', responsable, flags=re.IGNORECASE)
                        tecnicos_encontrados = [p.strip() for p in partes if p.strip()]
                    encontrado_delimitador = True
                    break
        
        # Si se encontraron múltiples técnicos, duplicar las filas con horas completas para cada técnico
        if len(tecnicos_encontrados) > 1:
            num_tecnicos = len(tecnicos_encontrados)
            
            for tecnico in tecnicos_encontrados:
                # Crear copia de la fila para cada técnico
                nueva_fila = row.copy()
                nueva_fila['RESPONSABLE'] = tecnico
                
                # **MODIFICACIÓN IMPORTANTE: Cada técnico recibe las horas COMPLETAS**
                # NO dividir las horas entre técnicos - cada uno recibe el total
                # Ejemplo: si trabajo tuvo 60 min normales y 60 min extras, cada técnico recibe 60 min normales y 60 min extras
                if 'TR_MIN' in nueva_fila:
                    # Mantener el mismo valor de TR_MIN para cada técnico (no dividir)
                    nueva_fila['TR_MIN'] = row['TR_MIN'] if pd.notna(row['TR_MIN']) else 0
                if 'H_EXTRA_MIN' in nueva_fila:
                    # Mantener el mismo valor de H_EXTRA_MIN para cada técnico (no dividir)
                    nueva_fila['H_EXTRA_MIN'] = row['H_EXTRA_MIN'] if pd.notna(row['H_EXTRA_MIN']) else 0
                if 'H_NORMAL_MIN' in nueva_fila:
                    # Mantener el mismo valor de H_NORMAL_MIN para cada técnico (no dividir)
                    nueva_fila['H_NORMAL_MIN'] = row['H_NORMAL_MIN'] if pd.notna(row['H_NORMAL_MIN']) else 0
                
                filas_separadas.append(nueva_fila)
        else:
            # Si solo hay un técnico, mantener la fila como está
            filas_separadas.append(row)
    
    # Crear nuevo DataFrame con las filas separadas
    df_resultado = pd.DataFrame(filas_separadas)
    
    return df_resultado

# Función para cargar datos del personal desde Google Sheets
@st.cache_data(ttl=300)
def load_personal_data_from_google_sheets():
    try:
        # ID del archivo de Google Sheets
        sheet_id = "1X3xgXkeyoei0WkgoNV54zx83XkIKhDlOVEo93lsaFB0"
        
        # Construir URL para exportar como CSV
        gsheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        
        # Leer la hoja PERSONAL
        df_personal = pd.read_excel(gsheet_url, sheet_name='PERSONAL')
        
        # Limpiar nombres de columnas
        df_personal.columns = [col.strip().upper() for col in df_personal.columns]
        
        return df_personal
    except Exception as e:
        st.error(f"Error al cargar datos del personal desde Google Sheets: {e}")
        return pd.DataFrame()

# Función para calcular costos de horas extras - VERSIÓN MEJORADA SEGÚN ESPECIFICACIONES
def calculate_overtime_costs(filtered_data, personal_data):
    if filtered_data.empty:
        return pd.DataFrame(), pd.DataFrame(), "No hay datos filtrados"
    
    # Primero separar los técnicos en el DataFrame filtrado
    filtered_data_separado = separar_tecnicos(filtered_data)
    
    # Filtrar solo registros con horas extras
    filtered_with_overtime = filtered_data_separado[filtered_data_separado['H_EXTRA_MIN'] > 0].copy()
    
    if filtered_with_overtime.empty:
        return pd.DataFrame(), pd.DataFrame(), "No hay registros con horas extras (H_EXTRA_MIN > 0)"
    
    # Verificar columna RESPONSABLE
    if 'RESPONSABLE' not in filtered_with_overtime.columns:
        return pd.DataFrame(), pd.DataFrame(), "No existe la columna 'RESPONSABLE' en los datos"
    
    # Filtrar registros con responsable
    filtered_with_overtime = filtered_with_overtime[filtered_with_overtime['RESPONSABLE'].notna()]
    
    if filtered_with_overtime.empty:
        return pd.DataFrame(), pd.DataFrame(), "No hay registros con responsable asignado"
    
    # Crear copia para no modificar el original
    df_costs = filtered_with_overtime.copy()
    
    # Convertir minutos de horas extras a horas
    df_costs['H_EXTRA_HORAS'] = df_costs['H_EXTRA_MIN'] / 60
    
    # Obtener semana del año y año
    df_costs['SEMANA'] = df_costs['FECHA_DE_INICIO'].dt.isocalendar().week
    df_costs['AÑO'] = df_costs['FECHA_DE_INICIO'].dt.year
    df_costs['SEMANA_STR'] = df_costs['AÑO'].astype(str) + '-S' + df_costs['SEMANA'].astype(str).str.zfill(2)
    
    # Preparar datos del personal
    if personal_data.empty:
        # Si no hay datos del personal, calcular solo horas sin costos
        df_costs['COSTO_TOTAL'] = 0
        df_costs['TECNICO'] = df_costs['RESPONSABLE']
        
        weekly_costs = df_costs.groupby(['SEMANA_STR', 'TECNICO']).agg({
            'COSTO_TOTAL': 'sum',
            'H_EXTRA_HORAS': 'sum'
        }).reset_index()
        
        accumulated_costs = df_costs.groupby('TECNICO').agg({
            'COSTO_TOTAL': 'sum',
            'H_EXTRA_HORAS': 'sum'
        }).reset_index().sort_values('H_EXTRA_HORAS', ascending=False)
        
        return weekly_costs, accumulated_costs, "Sin datos de personal - mostrando solo horas"
    
    # Limpiar nombres de columnas del personal
    personal_data.columns = [str(col).strip().upper() for col in personal_data.columns]
    
    # Buscar columnas específicas según las especificaciones
    nombre_col = None
    costo_50_col = None
    costo_100_col = None
    
    # Buscar columna de nombre del técnico (APELLIDO Y NOMBRE según especificaciones)
    for col in personal_data.columns:
        col_upper = col.upper()
        if 'APELLIDO' in col_upper and 'NOMBRE' in col_upper:
            nombre_col = col
            break
    
    # Si no se encuentra la columna exacta, buscar alternativas
    if nombre_col is None:
        for col in personal_data.columns:
            if 'NOMBRE' in col.upper() or 'TECNICO' in col.upper() or 'RESPONSABLE' in col.upper():
                nombre_col = col
                break
    
    if nombre_col is None:
        nombre_col = personal_data.columns[0]
    
    # Buscar columnas de costos específicas
    for col in personal_data.columns:
        col_upper = col.upper()
        # Buscar 'VALOR DE HORAS AL 50%' según especificaciones
        if 'VALOR' in col_upper and 'HORAS' in col_upper and '50' in col_upper:
            costo_50_col = col
        # Buscar 'VALOR DE HORAS AL 100%' según especificaciones
        elif 'VALOR' in col_upper and 'HORAS' in col_upper and '100' in col_upper:
            costo_100_col = col
    
    # Si no se encuentran con los nombres específicos, buscar por partes
    if costo_50_col is None:
        for col in personal_data.columns:
            if '50' in col or 'CINCUENTA' in col.upper():
                costo_50_col = col
                break
    
    if costo_100_col is None:
        for col in personal_data.columns:
            if '100' in col or 'CIEN' in col.upper():
                costo_100_col = col
                break
    
    # Crear diccionario de costos con nombres normalizados
    costos_tecnicos = {}
    tecnicos_personal = set()
    
    for _, row in personal_data.iterrows():
        nombre = str(row[nombre_col]).strip()
        if not nombre or pd.isna(nombre):
            continue
        
        # Normalizar nombre (quitar espacios extra, convertir a mayúsculas)
        nombre_normalizado = ' '.join(nombre.split()).upper()
        tecnicos_personal.add(nombre_normalizado)
        
        # Obtener costos
        costo_50 = 0
        costo_100 = 0
        
        if costo_50_col:
            try:
                valor = row[costo_50_col]
                if pd.notna(valor):
                    # Intentar convertir a número, manejar diferentes formatos
                    if isinstance(valor, str):
                        # Limpiar formato de moneda
                        valor = valor.replace('$', '').replace(',', '').replace(' ', '').strip()
                    costo_50 = float(valor)
            except (ValueError, TypeError):
                costo_50 = 0
        
        if costo_100_col:
            try:
                valor = row[costo_100_col]
                if pd.notna(valor):
                    # Intentar convertir a número, manejar diferentes formatos
                    if isinstance(valor, str):
                        # Limpiar formato de moneda
                        valor = valor.replace('$', '').replace(',', '').replace(' ', '').strip()
                    costo_100 = float(valor)
            except (ValueError, TypeError):
                costo_100 = 0
        
        costos_tecnicos[nombre_normalizado] = {
            '50%': costo_50,
            '100%': costo_100
        }
    
    # Calcular costos para cada registro
    costos_detallados = []
    tecnicos_no_encontrados = set()
    tecnicos_encontrados = set()
    registros_con_tipo_indeterminado = 0
    
    for idx, row in df_costs.iterrows():
        nombre_tecnico = str(row['RESPONSABLE']).strip()
        if not nombre_tecnico or pd.isna(nombre_tecnico):
            continue
            
        # Normalizar nombre del técnico (igual que en el personal)
        nombre_tecnico_normalizado = ' '.join(nombre_tecnico.split()).upper()
        
        # Determinar tipo de hora extra según especificaciones
        # Buscar en las columnas existentes que puedan indicar el tipo
        tipo_hora = '50%'  # Valor por defecto según especificaciones
        
        # 1. Buscar columna específica 'VALOR DE HORAS' que pueda contener '50%' o '100%'
        if 'VALOR DE HORAS' in row and pd.notna(row['VALOR DE HORAS']):
            valor_hora_str = str(row['VALOR DE HORAS']).upper()
            if '100%' in valor_hora_str or '100' in valor_hora_str or 'CIEN' in valor_hora_str:
                tipo_hora = '100%'
            elif '50%' in valor_hora_str or '50' in valor_hora_str or 'CINCUENTA' in valor_hora_str:
                tipo_hora = '50%'
        
        # 2. Buscar en otras columnas que puedan indicar el tipo
        elif 'TIPO HORA EXTRA' in row and pd.notna(row['TIPO HORA EXTRA']):
            tipo_str = str(row['TIPO HORA EXTRA']).upper()
            if '100' in tipo_str:
                tipo_hora = '100%'
            elif '50' in tipo_str:
                tipo_hora = '50%'
        
        # 3. Si no se encuentra información, asumir 50% (por defecto)
        else:
            registros_con_tipo_indeterminado += 1
        
        # Obtener costo por hora del técnico
        costo_por_hora = 0
        if nombre_tecnico_normalizado in costos_tecnicos:
            costo_por_hora = costos_tecnicos[nombre_tecnico_normalizado].get(tipo_hora, 0)
            tecnicos_encontrados.add(nombre_tecnico)
        else:
            tecnicos_no_encontrados.add(nombre_tecnico)
            # Intentar búsqueda parcial si no se encuentra exacto
            for tecnico_personal in tecnicos_personal:
                if nombre_tecnico_normalizado in tecnico_personal or tecnico_personal in nombre_tecnico_normalizado:
                    costo_por_hora = costos_tecnicos[tecnico_personal].get(tipo_hora, 0)
                    tecnicos_encontrados.add(nombre_tecnico)
                    break
        
        # Calcular costo total
        horas_extra = row['H_EXTRA_HORAS']
        costo_total = horas_extra * costo_por_hora
        
        costos_detallados.append({
            'SEMANA_STR': row['SEMANA_STR'],
            'TECNICO': nombre_tecnico,
            'TECNICO_NORMALIZADO': nombre_tecnico_normalizado,
            'TIPO_HORA': tipo_hora,
            'HORAS_EXTRA': horas_extra,
            'COSTO_POR_HORA': costo_por_hora,
            'COSTO_TOTAL': costo_total,
            'H_EXTRA_MIN': row['H_EXTRA_MIN']
        })
    
    if not costos_detallados:
        return pd.DataFrame(), pd.DataFrame(), "No se pudieron calcular costos (lista vacía)"
    
    # Crear DataFrame con costos detallados
    df_costos = pd.DataFrame(costos_detallados)
    
    # Datos semanales agrupados
    weekly_costs = df_costos.groupby(['SEMANA_STR', 'TECNICO']).agg({
        'COSTO_TOTAL': 'sum',
        'HORAS_EXTRA': 'sum',
        'H_EXTRA_MIN': 'sum'
    }).reset_index()
    
    # Datos acumulados por técnico
    accumulated_costs = df_costos.groupby('TECNICO').agg({
        'COSTO_TOTAL': 'sum',
        'HORAS_EXTRA': 'sum',
        'H_EXTRA_MIN': 'sum'
    }).reset_index().sort_values('COSTO_TOTAL', ascending=False)
    
    # Construir mensaje informativo
    mensaje_extra = f" | Técnicos encontrados: {len(tecnicos_encontrados)}"
    if tecnicos_no_encontrados:
        mensaje_extra += f" | Técnicos no encontrados: {len(tecnicos_no_encontrados)}"
    if registros_con_tipo_indeterminado > 0:
        mensaje_extra += f" | Registros con tipo indeterminado (asumido 50%): {registros_con_tipo_indeterminado}"
    
    # Información adicional sobre costos
    total_costo = accumulated_costs['COSTO_TOTAL'].sum()
    total_horas = accumulated_costs['HORAS_EXTRA'].sum()
    costo_promedio_hora = total_costo / total_horas if total_horas > 0 else 0
    
    mensaje_extra += f" | Costo total: ${total_costo:,.2f}"
    mensaje_extra += f" | Horas totales: {total_horas:,.2f}"
    mensaje_extra += f" | Costo promedio/hora: ${costo_promedio_hora:,.2f}"
    
    return weekly_costs, accumulated_costs, f"Cálculo exitoso{mensaje_extra}"

# Función para mostrar información detallada de costos
def show_detailed_costs_info(weekly_costs, accumulated_costs, personal_data):
    """Muestra información detallada sobre los costos calculados"""
    
    st.subheader("📋 Información Detallada de Costos")
    
    if accumulated_costs.empty:
        st.info("No hay datos de costos acumulados para mostrar.")
        return
    
    # Mostrar resumen general
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_costo = accumulated_costs['COSTO_TOTAL'].sum()
        st.metric("Costo Total Horas Extras", f"${total_costo:,.2f}")
    
    with col2:
        total_horas = accumulated_costs['HORAS_EXTRA'].sum()
        st.metric("Horas Extras Totales", f"{total_horas:,.1f} horas")
    
    with col3:
        costo_promedio = total_costo / total_horas if total_horas > 0 else 0
        st.metric("Costo Promedio por Hora", f"${costo_promedio:,.2f}")
    
    with col4:
        num_tecnicos = len(accumulated_costs)
        st.metric("Técnicos con Horas Extras", f"{num_tecnicos}")
    
    # Mostrar tabla detallada con formato
    st.subheader("📊 Detalle de Costos por Técnico")
    
    # Crear tabla formateada
    tabla_detalle = accumulated_costs.copy()
    tabla_detalle['COSTO_TOTAL_FMT'] = tabla_detalle['COSTO_TOTAL'].apply(lambda x: f"${x:,.2f}")
    tabla_detalle['HORAS_EXTRA_FMT'] = tabla_detalle['HORAS_EXTRA'].apply(lambda x: f"{x:,.2f}")
    tabla_detalle['COSTO_POR_HORA'] = tabla_detalle.apply(
        lambda x: x['COSTO_TOTAL'] / x['HORAS_EXTRA'] if x['HORAS_EXTRA'] > 0 else 0, 
        axis=1
    )
    tabla_detalle['COSTO_POR_HORA_FMT'] = tabla_detalle['COSTO_POR_HORA'].apply(lambda x: f"${x:,.2f}")
    tabla_detalle['PORCENTAJE'] = (tabla_detalle['COSTO_TOTAL'] / total_costo * 100) if total_costo > 0 else 0
    tabla_detalle['PORCENTAJE_FMT'] = tabla_detalle['PORCENTAJE'].apply(lambda x: f"{x:.1f}%")
    
    # Ordenar columnas para mostrar
    columnas_mostrar = ['TECNICO', 'HORAS_EXTRA_FMT', 'COSTO_POR_HORA_FMT', 'COSTO_TOTAL_FMT', 'PORCENTAJE_FMT']
    tabla_detalle = tabla_detalle[columnas_mostrar]
    tabla_detalle.columns = ['Técnico', 'Horas Extras', 'Costo por Hora', 'Costo Total', '% del Total']
    
    st.dataframe(tabla_detalle, use_container_width=True)
    
    # Mostrar datos semanales si existen
    if not weekly_costs.empty:
        with st.expander("Ver datos semanales detallados"):
            # Formatear datos semanales
            weekly_formatted = weekly_costs.copy()
            weekly_formatted['COSTO_TOTAL_FMT'] = weekly_formatted['COSTO_TOTAL'].apply(lambda x: f"${x:,.2f}")
            weekly_formatted['HORAS_EXTRA_FMT'] = weekly_formatted['HORAS_EXTRA'].apply(lambda x: f"{x:,.2f}")
            
            st.dataframe(
                weekly_formatted[['SEMANA_STR', 'TECNICO', 'HORAS_EXTRA_FMT', 'COSTO_TOTAL_FMT']],
                use_container_width=True
            )

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
    
    # REEMPLAZO DE COLUMNAS ORIGINALES POR COLUMNAS "NOMBRE" PARA CÁLCULOS
    # Mantener los nombres originales para visualización
    
    # 1. UBICACIÓN TÉCNICA
    if 'UBICACIÓN TÉCNICA NOMBRE' in df_clean.columns:
        # Reemplazar valores de UBICACIÓN TÉCNICA con UBICACIÓN TÉCNICA NOMBRE para cálculos
        df_clean['UBICACIÓN TÉCNICA'] = df_clean['UBICACIÓN TÉCNICA NOMBRE']
    
    # Manejar la columna de ubicación técnica si no existe
    elif 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'UBICACION TECNICA' in df_clean.columns:
        df_clean = df_clean.rename(columns={'UBICACION TECNICA': 'UBICACIÓN TÉCNICA'})
    elif 'UBICACIÓN TÉCNICA' not in df_clean.columns and 'Ubicación Técnica' in df_clean.columns:
        df_clean = df_clean.rename(columns={'Ubicación Técnica': 'UBICACIÓN TÉCNICA'})
    
    # 2. EQUIPO
    if 'EQUIPO NOMBRE' in df_clean.columns:
        # Reemplazar valores de EQUIPO con EQUIPO NOMBRE para cálculos
        df_clean['EQUIPO'] = df_clean['EQUIPO NOMBRE']
    
    # 3. CONJUNTO
    if 'CONJUNTO NOMBRE' in df_clean.columns:
        # Reemplazar valores de CONJUNTO con CONJUNTO NOMBRE para cálculos
        df_clean['CONJUNTO'] = df_clean['CONJUNTO NOMBRE']
    
    # 4. RESPONSABLE
    if 'RESPONSABLE NOMBRE' in df_clean.columns:
        # Reemplazar valores de RESPONSABLE con RESPONSABLE NOMBRE para cálculos
        df_clean['RESPONSABLE'] = df_clean['RESPONSABLE NOMBRE']
    
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
    m['total_fallas_emergency'] = len(df_emergency)
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

# Función para obtener datos semanales - MEJORADA para manejar correctamente cambio de año
def get_weekly_data(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
    
    # Crear SEMANA_STR con formato AÑO-SEMANA (ej: 2025-S52, 2026-S01)
    df_weekly['SEMANA_STR'] = df_weekly.apply(
        lambda x: f"{x['AÑO']}-S{x['SEMANA']:02d}", 
        axis=1
    )
    
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
    weekly_data['SEMANA_NUM'] = weekly_data['AÑO'] * 100 + weekly_data['SEMANA']
    weekly_data = weekly_data.sort_values('SEMANA_NUM')
    
    return weekly_data

# Función para obtener datos semanales por técnico (TR_MIN y H_EXTRA_MIN) - CON TÉCNICOS SEPARADOS - MEJORADA
def get_weekly_technician_hours(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns or 'RESPONSABLE' not in df.columns:
        return pd.DataFrame()
    
    # Primero separar los técnicos - AHORA CADA TÉCNICO RECIBE HORAS COMPLETAS
    df_separado = separar_tecnicos(df)
    
    # Crear copia para no modificar el original
    df_weekly = df_separado.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
    
    # Crear SEMANA_STR con formato AÑO-SEMANA (ej: 2025-S52, 2026-S01)
    df_weekly['SEMANA_STR'] = df_weekly.apply(
        lambda x: f"{x['AÑO']}-S{x['SEMANA']:02d}", 
        axis=1
    )
    
    # Agrupar por semana y técnico - TODOS LOS REGISTROS
    weekly_tech_data = df_weekly.groupby(['SEMANA_STR', 'AÑO', 'SEMANA', 'RESPONSABLE']).agg({
        'TR_MIN': 'sum',
        'H_EXTRA_MIN': 'sum'
    }).reset_index()
    
    # Convertir minutos a horas
    weekly_tech_data['TR_HORAS'] = weekly_tech_data['TR_MIN'] / 60
    weekly_tech_data['H_EXTRA_HORAS'] = weekly_tech_data['H_EXTRA_MIN'] / 60
    
    # Crear columna numérica para ordenar correctamente las semanas
    weekly_tech_data['SEMANA_NUM'] = weekly_tech_data['AÑO'] * 100 + weekly_tech_data['SEMANA']
    weekly_tech_data = weekly_tech_data.sort_values('SEMANA_NUM')
    
    return weekly_tech_data

# Función para obtener datos acumulados por técnico - CON TÉCNICOS SEPARADOS
def get_accumulated_technician_hours(df):
    if df.empty or 'RESPONSABLE' not in df.columns:
        return pd.DataFrame()
    
    # Primero separar los técnicos - AHORA CADA TÉCNICO RECIBE HORAS COMPLETAS
    df_separado = separar_tecnicos(df)
    
    # Agrupar por técnico
    tech_data = df_separado.groupby('RESPONSABLE').agg({
        'TR_MIN': 'sum',
        'H_EXTRA_MIN': 'sum'
    }).reset_index()
    
    # Convertir minutos a horas
    tech_data['TR_HORAS'] = tech_data['TR_MIN'] / 60
    tech_data['H_EXTRA_HORAS'] = tech_data['H_EXTRA_MIN'] / 60
    
    # Ordenar por horas normales (descendente)
    tech_data = tech_data.sort_values('TR_HORAS', ascending=False)
    
    return tech_data

# Función para obtener datos semanales de correctivos de emergencia (con MTTR) - MEJORADA
def get_weekly_emergency_data(df):
    if df.empty or 'FECHA_DE_INICIO' not in df.columns:
        return pd.DataFrame()
    
    # Crear copia para no modificar el original
    df_weekly = df.copy()
    
    # Obtener semana del año y año - USAR FECHA_DE_INICIO
    df_weekly['SEMANA'] = df_weekly['FECHA_DE_INICIO'].dt.isocalendar().week
    df_weekly['AÑO'] = df_weekly['FECHA_DE_INICIO'].dt.year
    
    # Crear SEMANA_STR con formato AÑO-SEMANA (ej: 2025-S52, 2026-S01)
    df_weekly['SEMANA_STR'] = df_weekly.apply(
        lambda x: f"{x['AÑO']}-S{x['SEMANA']:02d}", 
        axis=1
    )
    
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
    weekly_emergency_data['SEMANA_NUM'] = weekly_emergency_data['AÑO'] * 100 + weekly_emergency_data['SEMANA']
    weekly_emergency_data = weekly_emergency_data.sort_values('SEMANA_NUM')
    
    return weekly_emergency_data

# Función para obtener datos mensuales de cumplimiento del plan para 2026 - MEJORADA CON LA NUEVA CATEGORÍA
def get_monthly_plan_data(df, year=2026):
    """Obtiene datos mensuales para el cumplimiento del plan incluyendo:
    - Órdenes planificadas: Todas las órdenes de tipo PREVENTIVO, BASADO EN CONDICIÓN y MEJORA DE SISTEMA
    - Órdenes culminadas: con status 'CULMINADO'
    - Órdenes en ejecución: con status 'EN PROCESO'
    - Órdenes retrasadas: con status 'PENDIENTE' y fecha menor a la fecha actual
    - Órdenes proyectadas: con status 'PENDIENTE' y fecha mayor o igual a la fecha actual"""
    
    # Crear un DataFrame base con todos los meses de 2026
    meses_todos = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), (5, 'Mayo'), (6, 'Junio'),
        (7, 'Julio'), (8, 'Agosto'), (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
    ]
    
    monthly_data = pd.DataFrame(meses_todos, columns=['MES', 'MES_NOMBRE'])
    monthly_data['AÑO'] = year
    monthly_data['MES_ORDEN'] = monthly_data['MES']
    
    # Inicializar todas las columnas con 0 (incluyendo la nueva categoría)
    monthly_data['TOTAL_PLANIFICADAS'] = 0
    monthly_data['ORDENES_CULMINADAS'] = 0
    monthly_data['ORDENES_EN_EJECUCION'] = 0  # NUEVA CATEGORÍA
    monthly_data['ORDENES_RETRASADAS'] = 0
    monthly_data['ORDENES_PROYECTADAS'] = 0
    monthly_data['CUMPLIMIENTO_PCT'] = 0
    
    if df.empty or 'FECHA_DE_INICIO' not in df.columns or 'TIPO DE MTTO' not in df.columns:
        return monthly_data
    
    # Filtrar solo órdenes de tipo PREVENTIVO, BASADO EN CONDICIÓN y MEJORA DE SISTEMA
    tipos_planificados = ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'MEJORA DE SISTEMA']
    df_plan = df[df['TIPO DE MTTO'].isin(tipos_planificados)].copy()
    
    # Filtrar por año 2026
    df_plan = df_plan[df_plan['FECHA_DE_INICIO'].dt.year == year]
    
    if df_plan.empty:
        return monthly_data
    
    # Obtener mes y año
    df_plan['MES'] = df_plan['FECHA_DE_INICIO'].dt.month
    df_plan['MES_NOMBRE'] = df_plan['MES'].map(dict(meses_todos))
    df_plan['AÑO'] = df_plan['FECHA_DE_INICIO'].dt.year
    
    # Obtener fecha actual
    fecha_actual = datetime.now().date()
    df_plan['FECHA_INICIO_DATE'] = df_plan['FECHA_DE_INICIO'].dt.date
    
    # Verificar si existe columna STATUS y normalizarla
    if 'STATUS' not in df_plan.columns:
        # Si no existe columna STATUS, todas se consideran culminadas
        df_plan['STATUS_NORM'] = 'CULMINADO'
    else:
        # Normalizar el estado (convertir a mayúsculas, quitar espacios, manejar variantes)
        df_plan['STATUS_NORM'] = df_plan['STATUS'].astype(str).str.upper().str.strip()
        
        # Normalizar variantes comunes
        # Aceptar tanto 'CULMINADO' como 'CULMINADA'
        df_plan.loc[df_plan['STATUS_NORM'].str.contains('CULMINAD'), 'STATUS_NORM'] = 'CULMINADO'
        # Aceptar 'EN PROCESO', 'EN PROGRESO', 'PROCESO', etc.
        df_plan.loc[df_plan['STATUS_NORM'].str.contains('PROCESO') | 
                   df_plan['STATUS_NORM'].str.contains('PROGRESO') |
                   df_plan['STATUS_NORM'].str.contains('EJECUCI'), 'STATUS_NORM'] = 'EN PROCESO'
    
    # Clasificar órdenes según las nuevas definiciones
    # 1. Órdenes culminadas (con status 'CULMINADO')
    mask_culminadas = df_plan['STATUS_NORM'] == 'CULMINADO'
    
    # 2. Órdenes en ejecución (con status 'EN PROCESO') - NUEVA CATEGORÍA
    mask_en_ejecucion = df_plan['STATUS_NORM'] == 'EN PROCESO'
    
    # 3. Órdenes retrasadas (con status 'PENDIENTE' y menor a la fecha actual)
    mask_retrasadas = (df_plan['STATUS_NORM'] == 'PENDIENTE') & (df_plan['FECHA_INICIO_DATE'] < fecha_actual)
    
    # 4. Órdenes proyectadas (con status 'PENDIENTE' y mayor o igual a la fecha actual)
    mask_proyectadas = (df_plan['STATUS_NORM'] == 'PENDIENTE') & (df_plan['FECHA_INICIO_DATE'] >= fecha_actual)
    
    # Agrupar por mes para cada categoría
    # Total planificadas (todas las órdenes)
    monthly_real_data = df_plan.groupby(['AÑO', 'MES', 'MES_NOMBRE']).agg({
        'TIPO DE MTTO': 'count'
    }).reset_index()
    monthly_real_data = monthly_real_data.rename(columns={'TIPO DE MTTO': 'TOTAL_PLANIFICADAS'})
    
    # Órdenes culminadas
    df_culminadas = df_plan[mask_culminadas]
    monthly_culminadas = df_culminadas.groupby(['AÑO', 'MES', 'MES_NOMBRE']).agg({
        'TIPO DE MTTO': 'count'
    }).reset_index()
    monthly_culminadas = monthly_culminadas.rename(columns={'TIPO DE MTTO': 'ORDENES_CULMINADAS'})
    
    # Órdenes en ejecución - NUEVA CATEGORÍA
    df_en_ejecucion = df_plan[mask_en_ejecucion]
    monthly_en_ejecucion = df_en_ejecucion.groupby(['AÑO', 'MES', 'MES_NOMBRE']).agg({
        'TIPO DE MTTO': 'count'
    }).reset_index()
    monthly_en_ejecucion = monthly_en_ejecucion.rename(columns={'TIPO DE MTTO': 'ORDENES_EN_EJECUCION'})
    
    # Órdenes retrasadas
    df_retrasadas = df_plan[mask_retrasadas]
    monthly_retrasadas = df_retrasadas.groupby(['AÑO', 'MES', 'MES_NOMBRE']).agg({
        'TIPO DE MTTO': 'count'
    }).reset_index()
    monthly_retrasadas = monthly_retrasadas.rename(columns={'TIPO DE MTTO': 'ORDENES_RETRASADAS'})
    
    # Órdenes proyectadas
    df_proyectadas = df_plan[mask_proyectadas]
    monthly_proyectadas = df_proyectadas.groupby(['AÑO', 'MES', 'MES_NOMBRE']).agg({
        'TIPO DE MTTO': 'count'
    }).reset_index()
    monthly_proyectadas = monthly_proyectadas.rename(columns={'TIPO DE MTTO': 'ORDENES_PROYECTADAS'})
    
    # Combinar datos reales con la estructura base
    for _, row in monthly_real_data.iterrows():
        mes = row['MES']
        mask = monthly_data['MES'] == mes
        monthly_data.loc[mask, 'TOTAL_PLANIFICADAS'] = row['TOTAL_PLANIFICADAS']
    
    for _, row in monthly_culminadas.iterrows():
        mes = row['MES']
        mask = monthly_data['MES'] == mes
        monthly_data.loc[mask, 'ORDENES_CULMINADAS'] = row['ORDENES_CULMINADAS']
    
    # Combinar datos de en ejecución - NUEVA CATEGORÍA
    if not monthly_en_ejecucion.empty:
        for _, row in monthly_en_ejecucion.iterrows():
            mes = row['MES']
            mask = monthly_data['MES'] == mes
            monthly_data.loc[mask, 'ORDENES_EN_EJECUCION'] = row['ORDENES_EN_EJECUCION']
    
    # Combinar datos de retrasadas
    if not monthly_retrasadas.empty:
        for _, row in monthly_retrasadas.iterrows():
            mes = row['MES']
            mask = monthly_data['MES'] == mes
            monthly_data.loc[mask, 'ORDENES_RETRASADAS'] = row['ORDENES_RETRASADAS']
    
    # Combinar datos de proyectadas
    if not monthly_proyectadas.empty:
        for _, row in monthly_proyectadas.iterrows():
            mes = row['MES']
            mask = monthly_data['MES'] == mes
            monthly_data.loc[mask, 'ORDENES_PROYECTADAS'] = row['ORDENES_PROYECTADAS']
    
    # Calcular porcentaje de cumplimiento (culminadas / total planificadas)
    monthly_data['CUMPLIMIENTO_PCT'] = monthly_data.apply(
        lambda row: (row['ORDENES_CULMINADAS'] / row['TOTAL_PLANIFICADAS']) * 100 
        if row['TOTAL_PLANIFICADAS'] > 0 else 0,
        axis=1
    )
    
    # Ordenar por mes
    monthly_data = monthly_data.sort_values('MES_ORDEN')
    
    return monthly_data

# Función para aplicar filtros - ACTUALIZADA CON FILTRO DE TIPO DE MTTO
def apply_filters(df, equipo_filter, conjunto_filter, ubicacion_filter, tipo_mtto_filter, fecha_inicio, fecha_fin):
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
    
    if tipo_mtto_filter != "Todos":
        # Convertir a string para comparación
        filtered_df = filtered_df[filtered_df['TIPO DE MTTO'].astype(str) == tipo_mtto_filter]
    
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
    
    if 'personal_data' not in st.session_state:
        st.session_state.personal_data = pd.DataFrame()
    
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
    
    # Cargar datos del personal si no están cargados
    if st.session_state.personal_data.empty:
        with st.spinner("Cargando datos del personal..."):
            personal_df = load_personal_data_from_google_sheets()
            if not personal_df.empty:
                st.session_state.personal_data = personal_df
                st.success("✅ Datos del personal cargados correctamente")
            else:
                st.warning("⚠️ No se pudieron cargar los datos del personal. La pestaña de costos puede no funcionar correctamente.")
    
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
        
        # 3. FILTRO DE EQUIPOS - CORREGIDO (ahora usando valores de EQUIPO NOMBRE)
        equipos_unique = st.session_state.data['EQUIPO'].unique().tolist()
        equipos_str = [str(x) for x in equipos_unique]
        equipos = ["Todos"] + sorted(equipos_str)
        equipo_filter = st.sidebar.selectbox("Equipo", equipos)
        
        # 4. FILTRO DE CONJUNTOS - CORREGIDO (ahora usando valores de CONJUNTO NOMBRE)
        conjuntos_unique = st.session_state.data['CONJUNTO'].unique().tolist()
        conjuntos_str = [str(x) for x in conjuntos_unique]
        conjuntos = ["Todos"] + sorted(conjuntos_str)
        conjunto_filter = st.sidebar.selectbox("Conjunto", conjuntos)
        
        # 5. FILTRO DE TIPO DE MTTO (NUEVO) - Colocado debajo de Conjunto como solicitado
        if 'TIPO DE MTTO' in st.session_state.data.columns:
            tipos_mtto_unique = st.session_state.data['TIPO DE MTTO'].dropna().unique().tolist()
            tipos_mtto_str = [str(x) for x in tipos_mtto_unique]
            tipos_mtto = ["Todos"] + sorted(tipos_mtto_str)
        else:
            tipos_mtto = ["Todos"]
        
        tipo_mtto_filter = st.sidebar.selectbox("Tipo de Mtto", tipos_mtto, key="tipo_mtto_filter")
        
        # Aplicar filtros (incluyendo el nuevo filtro de tipo de mtto)
        filtered_data = apply_filters(st.session_state.data, equipo_filter, conjunto_filter, 
                                      ubicacion_filter, tipo_mtto_filter, fecha_inicio, fecha_fin)
        
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
        
        # Pestañas - MODIFICADO: agregar nueva pestaña de Cumplimiento del Plan
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
            "Planta", "TFS", "TR", "TFC", "Tipo de Mtto", "Confiabilidad", 
            "Horas Personal Técnico", "Costos Horas Extras Personal Técnico", "Cumplimiento del Plan"
        ])
        
        # Calcular métricas
        metrics = calculate_metrics(filtered_data)
        weekly_data = get_weekly_data(filtered_data)
        
        # Calcular métricas de confiabilidad específicas para correctivos de emergencia
        reliability_metrics = calculate_reliability_metrics(filtered_data)
        
        # Obtener datos semanales de correctivos de emergencia
        weekly_emergency_data = get_weekly_emergency_data(filtered_data)
        
        # Obtener datos semanales por técnico (CON TÉCNICOS SEPARADOS)
        weekly_tech_data = get_weekly_technician_hours(filtered_data)
        
        # Obtener datos acumulados por técnico (CON TÉCNICOS SEPARADOS)
        accumulated_tech_data = get_accumulated_technician_hours(filtered_data)
        
        # Calcular costos de horas extras (YA INCLUYE SEPARACIÓN DE TÉCNICOS)
        weekly_costs, accumulated_costs, mensaje_calculo = calculate_overtime_costs(filtered_data, st.session_state.personal_data)
        
        # Obtener datos de cumplimiento del plan para 2026 CON LAS MEJORAS
        monthly_plan_data = get_monthly_plan_data(st.session_state.data, year=2026)
        
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
        
        # Pestaña TFS - COMPLETA CON UBICACIÓN TÉCNICA
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
                
                # TFS por Ubicación Técnica (NUEVO)
                if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                    tfs_por_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA')['TFS_MIN'].sum().reset_index()
                    tfs_por_ubicacion = tfs_por_ubicacion.sort_values('TFS_MIN', ascending=False).head(10)
                    
                    if not tfs_por_ubicacion.empty:
                        fig = px.bar(tfs_por_ubicacion, x='UBICACIÓN TÉCNICA', y='TFS_MIN',
                                    title='TFS por Ubicación Técnica',
                                    labels={'UBICACIÓN TÉCNICA': 'Ubicación Técnica', 'TFS_MIN': 'TFS (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][1])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TFS por ubicación técnica")
                
                # Tablas de resumen - AHORA CON 3 COLUMNAS
                st.subheader("Resúmenes TFS")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("**Resumen TFS por Equipo**")
                    resumen_equipo = filtered_afecta.groupby('EQUIPO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_equipo, use_container_width=True)
                
                with col2:
                    st.write("**Resumen TFS por Conjunto**")
                    resumen_conjunto = filtered_afecta.groupby('CONJUNTO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_conjunto.head(10), use_container_width=True)
                
                with col3:
                    st.write("**Resumen TFS por Ubicación Técnica**")
                    if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                        resumen_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA').agg({
                            'TFS_MIN': 'sum',
                            'TR_MIN': 'sum',
                            'TFC_MIN': 'sum'
                        }).reset_index()
                        st.dataframe(resumen_ubicacion.head(10), use_container_width=True)
                    else:
                        st.info("No hay datos de ubicación técnica")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TR - COMPLETA CON UBICACIÓN TÉCNICA
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
                
                # TR por Ubicación Técnica (NUEVO)
                if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                    tr_por_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA')['TR_MIN'].sum().reset_index()
                    tr_por_ubicacion = tr_por_ubicacion.sort_values('TR_MIN', ascending=False).head(10)
                    
                    if not tr_por_ubicacion.empty:
                        fig = px.bar(tr_por_ubicacion, x='UBICACIÓN TÉCNICA', y='TR_MIN',
                                    title='TR por Ubicación Técnica',
                                    labels={'UBICACIÓN TÉCNICA': 'Ubicación Técnica', 'TR_MIN': 'TR (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][2])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TR por ubicación técnica")
                
                # Tablas de resumen - AHORA CON 3 COLUMNAS
                st.subheader("Resúmenes TR")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("**Resumen TR por Equipo**")
                    resumen_equipo = filtered_afecta.groupby('EQUIPO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_equipo, use_container_width=True)
                
                with col2:
                    st.write("**Resumen TR por Conjunto**")
                    resumen_conjunto = filtered_afecta.groupby('CONJUNTO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_conjunto.head(10), use_container_width=True)
                
                with col3:
                    st.write("**Resumen TR por Ubicación Técnica**")
                    if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                        resumen_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA').agg({
                            'TFS_MIN': 'sum',
                            'TR_MIN': 'sum',
                            'TFC_MIN': 'sum'
                        }).reset_index()
                        st.dataframe(resumen_ubicacion.head(10), use_container_width=True)
                    else:
                        st.info("No hay datos de ubicación técnica")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña TFC - COMPLETA CON UBICACIÓN TÉCNICA
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
                
                # TFC por Ubicación Técnica (NUEVO)
                if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                    tfc_por_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA')['TFC_MIN'].sum().reset_index()
                    tfc_por_ubicacion = tfc_por_ubicacion.sort_values('TFC_MIN', ascending=False).head(10)
                    
                    if not tfc_por_ubicacion.empty:
                        fig = px.bar(tfc_por_ubicacion, x='UBICACIÓN TÉCNICA', y='TFC_MIN',
                                    title='TFC por Ubicación Técnica',
                                    labels={'UBICACIÓN TÉCNICA': 'Ubicación Técnica', 'TFC_MIN': 'TFC (min)'})
                        fig.update_traces(marker_color=COLOR_PALETTE['pastel'][3])
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay datos de TFC por ubicación técnica")
                
                # Tablas de resumen - AHORA CON 3 COLUMNAS
                st.subheader("Resúmenes TFC")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("**Resumen TFC por Equipo**")
                    resumen_equipo = filtered_afecta.groupby('EQUIPO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_equipo, use_container_width=True)
                
                with col2:
                    st.write("**Resumen TFC por Conjunto**")
                    resumen_conjunto = filtered_afecta.groupby('CONJUNTO').agg({
                        'TFS_MIN': 'sum',
                        'TR_MIN': 'sum',
                        'TFC_MIN': 'sum'
                    }).reset_index()
                    st.dataframe(resumen_conjunto.head(10), use_container_width=True)
                
                with col3:
                    st.write("**Resumen TFC por Ubicación Técnica**")
                    if 'UBICACIÓN TÉCNICA' in filtered_afecta.columns:
                        resumen_ubicacion = filtered_afecta.groupby('UBICACIÓN TÉCNICA').agg({
                            'TFS_MIN': 'sum',
                            'TR_MIN': 'sum',
                            'TFC_MIN': 'sum'
                        }).reset_index()
                        st.dataframe(resumen_ubicacion.head(10), use_container_width=True)
                    else:
                        st.info("No hay datos de ubicación técnica")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados")
        
        # Pestaña Tipo de Mantenimiento - CORREGIDA CON VALIDACIONES ROBUSTAS
        with tab5:
            st.header("Análisis por Tipo de Mantenimiento")
            
            # Verificación inicial de datos
            if not filtered_data.empty:
                # Mostrar métricas
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
                    # Verificar columnas necesarias
                    if 'FECHA_DE_INICIO' in filtered_data.columns and 'TIPO DE MTTO' in filtered_data.columns and 'TR_MIN' in filtered_data.columns:
                        df_weekly_mtto = filtered_data.copy()
                        df_weekly_mtto['SEMANA'] = df_weekly_mtto['FECHA_DE_INICIO'].dt.isocalendar().week
                        df_weekly_mtto['AÑO'] = df_weekly_mtto['FECHA_DE_INICIO'].dt.year
                        df_weekly_mtto['SEMANA_STR'] = df_weekly_mtto.apply(
                            lambda x: f"{x['AÑO']}-S{x['SEMANA']:02d}", 
                            axis=1
                        )
                        
                        # Agrupar por semana y tipo de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO
                        try:
                            tipo_mtto_semana = df_weekly_mtto.groupby(['SEMANA_STR', 'TIPO DE MTTO'])['TR_MIN'].sum().reset_index()
                            
                            if not tipo_mtto_semana.empty:
                                # Ordenar por semana
                                tipo_mtto_semana = tipo_mtto_semana.sort_values('SEMANA_STR')
                                
                                # Obtener todos los tipos de mantenimiento únicos
                                tipos_mtto_unicos = tipo_mtto_semana['TIPO DE MTTO'].unique()
                                
                                # Ordenar los tipos de mantenimiento
                                tipos_ordenados = []
                                for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PROGRAMADO', 'CORRECTIVO DE EMERGENCIA', 'MEJORA DE SISTEMA']:
                                    if tipo in tipos_mtto_unicos:
                                        tipos_ordenados.append(tipo)
                                
                                # Agregar cualquier otro tipo que no esté en la lista ordenada
                                for tipo in tipos_mtto_unicos:
                                    if tipo not in tipos_ordenados:
                                        tipos_ordenados.append(tipo)
                                
                                # Crear gráfico de barras apiladas con colores específicos
                                try:
                                    fig = px.bar(tipo_mtto_semana, x='SEMANA_STR', y='TR_MIN', color='TIPO DE MTTO',
                                                title='Tipo de Mantenimiento por Semana (Barras Apiladas) - Todos los Tipos',
                                                labels={'SEMANA_STR': 'Semana', 'TR_MIN': 'Tiempo (min)', 'TIPO DE MTTO': 'Tipo de Mantenimiento'},
                                                color_discrete_map=COLOR_PALETTE['tipo_mtto'],
                                                category_orders={'TIPO DE MTTO': tipos_ordenados})
                                    
                                    # Ajustar la leyenda del gráfico de barras
                                    fig.update_layout(
                                        legend=dict(
                                            title='Tipo de Mantenimiento',
                                            orientation='v',
                                            yanchor='top',
                                            y=1,
                                            xanchor='right',
                                            x=1.05,
                                            bgcolor='rgba(255, 255, 255, 0.8)',
                                            bordercolor='lightgray',
                                            borderwidth=1
                                        )
                                    )
                                    
                                    st.plotly_chart(fig, use_container_width=True)
                                except Exception as e:
                                    st.error(f"Error al crear gráfico de barras: {str(e)[:100]}")
                                    st.info("Mostrando versión simplificada del gráfico")
                                    fig = px.bar(tipo_mtto_semana, x='SEMANA_STR', y='TR_MIN', color='TIPO DE MTTO',
                                                title='Tipo de Mantenimiento por Semana')
                                    st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("No hay datos de tipo de mantenimiento por semana")
                        except Exception as e:
                            st.error(f"Error al agrupar datos: {str(e)[:100]}")
                    else:
                        st.warning("Faltan columnas necesarias para el gráfico de barras (FECHA_DE_INICIO, TIPO DE MTTO, TR_MIN)")

                with col2:
                    # Distribución de mantenimiento - TODOS LOS TIPOS DE MANTENIMIENTO
                    # Verificar columnas necesarias antes de proceder
                    if 'TIPO DE MTTO' in filtered_data.columns and 'TR_MIN' in filtered_data.columns:
                        try:
                            # Crear DataFrame agrupado
                            tipo_mtto_totals = filtered_data.groupby('TIPO DE MTTO')['TR_MIN'].sum().reset_index()
                            
                            # Verificar que el DataFrame no esté vacío
                            if not tipo_mtto_totals.empty and len(tipo_mtto_totals) > 0:
                                # Verificar que las columnas existan
                                if 'TIPO DE MTTO' in tipo_mtto_totals.columns and 'TR_MIN' in tipo_mtto_totals.columns:
                                    # Obtener los tipos únicos del DataFrame agrupado
                                    tipos_mtto_unicos = tipo_mtto_totals['TIPO DE MTTO'].unique()
                                    
                                    # Ordenar los tipos de mantenimiento
                                    tipos_ordenados = []
                                    for tipo in ['PREVENTIVO', 'BASADO EN CONDICIÓN', 'CORRECTIVO PROGRAMADO', 'CORRECTIVO DE EMERGENCIA', 'MEJORA DE SISTEMA']:
                                        if tipo in tipos_mtto_unicos:
                                            tipos_ordenados.append(tipo)
                                    
                                    # Agregar cualquier otro tipo que no esté en la lista ordenada
                                    for tipo in tipos_mtto_unicos:
                                        if tipo not in tipos_ordenados:
                                            tipos_ordenados.append(tipo)
                                    
                                    # Crear un mapa de colores extendido que use los mismos colores que el gráfico de barras
                                    # Usar la misma paleta base que el gráfico de barras
                                    color_map_comun = COLOR_PALETTE['tipo_mtto'].copy()
                                    
                                    # Si hay tipos de mantenimiento que no están en la paleta base, asignarles colores consistentes
                                    colores_adicionales = ['#FFA500', '#800080', '#008000', '#FF69B4', '#00CED1']
                                    
                                    for i, tipo in enumerate(tipos_ordenados):
                                        if tipo not in color_map_comun:
                                            # Asignar un color de la lista de colores adicionales
                                            color_map_comun[tipo] = colores_adicionales[i % len(colores_adicionales)]
                                    
                                    # MEJORA: Crear gráfico de torta con los mismos colores que el gráfico de barras
                                    try:
                                        # Primero, ordenar el DataFrame según el orden definido
                                        tipo_mtto_totals['TIPO_ORDEN'] = tipo_mtto_totals['TIPO DE MTTO'].apply(
                                            lambda x: tipos_ordenados.index(x) if x in tipos_ordenados else len(tipos_ordenados)
                                        )
                                        tipo_mtto_totals = tipo_mtto_totals.sort_values('TIPO_ORDEN')
                                        
                                        # Calcular porcentajes para mostrar en el tooltip
                                        total_tiempo = tipo_mtto_totals['TR_MIN'].sum()
                                        tipo_mtto_totals['PORCENTAJE'] = (tipo_mtto_totals['TR_MIN'] / total_tiempo * 100).round(1)
                                        
                                        # Crear el gráfico de torta con los mismos colores
                                        fig = px.pie(tipo_mtto_totals, 
                                                    values='TR_MIN', 
                                                    names='TIPO DE MTTO',
                                                    title='Distribución de Mantenimiento - Todos los Tipos',
                                                    color='TIPO DE MTTO',  # Especificar la columna para colorear
                                                    color_discrete_map=color_map_comun,  # Usar el mismo mapa de colores
                                                    category_orders={'TIPO DE MTTO': tipos_ordenados})
                                        
                                        # MEJORA: Ajustar la leyenda para que sea igual al gráfico de barras
                                        # Primero, determinar si mostrar porcentajes dentro de la torta o no
                                        # Si hay muchos tipos, es mejor mostrar solo en el tooltip
                                        
                                        # Configurar el texto dentro de la torta
                                        if len(tipo_mtto_totals) <= 6:
                                            # Pocos tipos: mostrar porcentaje y etiqueta dentro
                                            textinfo_value = 'percent+label'
                                            textposition_value = 'inside'
                                                                                                                            
                                        # Ajustar el layout para mejor legibilidad y leyenda consistente
                                        fig.update_layout(
                                            # MEJORA: Leyenda igual al gráfico de barras
                                            legend=dict(
                                                title='Tipo de Mantenimiento',  # Mismo título que el gráfico de barras
                                                orientation='v',
                                                yanchor='top',
                                                y=1,  # Misma altura que el gráfico de barras
                                                xanchor='right',
                                                x=1.05,  # Misma posición horizontal
                                                bgcolor='rgba(255, 255, 255, 0.8)',
                                                bordercolor='lightgray',
                                                borderwidth=1,
                                                font=dict(size=12),
                                                itemwidth=30
                                            ),
                                            # Ajustes para el texto dentro de la torta
                                            uniformtext_minsize=10,
                                            uniformtext_mode='hide',
                                            showlegend=True,
                                          
                                        )
                                        
                                        # MEJORA: Ajustar tamaño de fuente del porcentaje si se muestra dentro
                                        if len(tipo_mtto_totals) <= 6:
                                            fig.update_traces(textfont=dict(size=11, color='white'))
                                        
                                        st.plotly_chart(fig, use_container_width=True)
                                        
                                    except Exception as e:
                                        st.warning(f"Error al crear gráfico de pie personalizado: {str(e)[:100]}")
                                        # Intentar versión simplificada
                                        try:
                                            fig = px.pie(tipo_mtto_totals, 
                                                        values='TR_MIN', 
                                                        names='TIPO DE MTTO',
                                                        title='Distribución de Mantenimiento - Todos los Tipos',
                                                        color='TIPO DE MTTO',
                                                        color_discrete_map=color_map_comun)
                                            
                                            # Añadir leyenda consistente en versión simplificada
                                            fig.update_layout(
                                                legend=dict(
                                                    title='Tipo de Mantenimiento',
                                                    orientation='v',
                                                    yanchor='top',
                                                    y=1,
                                                    xanchor='right',
                                                    x=1.05
                                                )
                                            )
                                            
                                            st.plotly_chart(fig, use_container_width=True)
                                        except Exception as e2:
                                            st.error(f"Error crítico al crear gráfico: {str(e2)[:100]}")
                                            st.info("Datos disponibles:")
                                            st.write(f"Columnas: {tipo_mtto_totals.columns.tolist()}")
                                            st.write(f"Filas: {len(tipo_mtto_totals)}")
                                else:
                                    st.warning("El DataFrame agrupado no tiene las columnas esperadas")
                                    st.info(f"Columnas disponibles: {tipo_mtto_totals.columns.tolist()}")
                            else:
                                st.info("No hay datos de distribución de mantenimiento después del agrupamiento")
                        except Exception as e:
                            st.error(f"Error al procesar datos para gráfico de pie: {str(e)[:100]}")
                    else:
                        st.warning("Faltan columnas necesarias para el gráfico de pie (TIPO DE MTTO, TR_MIN)")
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
        
        # Pestaña Horas Personal Técnico - MODIFICADA PARA MANEJAR MÚLTIPLES TÉCNICOS
        with tab7:
            st.header("👷 Análisis de Horas del Personal Técnico")
            
            if not filtered_data.empty:
                # Verificar si existe la columna RESPONSABLE
                if 'RESPONSABLE' not in filtered_data.columns:
                    st.warning("⚠️ La columna 'RESPONSABLE' no está presente en los datos.")
                    st.info("Para ver el análisis de horas por técnico, asegúrate de que tu dataset incluya la columna 'RESPONSABLE'.")
                else:
                    # Crear DataFrame con técnicos separados - AHORA CADA TÉCNICO RECIBE HORAS COMPLETAS
                    data_with_responsible_separado = separar_tecnicos(filtered_data)
                    
                    if data_with_responsible_separado.empty:
                        st.info("No hay datos con responsable asignado para mostrar.")
                    else:
                        # Obtener datos semanales por técnico (ya separados en la función)
                        if not weekly_tech_data.empty:
                            # Crear paleta de colores para técnicos
                            tecnicos_unicos = weekly_tech_data['RESPONSABLE'].unique()
                            colores_tecnicos = {}
                            
                            # Paleta de colores para técnicos (usando colores pastel)
                            colores_disponibles = COLOR_PALETTE['pastel'] + ['#FFA07A', '#20B2AA', '#778899', '#B0C4DE', '#FFB6C1', '#98FB98', '#DDA0DD', '#FFE4B5']
                            
                            for i, tecnico in enumerate(tecnicos_unicos):
                                colores_tecnicos[tecnico] = colores_disponibles[i % len(colores_disponibles)]
                            
                            # --- SECCIÓN 1: HORAS NORMALES (TR_MIN) ---
                            st.subheader("📊 Horas Normales por Técnico")
                            
                            # Gráfico 1: Barras apiladas semanales de horas normales
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Ordenar semanas
                                semanas_ordenadas = sorted(weekly_tech_data['SEMANA_STR'].unique())
                                
                                fig = px.bar(weekly_tech_data, 
                                            x='SEMANA_STR', 
                                            y='TR_HORAS',
                                            color='RESPONSABLE',
                                            title='Horas Normales por Semana (por Técnico)',
                                            labels={'SEMANA_STR': 'Semana', 'TR_HORAS': 'Horas Normales', 'RESPONSABLE': 'Técnico'},
                                            color_discrete_map=colores_tecnicos,
                                            category_orders={'SEMANA_STR': semanas_ordenadas})
                                fig.update_layout(barmode='stack')
                                st.plotly_chart(fig, use_container_width=True)
                            
                            with col2:
                                # Gráfico de torta: Horas normales acumuladas por técnico
                                horas_normales_acumuladas = data_with_responsible_separado.groupby('RESPONSABLE')['TR_MIN'].sum().reset_index()
                                horas_normales_acumuladas['TR_HORAS'] = horas_normales_acumuladas['TR_MIN'] / 60
                                horas_normales_acumuladas = horas_normales_acumuladas.sort_values('TR_HORAS', ascending=False)
                                
                                if not horas_normales_acumuladas.empty:
                                    # Formatear etiquetas para mostrar técnico y horas
                                    horas_normales_acumuladas['LABEL'] = horas_normales_acumuladas.apply(
                                        lambda x: f"{x['RESPONSABLE']}: {x['TR_HORAS']:.1f} horas", axis=1
                                    )
                                    
                                    fig = px.pie(horas_normales_acumuladas, 
                                                values='TR_HORAS', 
                                                names='LABEL',
                                                title='Distribución de Horas Normales Acumuladas',
                                                color='RESPONSABLE',
                                                color_discrete_map=colores_tecnicos)
                                    
                                    # Actualizar el hovertemplate para mostrar información adicional
                                    fig.update_traces(
                                        textposition='inside', 
                                        textinfo='percent+label',
                                        hovertemplate='<b>%{label}</b><br>' +
                                                    'Horas: %{value:.1f}<br>' +
                                                    'Porcentaje: %{percent}<extra></extra>'
                                    )
                                    st.plotly_chart(fig, use_container_width=True)
                                else:
                                    st.info("No hay datos de horas normales acumuladas para mostrar.")
                            
                            # --- SECCIÓN 2: HORAS EXTRAS (H_EXTRA_MIN) ---
                            st.subheader("⏰ Horas Extras por Técnico")
                            
                            # Filtrar datos con responsable y que tengan horas extras
                            weekly_tech_extras = weekly_tech_data[weekly_tech_data['H_EXTRA_HORAS'] > 0]
                            
                            if not weekly_tech_extras.empty:
                                # Usar la misma paleta de colores que en la sección anterior
                                # Gráfico 3: Barras apiladas semanales de horas extras
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    # Ordenar semanas
                                    semanas_ordenadas = sorted(weekly_tech_extras['SEMANA_STR'].unique())
                                    
                                    fig = px.bar(weekly_tech_extras, 
                                                x='SEMANA_STR', 
                                                y='H_EXTRA_HORAS',
                                                color='RESPONSABLE',
                                                title='Horas Extras por Semana (por Técnico)',
                                                labels={'SEMANA_STR': 'Semana', 'H_EXTRA_HORAS': 'Horas Extras', 'RESPONSABLE': 'Técnico'},
                                                color_discrete_map=colores_tecnicos,
                                                category_orders={'SEMANA_STR': semanas_ordenadas})
                                    fig.update_layout(barmode='stack')
                                    st.plotly_chart(fig, use_container_width=True)
                                
                                with col2:
                                    # Gráfico de torta: Horas extras acumuladas por técnico
                                    horas_extras_acumuladas = data_with_responsible_separado.groupby('RESPONSABLE')['H_EXTRA_MIN'].sum().reset_index()
                                    horas_extras_acumuladas['H_EXTRA_HORAS'] = horas_extras_acumuladas['H_EXTRA_MIN'] / 60
                                    horas_extras_acumuladas = horas_extras_acumuladas[horas_extras_acumuladas['H_EXTRA_HORAS'] > 0]
                                    horas_extras_acumuladas = horas_extras_acumuladas.sort_values('H_EXTRA_HORAS', ascending=False)
                                    
                                    if not horas_extras_acumuladas.empty:
                                        # Formatear etiquetas para mostrar técnico y horas
                                        horas_extras_acumuladas['LABEL'] = horas_extras_acumuladas.apply(
                                            lambda x: f"{x['RESPONSABLE']}: {x['H_EXTRA_HORAS']:.1f} horas", axis=1
                                        )
                                        
                                        fig = px.pie(horas_extras_acumuladas, 
                                                    values='H_EXTRA_HORAS', 
                                                    names='LABEL',
                                                    title='Distribución de Horas Extras Acumuladas',
                                                    color='RESPONSABLE',
                                                    color_discrete_map=colores_tecnicos)
                                        
                                        # Actualizar el hovertemplate para mostrar información adicional
                                        fig.update_traces(
                                            textposition='inside', 
                                            textinfo='percent+label',
                                            hovertemplate='<b>%{label}</b><br>' +
                                                        'Horas Extras: %{value:.1f}<br>' +
                                                        'Porcentaje: %{percent}<extra></extra>'
                                        )
                                        st.plotly_chart(fig, use_container_width=True)
                                    else:
                                        st.info("No hay datos de horas extras acumuladas para mostrar.")
                            else:
                                st.info("No hay datos de horas extras por técnico para mostrar.")
                            
                            # --- EXPLICACIÓN DE LA MODIFICACIÓN ---
                            with st.expander("ℹ️ Información sobre el cálculo de horas"):
                                st.markdown("""
                                ### 📊 **Modificación en el cálculo de horas por técnico**
                                
                                **Antes:** Si una orden tenía 2 técnicos y 60 minutos de trabajo, cada técnico recibía 30 minutos.
                                
                                **Ahora:** Si una orden tiene 2 técnicos y 60 minutos de trabajo, **cada técnico recibe 60 minutos**.
                                
                                ### **Ejemplo:**
                                - Orden con 2 técnicos (Juan y Pedro)
                                - Duración: 60 minutos normales + 60 minutos extras
                                - **Resultado:**
                                  - Juan: 60 minutos normales + 60 minutos extras
                                  - Pedro: 60 minutos normales + 60 minutos extras
                                
                                ### **Justificación:**
                                Esta modificación refleja la realidad de que cada técnico trabaja el tiempo completo de la orden,
                                independientemente de cuántos técnicos participen en el trabajo.
                                """)
                        else:
                            st.info("No hay datos semanales por técnico para mostrar.")
            else:
                st.info("No hay datos para mostrar con los filtros seleccionados.")
        
        # Pestaña Costos Horas Extras Personal Técnico - NUEVA PESTAÑA (YA INCLUYE SEPARACIÓN DE TÉCNICOS)
        with tab8:
            st.header("💰 Costos de Horas Extras del Personal Técnico")
            
            if not filtered_data.empty:
                # Calcular costos (con la función mejorada)
                weekly_costs, accumulated_costs, mensaje_calculo = calculate_overtime_costs(filtered_data, st.session_state.personal_data)
                
                # Mostrar mensaje de estado
                st.info(f"Estado del cálculo: {mensaje_calculo}")
                
                if weekly_costs.empty or accumulated_costs.empty:
                    # Mostrar información de depuración
                    with st.expander("🔍 Depuración - Ver detalles de los datos", expanded=True):
                        st.subheader("Registros con horas extras encontrados")
                        
                        # Filtrar registros con horas extras
                        registros_con_extras = filtered_data[filtered_data['H_EXTRA_MIN'] > 0]
                        
                        if not registros_con_extras.empty:
                            st.write(f"**Total de registros con horas extras:** {len(registros_con_extras)}")
                            
                            # Mostrar columnas relevantes
                            columnas = ['FECHA_DE_INICIO', 'RESPONSABLE', 'H_EXTRA_MIN']
                            if 'VALOR DE HORAS' in registros_con_extras.columns:
                                columnas.append('VALOR DE HORAS')
                            
                            st.dataframe(
                                registros_con_extras[columnas].head(20),
                                use_container_width=True,
                                column_config={
                                    "H_EXTRA_MIN": st.column_config.NumberColumn(
                                        "Minutos Extra",
                                        help="Minutos de horas extras",
                                        format="%d min"
                                    )
                                }
                            )
                            
                            # Mostrar cómo se separarían los técnicos
                            st.subheader("Separación de técnicos (ejemplo)")
                            ejemplo_separado = separar_tecnicos(registros_con_extras.head(5))
                            if not ejemplo_separado.empty and len(ejemplo_separado) > 0:
                                st.write("**Ejemplo de cómo se distribuirían las horas entre múltiples técnicos:**")
                                st.markdown("""
                                **NOTA:** Con la nueva modificación, cada técnico recibe las horas COMPLETAS de la orden.
                                
                                Ejemplo:
                                - Orden original: 120 minutos extras, 2 técnicos (Juan y Pedro)
                                - Resultado después de separar:
                                  - Juan: 120 minutos extras
                                  - Pedro: 120 minutos extras
                                """)
                                st.dataframe(ejemplo_separado[['FECHA_DE_INICIO', 'RESPONSABLE', 'H_EXTRA_MIN']], 
                                           use_container_width=True)
                            
                            # Mostrar resumen por técnico
                            st.subheader("Resumen por técnico")
                            registros_separados = separar_tecnicos(registros_con_extras)
                            resumen_tecnicos = registros_separados.groupby('RESPONSABLE').agg({
                                'H_EXTRA_MIN': ['sum', 'count']
                            }).reset_index()
                            resumen_tecnicos.columns = ['Técnico', 'Total Minutos', 'N° Registros']
                            resumen_tecnicos['Total Horas'] = resumen_tecnicos['Total Minutos'] / 60
                            st.dataframe(resumen_tecnicos, use_container_width=True)
                        else:
                            st.warning("No se encontraron registros con H_EXTRA_MIN > 0")
                        
                        # Mostrar datos del personal
                        if not st.session_state.personal_data.empty:
                            st.subheader("Datos del personal cargados")
                            st.write(f"**Registros en PERSONAL:** {len(st.session_state.personal_data)}")
                            st.dataframe(st.session_state.personal_data.head(20), use_container_width=True)
                            
                            # Mostrar nombres de técnicos en PERSONAL
                            st.subheader("Técnicos en hoja PERSONAL")
                            # Buscar columna de nombres
                            nombre_col = None
                            for col in st.session_state.personal_data.columns:
                                col_str = str(col).upper()
                                if any(keyword in col_str for keyword in ['NOMBRE', 'TECNICO', 'RESPONSABLE']):
                                    nombre_col = col
                                    break
                            
                            if nombre_col:
                                tecnicos_personal = st.session_state.personal_data[nombre_col].dropna().unique()
                                st.write(f"**Columna de nombres:** {nombre_col}")
                                st.write(f"**Técnicos encontrados:** {len(tecnicos_personal)}")
                                for i, tecnico in enumerate(tecnicos_personal[:15]):
                                    st.write(f"{i+1}. {tecnico}")
                                if len(tecnicos_personal) > 15:
                                    st.write(f"... y {len(tecnicos_personal) - 15} más")
                            else:
                                st.write("No se pudo identificar la columna de nombres")
                            
                            # Mostrar columnas de costos
                            st.subheader("Columnas de costos encontradas")
                            columnas_costos = []
                            for col in st.session_state.personal_data.columns:
                                if 'VALOR' in col.upper() and 'HORAS' in col.upper():
                                    columnas_costos.append(col)
                            
                            if columnas_costos:
                                st.write(f"**Columnas de costos:** {', '.join(columnas_costos)}")
                            else:
                                st.warning("No se encontraron columnas de costos (buscar 'VALOR' y 'HORAS' en el nombre)")
                        else:
                            st.warning("No se cargaron datos de la hoja PERSONAL")
                    
                    st.markdown("""
                    ### 🔧 Posibles soluciones:
                    
                    1. **Verificar nombres de técnicos:** 
                       - Los nombres en 'RESPONSABLE' deben coincidir con los de la hoja PERSONAL
                       - Revisa mayúsculas, tildes y espacios
                    
                    2. **Verificar estructura de la hoja PERSONAL:**
                       - Debe contener columnas con los costos por hora
                       - Busca columnas llamadas 'VALOR DE HORAS AL 50%' y 'VALOR DE HORAS AL 100%'
                    
                    3. **Verificar formato de horas extras:**
                       - La columna 'h extra (min)' debe contener números mayores a 0
                    
                    4. **Verificar filtros aplicados:**
                       - Asegúrate de que los filtros no estén excluyendo los registros con horas extras
                    """)
                    
                else:
                    # Mostrar información detallada de costos
                    show_detailed_costs_info(weekly_costs, accumulated_costs, st.session_state.personal_data)
                    
                    # Obtener lista única de técnicos para crear paleta de colores
                    tecnicos_unicos = list(weekly_costs['TECNICO'].unique())
                    colores_tecnicos = {}
                    
                    # Paleta de colores para técnicos
                    colores_disponibles = COLOR_PALETTE['pastel'] + ['#FFA07A', '#20B2AA', '#778899', '#B0C4DE', '#FFB6C1', '#98FB98', '#DDA0DD', '#FFE4B5']
                    
                    for i, tecnico in enumerate(tecnicos_unicos):
                        colores_tecnicos[tecnico] = colores_disponibles[i % len(colores_disponibles)]
                    
                    # --- GRÁFICO 1: Barras apiladas de costos por semana ---
                    st.subheader("📈 Evolución de Costos por Semana")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Ordenar semanas
                        semanas_ordenadas = sorted(weekly_costs['SEMANA_STR'].unique())
                        
                        fig = px.bar(weekly_costs, 
                                    x='SEMANA_STR', 
                                    y='COSTO_TOTAL',
                                    color='TECNICO',
                                    title='Costos de Horas Extras por Semana (USD)',
                                    labels={'SEMANA_STR': 'Semana', 'COSTO_TOTAL': 'Costo Total (USD)', 'TECNICO': 'Técnico'},
                                    color_discrete_map=colores_tecnicos,
                                    category_orders={'SEMANA_STR': semanas_ordenadas})
                        fig.update_layout(barmode='stack')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # --- GRÁFICO 2: Evolución de horas extras por semana ---
                        fig = px.bar(weekly_costs, 
                                    x='SEMANA_STR', 
                                    y='HORAS_EXTRA',
                                    color='TECNICO',
                                    title='Horas Extras por Semana',
                                    labels={'SEMANA_STR': 'Semana', 'HORAS_EXTRA': 'Horas Extras', 'TECNICO': 'Técnico'},
                                    color_discrete_map=colores_tecnicos,
                                    category_orders={'SEMANA_STR': semanas_ordenadas})
                        fig.update_layout(barmode='stack')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # --- GRÁFICO 3: Análisis de distribución ---
                    st.subheader("📊 Análisis de Distribución")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Gráfico de torta de costos acumulados
                        pie_data = accumulated_costs.copy()
                        pie_data['PORCENTAJE'] = (pie_data['COSTO_TOTAL'] / pie_data['COSTO_TOTAL'].sum()) * 100
                        
                        # Formatear etiquetas para mostrar técnico, costo y porcentaje
                        pie_data['LABEL'] = pie_data.apply(
                            lambda x: f"{x['TECNICO']}: ${x['COSTO_TOTAL']:,.2f} ({x['PORCENTAJE']:.1f}%)", 
                            axis=1
                        )
                        
                        fig = px.pie(pie_data, 
                                    values='COSTO_TOTAL', 
                                    names='LABEL',
                                    title='Distribución de Costos de Horas Extras',
                                    color='TECNICO',
                                    color_discrete_map=colores_tecnicos)
                        
                        fig.update_traces(
                            textposition='inside', 
                            textinfo='percent+label',
                            hovertemplate='<b>%{label}</b><br>' +
                                        'Costo Total: $%{value:,.2f}<br>' +
                                        'Porcentaje: %{percent}<br>' +
                                        'Horas Extras: %{customdata[0]:,.1f}<extra></extra>',
                            customdata=pie_data[['HORAS_EXTRA']].values
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # Gráfico de barras horizontales para costos acumulados
                        fig = px.bar(accumulated_costs.sort_values('COSTO_TOTAL', ascending=True),
                                    y='TECNICO',
                                    x='COSTO_TOTAL',
                                    title='Costos Acumulados por Técnico',
                                    labels={'TECNICO': 'Técnico', 'COSTO_TOTAL': 'Costo Total (USD)'},
                                    color='TECNICO',
                                    color_discrete_map=colores_tecnicos,
                                    orientation='h')
                        
                        # Añadir anotaciones con los valores
                        fig.update_traces(texttemplate='$%{x:,.2f}', textposition='outside')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # --- EXPLICACIÓN DEL CÁLCULO ---
                    with st.expander("ℹ️ Información sobre el cálculo de costos"):
                        st.markdown("""
                        ### 📊 **Cálculo de Costos de Horas Extras**
                        
                        #### **Proceso de cálculo:**
                        1. **Detección de horas extras:** Solo se consideran registros con `H_EXTRA_MIN > 0`
                        2. **Conversión a horas:** Minutos ÷ 60
                        3. **Asignación por técnico:** Cada técnico recibe las horas **COMPLETAS** de la orden
                        4. **Obtención de costos:** Se obtienen de la hoja 'PERSONAL'
                        5. **Tipos de hora extra:**
                           - **50%:** Cantidad de horas extras × 'VALOR DE HORAS AL 50%'
                           - **100%:** Cantidad de horas extras × 'VALOR DE HORAS AL 100%'
                        
                        #### **Ejemplo según especificaciones:**
                        - **Técnico:** PEREZ BAJAÑA JUAN JOSE
                        - **Horas extras trabajadas:** 2 horas (50%)
                        - **Costo por hora extra:** $3,44 (de la hoja 'PERSONAL')
                        - **Costo total:** 2 horas × $3,44 = **$6,88**
                        
                        #### **Modificación en asignación de horas:**
                        **Antes:** Si una orden tenía 2 técnicos y 120 minutos extras, cada uno recibía 60 minutos.  
                        **Ahora:** Si una orden tiene 2 técnicos y 120 minutos extras, **cada técnico recibe 120 minutos** (horas completas).
                        
                        #### **Estructura esperada en hoja 'PERSONAL':**
                        1. Columna con nombres de técnicos (ej: 'APELLIDO Y NOMBRE')
                        2. Columna con costo de horas al 50% (ej: 'VALOR DE HORAS AL 50%')
                        3. Columna con costo de horas al 100% (ej: 'VALOR DE HORAS AL 100%')
                        """)
                        
            elif filtered_data.empty:
                st.info("No hay datos filtrados para mostrar.")
            else:
                st.warning("No se pudieron cargar los datos del personal. La pestaña de costos no está disponible.")
                st.info("""
                Para habilitar la pestaña de costos, asegúrate de:
                1. Tener acceso a la hoja 'PERSONAL' en el Google Sheet
                2. Que la hoja 'PERSONAL' contenga las columnas necesarias
                3. Que los datos del personal estén correctamente formateados
                """)
        
        # Pestaña Cumplimiento del Plan - MEJORADA CON LA NUEVA CATEGORÍA "EN EJECUCIÓN"
        with tab9:
            st.header("📋 Cumplimiento del Plan de Mantenimiento 2026")
            
            # 1. Texto explicativo desplegable (colapsado por defecto)
            with st.expander("ℹ️ **Información sobre el cálculo del cumplimiento**", expanded=False):
                st.markdown("""
                ### 📊 **Cálculo del Cumplimiento del Plan**
                
                #### **Órdenes consideradas:**
                - **PREVENTIVO**
                - **BASADO EN CONDICIÓN**
                - **MEJORA DE SISTEMA**
                
                #### **Período analizado:**
                - Año 2026 completo (todos los meses)
                
                #### **Definiciones (MEJORADAS):**
                ```
                1. ÓRDENES PLANIFICADAS:
                   - Todas las órdenes de los tipos especificados programadas para el mes
                
                2. ÓRDENES CULMINADAS:
                   - Tienen el estado 'CULMINADO' (también acepta 'CULMINADA')
                
                3. ÓRDENES EN EJECUCIÓN (NUEVA):
                   - Tienen el estado 'EN PROCESO' (también acepta 'PROCESO', 'EN PROGRESO', 'EJECUCIÓN')
                
                4. ÓRDENES RETRASADAS:
                   - Tienen estado 'PENDIENTE'
                   - Tienen fecha de inicio ANTERIOR a la fecha actual
                
                5. ÓRDENES PROYECTADAS:
                   - Tienen estado 'PENDIENTE'
                   - Tienen fecha de inicio MAYOR O IGUAL a la fecha actual
                ```
                
                #### **Fórmulas de cálculo:**
                ```
                TOTAL_PLANIFICADAS = Total de órdenes programadas para el mes
                
                CULMINADAS = Órdenes con STATUS = 'CULMINADO'
                
                EN EJECUCIÓN = Órdenes con STATUS = 'EN PROCESO' (nueva categoría)
                
                RETRASADAS = Órdenes PENDIENTES con fecha < hoy
                
                PROYECTADAS = Órdenes PENDIENTES con fecha >= hoy
                
                Cumplimiento % = (CULMINADAS / TOTAL_PLANIFICADAS) × 100%
                
                Verificación: TOTAL_PLANIFICADAS = CULMINADAS + EN EJECUCIÓN + RETRASADAS + PROYECTADAS
                ```
                
                #### **Interpretación de colores en gráficos (MEJORADA):**
                - 🟢 **Verde:** Órdenes culminadas (completadas)
                - 🟡 **Amarillo:** Órdenes en ejecución (en proceso)
                - 🟠 **Naranja:** Órdenes retrasadas (pendientes con fecha pasada)
                - 🔵 **Azul:** Órdenes proyectadas (pendientes con fecha futura)
                - ⚫ **Gris:** Total planificado (línea de referencia)
                
                #### **Objetivos de desempeño:**
                - **Cumplimiento mínimo aceptable:** 80%
                - **Cumplimiento objetivo:** 90%
                """)
            
            # Obtener datos de cumplimiento del plan para 2026
            monthly_plan_data = get_monthly_plan_data(st.session_state.data, year=2026)
            
            if not monthly_plan_data.empty:
                # Calcular indicadores generales del plan (ahora con 5 categorías)
                total_planificadas = monthly_plan_data['TOTAL_PLANIFICADAS'].sum()
                total_culminadas = monthly_plan_data['ORDENES_CULMINADAS'].sum()
                total_en_ejecucion = monthly_plan_data['ORDENES_EN_EJECUCION'].sum()  # NUEVA CATEGORÍA
                total_retrasadas = monthly_plan_data['ORDENES_RETRASADAS'].sum()
                total_proyectadas = monthly_plan_data['ORDENES_PROYECTADAS'].sum()
                
                # Verificar que la suma de categorías sea igual al total planificado
                suma_categorias = total_culminadas + total_en_ejecucion + total_retrasadas + total_proyectadas
                
                # Calcular porcentaje de cumplimiento
                cumplimiento_general = (total_culminadas / total_planificadas * 100) if total_planificadas > 0 else 0
                
                # 2. Evaluar estado del Plan basado en el cumplimiento
                if cumplimiento_general >= 90:
                    estado_plan = "🟢 Excelente"
                    estado_color = "green"
                    estado_desc = "El plan se está cumpliendo de manera excelente (>90%)"
                elif cumplimiento_general >= 80:
                    estado_plan = "🟡 Bueno"
                    estado_color = "orange"
                    estado_desc = "El plan se está cumpliendo adecuadamente (80-90%)"
                elif cumplimiento_general >= 70:
                    estado_plan = "🟠 Regular"
                    estado_color = "#FF8C00"  # naranja oscuro
                    estado_desc = "El plan necesita atención (70-80%)"
                else:
                    estado_plan = "🔴 Crítico"
                    estado_color = "red"
                    estado_desc = "El plan requiere intervención inmediata (<70%)"
                
                # Mostrar indicadores generales (7 columnas con las nuevas definiciones)
                st.subheader("📊 Indicadores Generales del Plan 2026")
                col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
                
                with col1:
                    st.metric("Total Planificadas", f"{total_planificadas}", 
                            help="Órdenes de tipo PREVENTIVO, BASADO EN CONDICIÓN y MEJORA DE SISTEMA para 2026")
                
                with col2:
                    st.metric("Órdenes Culminadas", f"{total_culminadas}",
                            help="Órdenes con estado 'CULMINADO' del plan para 2026")
                
                with col3:
                    st.metric("Órdenes en Ejecución", f"{total_en_ejecucion}",  # NUEVO
                            help="Órdenes con estado 'EN PROCESO' del plan para 2026")
                
                with col4:
                    st.metric("Órdenes Retrasadas", f"{total_retrasadas}",
                            help="Órdenes PENDIENTES con fecha < hoy")
                
                with col5:
                    st.metric("Órdenes Proyectadas", f"{total_proyectadas}",
                            help="Órdenes PENDIENTES con fecha >= hoy")
                
                with col6:
                    st.metric("Cumplimiento", f"{cumplimiento_general:.1f}%",
                            delta=None, delta_color="normal")
                
                with col7:
                    # Estado del Plan
                    st.markdown(f"**Estado del Plan**")
                    st.markdown(f"<h3 style='color:{estado_color};'>{estado_plan}</h3>", unsafe_allow_html=True)
                    st.caption(estado_desc)
                
                # Información de verificación
                if abs(suma_categorias - total_planificadas) > 0.1:  # Tolerancia pequeña para decimales
                    st.warning(f"⚠️ **Nota:** La suma de categorías ({suma_categorias}) no coincide exactamente con el total planificado ({total_planificadas}). Esto puede deberse a órdenes con estados diferentes a los definidos.")
                
                # Gráfico 1: Distribución mensual (MEJORADO con la nueva categoría)
                st.subheader("📊 Distribución de Órdenes por Mes (MEJORADO)")
                
                # Crear gráfico de barras apiladas con las 5 categorías
                fig1 = go.Figure()
                
                # Barras apiladas con las nuevas definiciones (orden de apilamiento: de abajo hacia arriba)
                # 1. Órdenes proyectadas (base)
                fig1.add_trace(go.Bar(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['ORDENES_PROYECTADAS'],
                    name='Proyectadas',
                    marker_color=COLOR_PALETTE['estado_orden']['PROYECTADAS'],  # Azul
                    text=monthly_plan_data['ORDENES_PROYECTADAS'],
                    textposition='inside',
                    textfont=dict(size=15, color='black'),
                    hovertemplate='<b>%{x}</b><br>Proyectadas: %{y}<extra></extra>'
                ))
                
                # 2. Órdenes retrasadas
                fig1.add_trace(go.Bar(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['ORDENES_RETRASADAS'],
                    name='Retrasadas',
                    marker_color=COLOR_PALETTE['estado_orden']['RETRASADAS'],  # Naranja
                    text=monthly_plan_data['ORDENES_RETRASADAS'],
                    textposition='inside',
                    textfont=dict(size=15, color='black'),
                    hovertemplate='<b>%{x}</b><br>Retrasadas: %{y}<extra></extra>'
                ))
                
                # 3. Órdenes en ejecución (NUEVA CATEGORÍA)
                fig1.add_trace(go.Bar(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['ORDENES_EN_EJECUCION'],
                    name='En Ejecución',
                    marker_color=COLOR_PALETTE['estado_orden']['EN EJECUCIÓN'],  # Amarillo
                    text=monthly_plan_data['ORDENES_EN_EJECUCION'],
                    textposition='inside',
                    textfont=dict(size=15, color='black'),
                    hovertemplate='<b>%{x}</b><br>En Ejecución: %{y}<extra></extra>'
                ))
                
                # 4. Órdenes culminadas (arriba del todo)
                fig1.add_trace(go.Bar(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['ORDENES_CULMINADAS'],
                    name='Culminadas',
                    marker_color=COLOR_PALETTE['estado_orden']['CULMINADAS'],  # Verde
                    text=monthly_plan_data['ORDENES_CULMINADAS'],
                    textposition='inside',
                    textfont=dict(size=15, color='black'),
                    hovertemplate='<b>%{x}</b><br>Culminadas: %{y}<extra></extra>'
                ))
                
                # Añadir línea para el total planificado
                fig1.add_trace(go.Scatter(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['TOTAL_PLANIFICADAS'],
                    name='Total Planificado',
                    mode='lines+markers',
                    line=dict(color=COLOR_PALETTE['estado_orden']['TOTAL_PLANIFICADAS'], width=3, dash='dash'),
                    marker=dict(size=8, color=COLOR_PALETTE['estado_orden']['TOTAL_PLANIFICADAS']),
                    hovertemplate='<b>%{x}</b><br>Total Planificado: %{y}<extra></extra>'
                ))
                
                # Añadir anotaciones de porcentaje de cumplimiento
                for i, row in monthly_plan_data.iterrows():
                    if row['TOTAL_PLANIFICADAS'] > 0:
                        cumplimiento_mensual = row['CUMPLIMIENTO_PCT']
                        
                        # Determinar color del texto según cumplimiento
                        if cumplimiento_mensual >= 90:
                            color_texto = 'green'
                        elif cumplimiento_mensual >= 80:
                            color_texto = 'orange'
                        elif cumplimiento_mensual >= 70:
                            color_texto = '#FF8C00'
                        else:
                            color_texto = 'red'
                        
                        # Anotación para cumplimiento
                        fig1.add_annotation(
                            x=row['MES_NOMBRE'],
                            y=row['TOTAL_PLANIFICADAS'] + (row['TOTAL_PLANIFICADAS'] * 0.05),
                            text=f"{cumplimiento_mensual:.0f}%",
                            showarrow=False,
                            font=dict(size=20, color=color_texto, weight='bold'),
                            yshift=5
                        )
                
                fig1.update_layout(
                    title='Distribución de Órdenes por Mes (Culminadas + En Ejecución + Retrasadas + Proyectadas)',
                    xaxis_title='Mes',
                    yaxis_title='Número de Órdenes',
                    barmode='stack',
                    hovermode='x unified',
                    height=500,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
                st.plotly_chart(fig1, use_container_width=True)
                
                # Gráfico 2: Cumplimiento por mes (gráfico de líneas)
                st.subheader("📈 Cumplimiento por Mes")
                
                fig2 = go.Figure()
                
                fig2.add_trace(go.Scatter(
                    x=monthly_plan_data['MES_NOMBRE'],
                    y=monthly_plan_data['CUMPLIMIENTO_PCT'],
                    mode='lines+markers+text',
                    name='% Cumplimiento',
                    line=dict(color='#32CD32', width=3),
                    marker=dict(size=10, color='#32CD32'),
                    text=[f"{val:.0f}%" for val in monthly_plan_data['CUMPLIMIENTO_PCT']],
                    textposition='top center',
                    textfont=dict(size=12, color='black'),
                    hovertemplate='<b>%{x}</b><br>Cumplimiento: %{y:.1f}%<extra></extra>'
                ))
                
                # Añadir línea de referencia al 80%
                fig2.add_hline(y=80, line_dash="dash", line_color="orange", 
                              annotation_text="Objetivo 80%", 
                              annotation_position="bottom right")
                
                # Añadir línea de referencia al 90%
                fig2.add_hline(y=90, line_dash="dash", line_color="green", 
                              annotation_text="Excelente 90%", 
                              annotation_position="top right")
                
                fig2.update_layout(
                    title='Porcentaje de Cumplimiento por Mes',
                    xaxis_title='Mes',
                    yaxis_title='Cumplimiento (%)',
                    yaxis_range=[0, 105],
                    height=400,
                    showlegend=True
                )
                
                st.plotly_chart(fig2, use_container_width=True)
                
                # Tabla detallada - TODOS LOS MESES (MEJORADA con la nueva categoría)
                st.subheader("📋 Detalle por Mes (Todos los meses de 2026)")
                
                # Crear tabla formateada con colores según cumplimiento
                tabla_detalle = monthly_plan_data.copy()
                tabla_detalle = tabla_detalle[['MES_NOMBRE', 'TOTAL_PLANIFICADAS', 'ORDENES_CULMINADAS', 
                                               'ORDENES_EN_EJECUCION', 'ORDENES_RETRASADAS', 
                                               'ORDENES_PROYECTADAS', 'CUMPLIMIENTO_PCT']]
                
                # Función para aplicar color según cumplimiento
                def color_cumplimiento(val):
                    if isinstance(val, (int, float)):
                        if val >= 90:
                            return 'background-color: #90EE90; color: black'  # verde claro
                        elif val >= 80:
                            return 'background-color: #FFD700; color: black'  # amarillo
                        elif val >= 70:
                            return 'background-color: #FFA500; color: black'  # naranja
                        else:
                            return 'background-color: #FFB6C1; color: black'  # rojo claro
                    return ''
                
                # Crear DataFrame para mostrar
                tabla_mostrar = tabla_detalle.copy()
                tabla_mostrar['CUMPLIMIENTO_PCT'] = tabla_mostrar.apply(
                    lambda x: f"{x['CUMPLIMIENTO_PCT']:.1f}%" if x['TOTAL_PLANIFICADAS'] > 0 else "Sin datos",
                    axis=1
                )
                
                tabla_mostrar.columns = ['Mes', 'Planificadas', 'Culminadas', 'En Ejecución', 'Retrasadas', 'Proyectadas', 'Cumplimiento %']
                
                # Aplicar estilos a la tabla
                st.dataframe(
                    tabla_mostrar.style.applymap(
                        lambda x: color_cumplimiento(float(x.replace('%', '')) if '%' in str(x) else x), 
                        subset=['Cumplimiento %']
                    ),
                    use_container_width=True
                )
                
                # Gráfico 3: Proporción General del Plan 2026 (MEJORADO con la nueva categoría)
                st.subheader("🥧 Proporción General del Plan 2026 (MEJORADO)")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Gráfico de torta para estado general (MEJORADO con 4 categorías)
                    estado_labels = ['Culminadas', 'En Ejecución', 'Retrasadas', 'Proyectadas']
                    estado_values = [total_culminadas, total_en_ejecucion, total_retrasadas, total_proyectadas]
                    estado_colores = [
                        COLOR_PALETTE['estado_orden']['CULMINADAS'],
                        COLOR_PALETTE['estado_orden']['EN EJECUCIÓN'],
                        COLOR_PALETTE['estado_orden']['RETRASADAS'],
                        COLOR_PALETTE['estado_orden']['PROYECTADAS']
                    ]
                    
                    fig3 = go.Figure(data=[go.Pie(
                        labels=estado_labels,
                        values=estado_values,
                        hole=0.4,
                        marker_colors=estado_colores,
                        textinfo='label+percent+value',
                        hovertemplate='<b>%{label}</b><br>' +
                                    'Cantidad: %{value}<br>' +
                                    'Porcentaje: %{percent}<extra></extra>'
                    )])
                    
                    fig3.update_layout(
                        title='Distribución General del Plan (MEJORADO)',
                        height=400
                    )
                    
                    st.plotly_chart(fig3, use_container_width=True)
                
                with col2:
                    # Gráfico de barras para top meses con mejor cumplimiento
                    # Filtrar meses con órdenes planificadas
                    meses_con_datos = monthly_plan_data[monthly_plan_data['TOTAL_PLANIFICADAS'] > 0].copy()
                    
                    if not meses_con_datos.empty:
                        # Calcular porcentaje de órdenes en ejecución por mes
                        meses_con_datos['%_EN_EJECUCION'] = (meses_con_datos['ORDENES_EN_EJECUCION'] / meses_con_datos['TOTAL_PLANIFICADAS']) * 100
                        
                        # Ordenar por porcentaje de cumplimiento (descendente)
                        top_cumplimiento = meses_con_datos.nlargest(5, 'CUMPLIMIENTO_PCT')[['MES_NOMBRE', 'CUMPLIMIENTO_PCT', '%_EN_EJECUCION']]
                        
                        # Crear gráfico de barras agrupadas
                        fig4 = go.Figure()
                        
                        # Barra de cumplimiento
                        fig4.add_trace(go.Bar(
                            x=top_cumplimiento['MES_NOMBRE'],
                            y=top_cumplimiento['CUMPLIMIENTO_PCT'],
                            name='Cumplimiento %',
                            marker_color='#32CD32',
                            text=top_cumplimiento['CUMPLIMIENTO_PCT'].apply(lambda x: f"{x:.1f}%"),
                            textposition='outside',
                            hovertemplate='<b>%{x}</b><br>Cumplimiento: %{y:.1f}%<extra></extra>'
                        ))
                        
                        # Barra de % en ejecución
                        fig4.add_trace(go.Bar(
                            x=top_cumplimiento['MES_NOMBRE'],
                            y=top_cumplimiento['%_EN_EJECUCION'],
                            name='% En Ejecución',
                            marker_color='#FFD700',
                            text=top_cumplimiento['%_EN_EJECUCION'].apply(lambda x: f"{x:.1f}%"),
                            textposition='outside',
                            hovertemplate='<b>%{x}</b><br>% En Ejecución: %{y:.1f}%<extra></extra>'
                        ))
                        
                        fig4.update_layout(
                            title='Top 5 Meses: Cumplimiento vs % En Ejecución',
                            xaxis_title='Mes',
                            yaxis_title='Porcentaje (%)',
                            barmode='group',
                            height=400
                        )
                        
                        st.plotly_chart(fig4, use_container_width=True)
                    else:
                        st.info("No hay meses con datos de planificación")
                
                # Mostrar información sobre meses sin datos
                meses_sin_planificadas = monthly_plan_data[monthly_plan_data['TOTAL_PLANIFICADAS'] == 0]['MES_NOMBRE'].tolist()
                if meses_sin_planificadas:
                    st.info(f"**Nota:** Los siguientes meses aún no tienen órdenes planificadas creadas: {', '.join(meses_sin_planificadas)}")
                
                # Información estadística adicional
                with st.expander("📊 **Estadísticas Adicionales**"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        # Porcentaje de órdenes en ejecución
                        pct_en_ejecucion = (total_en_ejecucion / total_planificadas * 100) if total_planificadas > 0 else 0
                        st.metric("Órdenes en Ejecución", f"{pct_en_ejecucion:.1f}%")
                    
                    with col2:
                        # Eficiencia (culminadas + en ejecución)
                        eficiencia = ((total_culminadas + total_en_ejecucion) / total_planificadas * 100) if total_planificadas > 0 else 0
                        st.metric("Eficiencia Total", f"{eficiencia:.1f}%")
                    
                    with col3:
                        # Tasa de retraso
                        tasa_retraso = (total_retrasadas / total_planificadas * 100) if total_planificadas > 0 else 0
                        st.metric("Tasa de Retraso", f"{tasa_retraso:.1f}%")
                    
                    # Análisis de tendencia
                    st.write("**Análisis de tendencia:**")
                    if total_en_ejecucion > 0:
                        st.info(f"Actualmente hay {total_en_ejecucion} órdenes en ejecución. Estas órdenes están siendo trabajadas actualmente y se espera que se conviertan en culminadas pronto.")
                    
                    if total_retrasadas > 0:
                        st.warning(f"⚠️ Hay {total_retrasadas} órdenes retrasadas. Se recomienda revisar estas órdenes para identificar causas de retraso.")
                    
                    # Recomendaciones basadas en los datos
                    if cumplimiento_general < 80:
                        st.error("**Recomendación:** El cumplimiento está por debajo del objetivo del 80%. Se recomienda revisar las órdenes retrasadas y en ejecución para mejorar el desempeño.")
                    elif pct_en_ejecucion > 20:
                        st.warning("**Recomendación:** Un alto porcentaje de órdenes están en ejecución. Asegúrese de que los recursos estén bien distribuidos para culminarlas a tiempo.")
                
                # Explicación de las mejoras
                with st.expander("📝 **Resumen de las mejoras implementadas**"):
                    st.markdown("""
                    ### **🎯 Mejoras implementadas en esta versión:**
                    
                    #### **1. NUEVA CATEGORÍA: "Órdenes en Ejecución"**
                    - **Definición:** Órdenes con estado 'EN PROCESO' (acepta variantes como 'PROCESO', 'EN PROGRESO', 'EJECUCIÓN')
                    - **Color:** Amarillo (#FFD700) para distinguirlas claramente
                    - **Ubicación en gráficos:** Entre culminadas (verde) y retrasadas (naranja)
                    
                    #### **2. Gráficos actualizados:**
                    - **Distribución de Órdenes por Mes:** Ahora muestra 4 categorías apiladas + línea de total
                    - **Proporción General del Plan:** Gráfico de torta con 4 categorías
                    - **Top 5 Meses:** Nuevo gráfico que compara cumplimiento vs % en ejecución
                    
                    #### **3. Indicadores mejorados:**
                    - 7 columnas de métricas (antes 6)
                    - Nueva métrica "Órdenes en Ejecución" en posición destacada
                    - Estadísticas adicionales con análisis de tendencia
                    
                    #### **4. Análisis mejorado:**
                    - Cálculo de eficiencia total (culminadas + en ejecución)
                    - Tasa de retraso como indicador adicional
                    - Recomendaciones automáticas basadas en los datos
                    
                    #### **5. Normalización de estados mejorada:**
                    - Acepta múltiples variantes para "EN PROCESO"
                    - Maneja inconsistencias en mayúsculas/minúsculas
                    - Más robusto ante variaciones en los datos
                    """)
                    
            else:
                st.info("No se pudieron cargar los datos del plan para 2026.")
                st.markdown("""
                ### 🔍 **Información:**
                - No se han encontrado órdenes de tipo **PREVENTIVO**, **BASADO EN CONDICIÓN** o **MEJORA DE SISTEMA** para el año 2026
                - Esto puede deberse a que:
                  1. Las órdenes aún no han sido creadas en el sistema
                  2. Las fechas de inicio de las órdenes no corresponden al año 2026
                  3. Los datos no han sido cargados correctamente
                
                ### **Solución:**
                - Verifica que el dataset contenga órdenes para el año 2026
                - Asegúrate de que las órdenes tengan los tipos correctos
                - Revisa que las fechas de inicio estén correctamente formateadas
                - Verifica que exista la columna 'STATUS' en los datos
                """)
        
    else:
        st.info("Por favor, carga datos para comenzar.")
        
        st.subheader("Instrucciones:")
        st.markdown("""
        1. **Carga automática desde Google Sheets:**
           - Los datos se cargan automáticamente desde Google Sheets al abrir la aplicación
           - Asegúrate de que el archivo de Google Sheets sea público y accesible
        
        2. **Estructura del archivo:**
           - Los datos deben estar en una hoja llamada 'DATAMTTO'
           - Los datos del personal deben estar en una hoja llamada 'PERSONAL'
           - Incluir columnas como: FECHA DE INICIO, FECHA DE FIN, EQUIPO, CONJUNTO, TIPO DE MTTO, RESPONSABLE, STATUS, etc.
        
        3. **Actualizaciones automáticas:**
           - Los datos de Google Sheets se actualizan automáticamente cada 5 minutos
           - Recarga la página para obtener los datos más recientes
        
        4. **NUEVA FUNCIONALIDAD: Cumplimiento del Plan con "Órdenes en Ejecución"**
           - La pestaña 'Cumplimiento del Plan' ahora incluye la categoría "Órdenes en Ejecución"
           - Esta categoría muestra las órdenes con status 'EN PROCESO'
           - Los gráficos han sido actualizados para reflejar esta nueva categoría
        """)

if __name__ == "__main__":
    main()
