import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import curve_fit
import re

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

    # Suma de la potencia instantánea
    df_sky['P_inst'] = df_sky[cols_sistema].sum(axis=1, min_count=1).fillna(0)
    
    # Filtrar ruido para el promedio
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
    
    # 1. Curva Ideal (Clear Sky)
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

    # 2. Curva Máxima y Curva Típica (MODIFICADO A LAS 13:00)
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

    # Construcción de la Gráfica Original (Base) asegurando 1200x400
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
# 3. GESTIÓN DE ESTADO (IDENTIFICADORES)
# ==========================================
if 'n_baterias_det' not in st.session_state: st.session_state['n_baterias_det'] = 0
if 'n_inv_det' not in st.session_state: st.session_state['n_inv_det'] = 0
if 'n_ctrl_det' not in st.session_state: st.session_state['n_ctrl_det'] = 0

# ==========================================
# 4. EXTRACCIÓN DE DATOS
# ==========================================
st.sidebar.header("Carga de Datos")
uploaded_file = st.sidebar.file_uploader("Cargar CSV de Registros", type=["csv"])

st.sidebar.markdown("---")
meses_bajos = st.sidebar.multiselect("Meses con reducción del 20% (Curva Típica)", 
                                     options=list(range(1, 13)), default=[6, 7, 8],
                                     help="Selecciona 3 meses (ej. temporada de lluvias).")

if uploaded_file is not None:
    df_raw = pd.read_csv(uploaded_file)
    df_raw.columns = [c.strip() for c in df_raw.columns]
    
    n_i, n_c, n_b = detectar_equipos_csv(df_raw.columns)
    st.session_state['n_inv_det'] = n_i
    st.session_state['n_ctrl_det'] = n_c
    st.session_state['n_baterias_det'] = n_b
    
    st.sidebar.success(f"**Identificadores Mantenidos:**\n• {n_i} Inversor(es)\n• {n_c} Controlador(es)\n• {n_b} Batería(s)")
    
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

    # Procesar dataframes y extraer figuras
    fig_base_inv, df_inv = procesar_sistema_solar(df_raw, inv_cols, "Inversores", "#00E676")
    fig_base_ctrl, df_ctrl = procesar_sistema_solar(df_raw, ctrl_cols, "Controladores", "#4FC3F7")
    carga_24h = procesar_perfil_carga(df_raw, cols_carga_a_usar)
    
    # Expandir carga
    if carga_24h is not None and df_inv is not None:
        hora_int_array = np.floor(df_inv['Hora_Dec']).astype(int)
        carga_vector = np.array([carga_24h[h] for h in hora_int_array])
    else:
        carga_vector = np.zeros(len(df_inv)) if df_inv is not None else np.zeros(100)

    # ==========================================
    # 5. VISUALIZACIÓN DE GRÁFICAS BASE (FILA 1)
    # ==========================================
    st.subheader("Análisis de Datos Base (Superposición de Curvas)")
    
    col_base1, col_base2 = st.columns(2)
    with col_base1:
        if fig_base_inv: st.plotly_chart(fig_base_inv, use_container_width=True)
    with col_base2:
        if fig_base_ctrl: st.plotly_chart(fig_base_ctrl, use_container_width=True)
        
    st.markdown("---")

    # ==========================================
    # 6. GENERACIÓN DE CURVAS MENSUALES (FILA 2 y 3)
    # ==========================================
    if df_inv is not None and df_ctrl is not None:
        
        def graficar_12_meses(df_fuente, titulo, color_base):
            fig = go.Figure()
            for mes in range(1, 13):
                factor = 0.8 if mes in meses_bajos else 1.0
                nombre = f"Mes {mes} {'(Lluvia)' if factor < 1.0 else ''}"
                opacidad = 0.8 if factor < 1.0 else 0.4
                color = '#FF4B4B' if factor < 1.0 else color_base
                
                fig.add_trace(go.Scatter(x=df_fuente['Time_Only'], 
                                         y=df_fuente['Tipica'] * factor, 
                                         mode='lines', 
                                         name=nombre,
                                         line=dict(color=color),
                                         opacity=opacidad))
            
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

        st.subheader("Predicción Mensual (Curva Típica y Carga)")
        
        # Fila 2: Predicciones individuales
        col_pred1, col_pred2 = st.columns(2)
        with col_pred1:
            st.plotly_chart(graficar_12_meses(df_inv, "Predicción 12 Meses - Inversores", "#00E676"), use_container_width=True)
        with col_pred2:
            st.plotly_chart(graficar_12_meses(df_ctrl, "Predicción 12 Meses - Controladores", "#4FC3F7"), use_container_width=True)
        
        # Fila 3: Producción Total (Alineado a la izquierda u ocupando el ancho de 1 columna)
        col_pred3, col_pred4 = st.columns(2)
        df_total = df_inv.copy()
        df_total['Tipica'] = df_inv['Tipica'] + df_ctrl['Tipica']
        
        with col_pred3:
            st.plotly_chart(graficar_12_meses(df_total, "Producción Solar Total (Inv + Ctrl)", "#FFD700"), use_container_width=True)

        # ==========================================
        # 7. TABLA HORIZONTAL POR MES
        # ==========================================
        st.markdown("---")
        st.subheader("Tabla Horizontal: Producción Típica Total por Mes (kW)")
        
        # Agrupar por hora para tener el vector base de 24 horas (rellenado con 0 si faltan)
        df_total['Hora_Int'] = np.floor(df_total['Hora_Dec']).astype(int)
        perfil_base_24h = df_total.groupby('Hora_Int')['Tipica'].mean().reindex(range(24), fill_value=0).values
        
        # Generar las filas de la tabla mes a mes aplicando la reducción si corresponde
        datos_tabla = {}
        for mes in range(1, 13):
            factor = 0.8 if mes in meses_bajos else 1.0
            datos_tabla[f"Mes {mes}"] = np.round(perfil_base_24h * factor, 2)
            
        # Crear DataFrame final
        columnas_horas = [f"{h:02d}:00" for h in range(24)]
        df_tabla_meses = pd.DataFrame.from_dict(datos_tabla, orient='index', columns=columnas_horas)
        
        st.dataframe(df_tabla_meses, use_container_width=True)
        
else:
    st.info("Sube un archivo CSV en la barra lateral izquierda para generar las gráficas base y las predicciones mensuales.")
