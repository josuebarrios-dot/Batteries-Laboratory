import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.optimize import curve_fit
from scipy.stats import gaussian_kde
import re

# --- Librerías para Google Sheets ---
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="EMS - Estimación de Curva Solar", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    </style>
    """, unsafe_allow_html=True)

st.title("Estimación de Curva Solar Típica y Análisis Base")

# ==========================================
# 2. FUNCIONES DE DETECCIÓN Y PROCESAMIENTO
# ==========================================

def detectar_equipos_csv(columnas):
    inv_set, ctrl_set, bat_set = set(), set(), set()
    for col in columnas:
        col_l = col.lower()
        m_bat = re.search(r'(?i)(?:battery|bat|bateria)\s*[_#-]?\s*(\d+)', col_l)
        if m_bat: bat_set.add(m_bat.group(1))
            
        if 'charger' in col_l or 'controller' in col_l or 'controlador' in col_l:
            if 'inverter' not in col_l and 'inversor' not in col_l:
                m_ctrl = re.search(r'(?i)([a-z0-9]+\s*\d+):\s*(?:solar\s*)?(?:charger|controller)', col)
                if m_ctrl: ctrl_set.add(m_ctrl.group(1).lower())
                else:
                    m_ctrl2 = re.search(r'(?i)(?:controller|controlador|charger)\s*[_#-]?\s*(\d+)', col_l)
                    if m_ctrl2: ctrl_set.add(m_ctrl2.group(1))
                    
        if 'inverter' in col_l or 'inversor' in col_l:
            if 'pv' not in col.split(':')[0].lower():
                m_inv = re.search(r'(?i)^([^:]+):\s*Inverter', col)
                if m_inv: inv_set.add(m_inv.group(1).lower())
                else:
                    m_inv2 = re.search(r'(?i)(?:inverter|inversor)\s*[_#-]?\s*(\d+)', col_l)
                    if m_inv2: inv_set.add(m_inv2.group(1))

    return len(inv_set), len(ctrl_set), len(bat_set)

def find_cols(dataframe, must_include, exclude=None):
    found = []
    for col in dataframe.columns:
        col_lower = col.lower()
        if all(keyword.lower() in col_lower for keyword in must_include):
            if exclude:
                if not any(keyword.lower() in col_lower for keyword in exclude):
                    found.append(col)
            else:
                found.append(col)
    return found

def modelo_senoidal_solar(t, p_max, t_amanecer, t_atardecer):
    fase = (t - t_amanecer) / (t_atardecer - t_amanecer)
    return np.where((fase > 0) & (fase < 1), p_max * np.sin(np.pi * fase), 0.0)

@st.cache_data(show_spinner=False)
def procesar_sistema_solar(df_sky, cols_sistema, titulo_sistema, color_curva):
    if not cols_sistema: return None, None

    df_sky['P_inst'] = df_sky[cols_sistema].sum(axis=1, min_count=1).fillna(0)
    df_sky['P_inst_clean'] = np.where(df_sky['P_inst'] >= 0.6, df_sky['P_inst'], np.nan)
    
    df_env = df_sky.groupby('Time_Only').agg(
        P_real=('P_inst', 'max'),
        P_avg=('P_inst_clean', 'mean'),
        Hour_Decimal=('Hour_Decimal', 'first')
    ).reset_index()

    df_env['P_avg'] = df_env['P_avg'].fillna(0)

    x_data = df_env['Hour_Decimal'].values
    y_data = df_env['P_real'].values
    y_avg = df_env['P_avg'].values
    
    mask_dia = y_data > 0.1
    curva_teorica = np.zeros_like(x_data)
    
    if np.sum(mask_dia) > 10:
        p_max_obs = np.max(y_data[mask_dia])
        def modelo_ajuste(t, t_am, t_at):
            return modelo_senoidal_solar(t, p_max_obs, t_am, t_at)
        p0 = [6.25, 18.0]
        limites = ([5.5, 17.0], [7.5, 19.0])
        try:
            popt, _ = curve_fit(modelo_ajuste, x_data[mask_dia], y_data[mask_dia], p0=p0, bounds=limites)
            curva_teorica = modelo_senoidal_solar(x_data, p_max_obs, *popt)
        except: pass

    curva_maxima = y_data
    curva_tipica = np.where(x_data < 13.0, curva_teorica, curva_maxima)

    df_final = pd.DataFrame({
        'Hora_Dec': x_data,
        'Time_Only': df_env['Time_Only'],
        'Ideal': curva_teorica,
        'Maxima': curva_maxima,
        'Promedio': y_avg,
        'Tipica': curva_tipica
    })

    fig = go.Figure()
    for d_str in sorted(df_sky['Date_Str'].unique()):
        df_d = df_sky[df_sky['Date_Str'] == d_str]
        fig.add_trace(go.Scatter(x=df_d['Time_Only'], y=df_d['P_inst'], mode='lines', 
                                 line=dict(color='rgba(150,150,150,0.15)', width=1), showlegend=False))
    
    fig.add_trace(go.Scatter(x=df_env['Time_Only'], y=y_avg, mode='lines', name="Promedio", 
                             line=dict(color='#FFA500', width=3, dash='dash')))
    fig.add_trace(go.Scatter(x=df_env['Time_Only'], y=y_data, mode='lines', name="Máx Real", 
                             line=dict(color='rgba(255, 214, 0, 0.6)', width=2)))
    fig.add_trace(go.Scatter(x=df_env['Time_Only'], y=curva_teorica, mode='lines', name="Máx Ideal", 
                             line=dict(color=color_curva, width=4)))
    fig.add_trace(go.Scatter(x=df_env['Time_Only'], y=curva_tipica, mode='lines', name="Curva Típica", 
                             line=dict(color='#FF4B4B', width=2, dash='dot')))

    fig.update_layout(
        title=f"Datos Base: {titulo_sistema}",
        width=1200, height=400,
        template="plotly_dark",
        legend=dict(orientation="h", y=-0.2), 
        hovermode="x unified", 
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    return fig, df_final

@st.cache_data(show_spinner=False)
def procesar_perfil_carga(df, cols_carga):
    if not cols_carga: return None

    df_load = df[['Timestamp'] + cols_carga].copy()
    df_load['P_Load_Total'] = df_load[cols_carga].sum(axis=1, min_count=1)
    df_load['Hora_Int'] = df_load['Timestamp'].dt.hour
    
    df_load['P_Load_Clean'] = np.where(df_load['P_Load_Total'] >= 0.6, df_load['P_Load_Total'], np.nan)
    perfil_agrupado = df_load.groupby('Hora_Int')['P_Load_Clean'].mean().reset_index()
    perfil_completo = pd.merge(pd.DataFrame({'Hora_Int': range(24)}), perfil_agrupado, on='Hora_Int', how='left').fillna(0)
    
    return perfil_completo['P_Load_Clean'].values

# ==========================================
# 3. GESTIÓN DE ESTADO Y CONSTANTES
# ==========================================
if 'matriz_generacion' not in st.session_state: st.session_state['matriz_generacion'] = None

MESES_NOMBRES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

COLORES_MESES = [
    '#FF3366', '#FF9933', '#FFCC00', '#99CC33', '#33CC66', '#00CC99',
    '#00CCCC', '#3399FF', '#6666FF', '#9933FF', '#CC00CC', '#FF6699'
]

# ==========================================
# 4. BARRA LATERAL (ENTRADAS DE DATOS SOLAR)
# ==========================================
st.sidebar.header("1. Carga de Datos Solares (CSV)")
uploaded_file = st.sidebar.file_uploader("Cargar CSV para Análisis Solar", type=["csv"], key="solar_csv")

st.sidebar.markdown("---")
st.sidebar.header("2. Predicción Mensual Externa")
nombre_sitio = st.sidebar.text_input("Nombre del sitio (Pestaña en Google Sheets):")

if st.sidebar.button("Extraer Matriz de Generación"):
    if nombre_sitio:
        try:
            with st.spinner('Autenticando y extrayendo datos de Google Sheets...'):
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
                client = gspread.authorize(creds)
                
                sheet_id = "1jsH1jRExZpcPpZjUCcri-7g-Weye08twxMfj4RNqcbA"
                sh = client.open_by_key(sheet_id)
                worksheet = sh.worksheet(nombre_sitio)
                
                valores_matriz = worksheet.get('B31:Y42')
                df_matriz = pd.DataFrame(valores_matriz)
                df_matriz = df_matriz.replace(',', '.', regex=True).apply(pd.to_numeric, errors='coerce').fillna(0.0)
                
                df_matriz.index = MESES_NOMBRES
                df_matriz.columns = [f"{h:02d}:00" for h in range(24)]
                
                df_matriz['Total Día'] = df_matriz.sum(axis=1).round(2)
                valor_maximo = df_matriz['Total Día'].max()
                
                if valor_maximo > 0:
                    df_matriz['Factor'] = (df_matriz['Total Día'] / valor_maximo).round(4)
                else:
                    df_matriz['Factor'] = 0.0
                
                st.session_state['matriz_generacion'] = df_matriz
                
            st.sidebar.success("¡Matriz y Factores extraídos con éxito!")
            
        except gspread.exceptions.WorksheetNotFound:
            st.sidebar.error(f"No se encontró la pestaña '{nombre_sitio}'. Verifica el nombre.")
        except Exception as e:
            st.sidebar.error(f"Error al extraer los datos: {e}")
    else:
        st.sidebar.warning("Por favor ingresa un nombre de sitio válido.")

# ==========================================
# 5. VISUALIZACIÓN DE MATRIZ EXTERNA
# ==========================================
if st.session_state['matriz_generacion'] is not None:
    st.subheader("📊 Matriz Base Extraída desde Google Sheets")
    st.dataframe(st.session_state['matriz_generacion'], use_container_width=True)
    st.markdown("---")

# ==========================================
# 6. PROCESAMIENTO DE CSV SOLAR Y GRÁFICAS
# ==========================================
if uploaded_file is not None:
    df_raw = pd.read_csv(uploaded_file)
    df_raw.columns = [c.strip() for c in df_raw.columns]
    
    n_i, n_c, n_b = detectar_equipos_csv(df_raw.columns)
    
    st.sidebar.success(f"**Hardware Detectado:**\n• {n_i} Inversor(es)\n• {n_c} Controlador(es)\n• {n_b} Batería(s)")
    
    df_raw['Timestamp'] = pd.to_datetime(df_raw['Timestamp'])
    df_raw['Hour_Decimal'] = df_raw['Timestamp'].dt.hour + df_raw['Timestamp'].dt.minute/60.0 + df_raw['Timestamp'].dt.second/3600.0
    df_raw['Time_Only'] = df_raw['Timestamp'].apply(lambda d: d.replace(year=2000, month=1, day=1))
    df_raw['Date_Str'] = df_raw['Timestamp'].dt.date.astype(str)
    
    inv_cols = list(set(find_cols(df_raw, ['Array', 'Power'], exclude=['Charger', 'Charge']) + 
                        find_cols(df_raw, ['PV', 'Power'], exclude=['Charger', 'Charge'])))
    ctrl_cols = [c for c in df_raw.columns if ('Charger Power' in c or 'Charge Power' in c) and 'Solar' in c]
    meter_cols = find_cols(df_raw, ['Meter', 'Power'])
    load_cols = find_cols(df_raw, ['Load', 'Power'], exclude=['Meter'])
    cols_carga_a_usar = meter_cols if meter_cols else load_cols

    fig_base_inv, df_inv = procesar_sistema_solar(df_raw, inv_cols, "Inversores", "#00E676")
    fig_base_ctrl, df_ctrl = procesar_sistema_solar(df_raw, ctrl_cols, "Controladores", "#4FC3F7")
    carga_24h = procesar_perfil_carga(df_raw, cols_carga_a_usar)
    
    if carga_24h is not None and df_inv is not None:
        hora_int_array = np.floor(df_inv['Hora_Dec']).astype(int)
        carga_vector = np.array([carga_24h[h] for h in hora_int_array])
    else:
        carga_vector = np.zeros(len(df_inv)) if df_inv is not None else np.zeros(100)

    # 6.1. VISUALIZACIÓN DE GRÁFICAS BASE
    st.subheader("Análisis de Datos Base Solar (Superposición de Curvas)")
    
    col_base1, col_base2 = st.columns(2)
    with col_base1:
        if fig_base_inv: st.plotly_chart(fig_base_inv, use_container_width=True)
    with col_base2:
        if fig_base_ctrl: st.plotly_chart(fig_base_ctrl, use_container_width=True)
        
    st.markdown("---")

    # 6.2. GENERACIÓN DE CURVAS MENSUALES
    if df_inv is not None and df_ctrl is not None:
        def graficar_12_meses(df_fuente, titulo):
            fig = go.Figure()
            for i, mes_nombre in enumerate(MESES_NOMBRES):
                if st.session_state['matriz_generacion'] is not None:
                    factor = st.session_state['matriz_generacion'].loc[mes_nombre, 'Factor']
                    etiqueta = f"{mes_nombre} (F: {factor:.2f})"
                else:
                    factor = 1.0
                    etiqueta = f"{mes_nombre}"
                
                fig.add_trace(go.Scatter(x=df_fuente['Time_Only'], 
                                         y=df_fuente['Tipica'] * factor, 
                                         mode='lines', 
                                         name=etiqueta,
                                         line=dict(color=COLORES_MESES[i]),
                                         opacity=0.85))
            
            fig.add_trace(go.Scatter(x=df_fuente['Time_Only'], 
                                     y=carga_vector, 
                                     mode='lines', 
                                     name="Curva de Carga", 
                                     line=dict(color='white', width=3, dash='dash')))
            
            fig.update_layout(
                title=titulo, 
                width=1200, height=400,
                template="plotly_dark", 
                yaxis_title="Potencia (kW)", 
                hovermode="x unified",
                margin=dict(l=20, r=20, t=50, b=20)
            )
            return fig

        st.subheader("Predicción Mensual Solar (Curva Típica * Factor)")
        if st.session_state['matriz_generacion'] is not None:
            st.info("💡 Las gráficas están siendo escaladas usando el **Factor Normalizado** proveniente de Google Sheets.")
        else:
            st.info("💡 Factor de 1.0 aplicado a todos los meses (Extrae la matriz de Google Sheets para aplicar proyección mensual real).")
            
        col_pred1, col_pred2 = st.columns(2)
        with col_pred1:
            st.plotly_chart(graficar_12_meses(df_inv, "Predicción 12 Meses - Inversores"), use_container_width=True)
        with col_pred2:
            st.plotly_chart(graficar_12_meses(df_ctrl, "Predicción 12 Meses - Controladores"), use_container_width=True)
        
        col_pred3, col_pred4 = st.columns(2)
        df_total = df_inv.copy()
        df_total['Tipica'] = df_inv['Tipica'] + df_ctrl['Tipica']
        
        with col_pred3:
            st.plotly_chart(graficar_12_meses(df_total, "Producción Solar Total (Inv + Ctrl)"), use_container_width=True)

        # 6.3. TABLA HORIZONTAL POR MES
        st.markdown("---")
        st.subheader("Tabla Horizontal: Producción Típica Total CSV por Mes (kW)")
        
        df_total['Hora_Int'] = np.floor(df_total['Hora_Dec']).astype(int)
        perfil_base_24h = df_total.groupby('Hora_Int')['Tipica'].mean().reindex(range(24), fill_value=0).values
        
        datos_tabla = {}
        for i, mes_nombre in enumerate(MESES_NOMBRES):
            if st.session_state['matriz_generacion'] is not None:
                factor = st.session_state['matriz_generacion'].loc[mes_nombre, 'Factor']
            else:
                factor = 1.0
                
            datos_tabla[mes_nombre] = np.round(perfil_base_24h * factor, 2)
            
        columnas_horas = [f"{h:02d}:00" for h in range(24)]
        df_tabla_meses = pd.DataFrame.from_dict(datos_tabla, orient='index', columns=columnas_horas)
        
        st.dataframe(df_tabla_meses, use_container_width=True)

else:
    st.info("Sube un archivo CSV en la barra lateral para generar las gráficas base y predicciones solares.")

# ==========================================
# 7. ANÁLISIS DE CLIPPING Y ESTADO DE CARGA (NUEVA SECCIÓN)
# ==========================================
st.markdown("---")
st.header("Análisis de Batería (Clipping y SoC)")

uploaded_file_soc = st.file_uploader("Cargar CSV específico para Análisis de Batería (SoC)", type=["csv"], key="soc_csv")

if uploaded_file_soc is not None:
    df_soc_raw = pd.read_csv(uploaded_file_soc)
    df_soc_raw.columns = [c.strip() for c in df_soc_raw.columns]

    if 'Timestamp' in df_soc_raw.columns:
        df_soc_raw['Timestamp'] = pd.to_datetime(df_soc_raw['Timestamp'])
        df_soc_raw = df_soc_raw.sort_values('Timestamp')

        # Buscar automáticamente la columna de la batería
        soc_cols = find_cols(df_soc_raw, ['soc'])
        if not soc_cols:
            soc_cols = find_cols(df_soc_raw, ['state of charge'])

        if soc_cols:
            soc_col = soc_cols[0]

            # Interfaz de ajustes
            col_soc1, col_soc2 = st.columns(2)
            with col_soc1:
                threshold = st.number_input("Límite de Clipping (SoC %)", min_value=0.0, max_value=100.0, value=99.0, step=0.1)
            with col_soc2:
                rango_horas = st.slider("Rango de horas de producción solar", 0, 24, (7, 15))

            # Filtrar horas de producción
            df_soc_idx = df_soc_raw.set_index('Timestamp')
            start_time_str = f"{rango_horas[0]:02d}:00"
            end_time_str = f"{rango_horas[1]:02d}:00"
            df_day = df_soc_idx.between_time(start_time_str, end_time_str).copy()

            # CORRECCIÓN DEL KEY ERROR: Devolver el índice a columna antes de agrupar
            df_day = df_day.reset_index()

            # Filtrar donde el SoC supera el límite y extraer el primer evento del día
            df_full = df_day[df_day[soc_col] >= threshold].copy()
            df_full['Date'] = df_full['Timestamp'].dt.date
            first_full = df_full.groupby('Date').first().reset_index()

            if not first_full.empty:
                # Calcular formato decimal y la mediana
                first_full['Time_Decimal'] = first_full['Timestamp'].dt.hour + first_full['Timestamp'].dt.minute/60.0 + first_full['Timestamp'].dt.second/3600.0
                median_val = first_full['Time_Decimal'].median()
                median_hour = int(median_val)
                median_minute = int((median_val - median_hour) * 60)

                # Calcular campos para la gráfica de fondo
                df_soc_raw['Date_Str'] = df_soc_raw['Timestamp'].dt.date.astype(str)
                df_soc_raw['Hour_Decimal'] = df_soc_raw['Timestamp'].dt.hour + df_soc_raw['Timestamp'].dt.minute/60.0 + df_soc_raw['Timestamp'].dt.second/3600.0

                # ==========================================
                # GRÁFICA UNIFICADA DE SoC Y CLIPPING (PLOTLY)
                # ==========================================
                fig_soc = make_subplots(specs=[[{"secondary_y": True}]])

                fig_soc.add_trace(
                    go.Scatter(x=[None], y=[None], mode='lines', line=dict(color='gray', width=2), name="Perfil de SoC (Histórico)"),
                    secondary_y=False
                )

                # Capa 1: Perfiles de SoC diarios (Fondo)
                for d in df_soc_raw['Date_Str'].unique():
                    day_df = df_soc_raw[df_soc_raw['Date_Str'] == d]
                    fig_soc.add_trace(
                        go.Scatter(x=day_df['Hour_Decimal'], y=day_df[soc_col], mode='lines',
                                   line=dict(color='gray', width=1), opacity=0.3, showlegend=False),
                        secondary_y=False
                    )

                # Capa 2: Histograma de frecuencia
                fig_soc.add_trace(
                    go.Histogram(x=first_full['Time_Decimal'], marker_color='#FFD600', opacity=0.7,
                                 name="Frecuencia (Días)", nbinsx=15),
                    secondary_y=True
                )

                # Capa 3: Curva KDE (Campana de Gauss) usando Scipy
                try:
                    kde = gaussian_kde(first_full['Time_Decimal'])
                    x_kde = np.linspace(first_full['Time_Decimal'].min(), first_full['Time_Decimal'].max(), 100)
                    y_kde = kde(x_kde)
                    
                    bin_width = (first_full['Time_Decimal'].max() - first_full['Time_Decimal'].min()) / 15
                    if bin_width == 0: bin_width = 1
                    y_kde_scaled = y_kde * len(first_full) * bin_width

                    fig_soc.add_trace(
                        go.Scatter(x=x_kde, y=y_kde_scaled, mode='lines', line=dict(color='white', width=2), name="Distribución (KDE)"),
                        secondary_y=True
                    )
                except Exception:
                    pass

                # Líneas de referencia y zonas de sombra
                fig_soc.add_vline(x=median_val, line_dash="dash", line_color="red",
                                  annotation_text=f" Mediana: {median_hour:02d}:{median_minute:02d}",
                                  annotation_position="top left", annotation_font_color="red")
                fig_soc.add_hline(y=threshold, line_dash="dot", line_color="red", secondary_y=False)
                fig_soc.add_vrect(x0=rango_horas[0], x1=rango_horas[1], fillcolor="yellow", opacity=0.1, layer="below")

                fig_soc.update_layout(
                    title=f"Perfil Diario de Batería y Mediana de Clipping ({threshold}%)",
                    width=1200, height=500,
                    template="plotly_dark",
                    hovermode="x unified",
                    legend=dict(orientation="h", y=1.1)
                )
                fig_soc.update_xaxes(title_text="Hora del día (Formato 24h)", range=[0, 24],
                                     tickvals=list(range(0, 25, 2)),
                                     ticktext=[f"{h:02d}:00" for h in range(0, 25, 2)])
                fig_soc.update_yaxes(title_text="Estado de Carga - SoC (%)", range=[0, 105], secondary_y=False)
                fig_soc.update_yaxes(title_text="Frecuencia (Número de Días)", secondary_y=True)

                st.plotly_chart(fig_soc, use_container_width=True)

                # 5. Tabla de eventos exactos
                st.markdown(f"**Fechas y horas exactas de inicio de Clipping (SoC >= {threshold}%)**")
                df_tabla_clipping = first_full[['Timestamp', soc_col]].copy()
                df_tabla_clipping['Hora Exacta'] = df_tabla_clipping['Timestamp'].dt.strftime('%H:%M:%S')
                df_tabla_clipping['Fecha'] = df_tabla_clipping['Timestamp'].dt.strftime('%Y-%m-%d')
                
                col_t1, col_t2, col_t3 = st.columns([1,2,1])
                with col_t2:
                    st.dataframe(df_tabla_clipping[['Fecha', 'Hora Exacta', soc_col]], use_container_width=True, hide_index=True)

            else:
                st.warning(f"No se encontraron eventos donde el SoC superara el {threshold}% entre las {start_time_str} y {end_time_str}.")

        else:
            st.info("No se detectó una columna de SoC (State of Charge) en el CSV para realizar el análisis de batería.")
    else:
        st.error("El CSV subido no contiene una columna 'Timestamp'.")
