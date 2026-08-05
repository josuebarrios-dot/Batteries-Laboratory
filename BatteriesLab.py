import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import io

# --- Librerías para Google Sheets y Drive ---
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from gspread_dataframe import set_with_dataframe
import statsmodels.api as sm

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Troubleshooting Tool - Batch Mode",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp { background-color: #0E1117; color: #FAFAFA; }
        .custom-header { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 24px; font-weight: 600; color: #FAFAFA; padding: 10px 0px; border-bottom: 1px solid #333; margin-bottom: 20px; }
        .card-title { font-size: 16px; font-weight: 600; color: #E0E0E0; text-align: center; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
        .kpi-card { background-color: #262730; padding: 20px; border-radius: 10px; border-left: 6px solid #444; margin-bottom: 10px; text-align: center; }
        .kpi-pass { border-left-color: #00E676 !important; }
        .kpi-fail { border-left-color: #FF5252 !important; }
        .kpi-title { font-size: 16px; color: #BBB; margin-bottom: 5px; text-transform: uppercase; }
        .kpi-value { font-size: 28px; font-weight: bold; color: #FFF; margin-bottom: 5px; }
        .kpi-sub { font-size: 13px; color: #888; font-family: 'Consolas', monospace; }
        .metric-container { background-color: #1E1E24; padding: 15px; border-radius: 8px; border: 1px solid #333; text-align: center; height: 100%; min-height: 120px; display: flex; flex-direction: column; justify-content: center; }
        .metric-label { font-size: 13px; color: #AAA; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
        .metric-val { font-size: 26px; font-weight: bold; color: #4FC3F7; }
        .metric-unit { font-size: 14px; color: #888; margin-left: 2px; }
        .metric-sub { font-size: 12px; color: #666; margin-top: 5px; }
        .val-solar { color: #FFD600 !important; }
        .val-grid { color: #2979FF !important; }
        .val-load { color: #00E676 !important; }
        .val-batt { color: #AB47BC !important; }
        .val-gen { color: #FF1744 !important; }
        .val-save { color: #69F0AE !important; }
        button[data-baseweb="tab"] { font-size: 16px !important; font-weight: 600 !important; color: #888 !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #00E676 !important; background-color: #262730 !important; }
        .block-container { padding: 1rem 2rem; }
        div[data-testid="stVerticalBlock"] > div { gap: 1rem; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="custom-header">HYBRICO TROUBLESHOOTING TOOL | BATCH EXPORTER</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. FUNCIONES GLOBALES
# -----------------------------------------------------------------------------
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

# =============================================================================
# INTERFAZ PRINCIPAL: MODO POR LOTE
# =============================================================================
with st.sidebar:
    st.header("Modo Por Lote")
    st.caption("Procesamiento masivo headless.")

tab_cargar, tab_resultados, tab_globales, tab_historico = st.tabs(["Cargar Sitios", "Resultados en Tabla", "Datos Globales", "Registro Histórico"])

# -----------------------------------------------------------------------
# PESTAÑA 1: CARGAR SITIOS
# -----------------------------------------------------------------------
with tab_cargar:
    st.markdown("#### Configuración de Sitios")

    metodo_carga = st.radio("Método de carga de datos:", ["Subida Manual", "Desde Carpeta de Google Drive"], horizontal=True)

    meses_lote = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    horas_lote = [f"{i}:00" for i in range(24)]

    if 'lote_site_data' not in st.session_state:
        st.session_state['lote_site_data'] = {}
    if 'lote_resultados' not in st.session_state:
        st.session_state['lote_resultados'] = None
    if 'drive_files_list' not in st.session_state:
        st.session_state['drive_files_list'] = []

    if metodo_carga == "Subida Manual":
        n_sitios = st.number_input("Cantidad de sitios a cargar:", min_value=1, max_value=50, value=3, step=1, key="lote_n_sitios")
        
        st.markdown("---")
        header_c1, header_c2, header_c3 = st.columns([2, 2, 3])
        with header_c1: st.markdown("**Archivo CSV**")
        with header_c2: st.markdown("**Nombre del Sitio**")
        with header_c3: st.markdown("**Estado de Extracción**")

        for i in range(int(n_sitios)):
            col_file, col_name, col_status = st.columns([2, 2, 3])
            with col_file:
                st.file_uploader(f"Sitio {i+1}", type=["csv"], key=f"lote_file_{i}", label_visibility="collapsed")
            with col_name:
                st.text_input(f"Nombre {i+1}", placeholder=f"Ej: Sitio {i+1}", key=f"lote_name_{i}", label_visibility="collapsed")
            with col_status:
                site_key = f"site_{i}"
                if site_key in st.session_state['lote_site_data']:
                    data_entry = st.session_state['lote_site_data'][site_key]
                    if data_entry.get('ok'):
                        st.success(f"OK — AC Load: {data_entry['avg_load']} W | Energy: {data_entry['energy_cons']} kWh")
                    else:
                        st.error(data_entry.get('error', 'Error desconocido'))
                else:
                    st.empty()
    
    else:
        # Opción desde Google Drive
        folder_id = st.text_input("ID de la carpeta de Google Drive:")
        if st.button("Buscar archivos CSV en Carpeta"):
            if folder_id:
                with st.spinner("Buscando archivos..."):
                    scopes_drive = ["https://www.googleapis.com/auth/drive"]
                    creds_drive = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes_drive)
                    drive_service = build('drive', 'v3', credentials=creds_drive)
                    
                    query = f"'{folder_id}' in parents and trashed=false"
                    results = drive_service.files().list(
                        q=query, 
                        fields="files(id, name)", 
                        pageSize=100,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True
                    ).execute()
                    
                    todos_los_archivos = results.get('files', [])
                    items = [f for f in todos_los_archivos if f['name'].lower().endswith('.csv')]
                    
                    if items:
                        st.session_state['drive_files_list'] = items
                        st.session_state['lote_n_sitios'] = len(items)
                        st.success(f"Se encontraron {len(items)} archivos CSV.")
                    else:
                        st.warning("No se encontraron CSVs en esa carpeta. (Verifica el ID y los permisos de la Service Account).")
                        st.session_state['drive_files_list'] = []

        items = st.session_state.get('drive_files_list', [])
        n_sitios = len(items)
        st.session_state['lote_n_sitios'] = n_sitios

        if items:
            st.markdown("---")
            header_c1, header_c2, header_c3 = st.columns([2, 2, 3])
            with header_c1: st.markdown("**Archivo Detectado en Drive**")
            with header_c2: st.markdown("**Nombre del Sitio (Editable)**")
            with header_c3: st.markdown("**Estado de Extracción**")

            for i, file_item in enumerate(items):
                col_file, col_name, col_status = st.columns([2, 2, 3])
                with col_file:
                    st.info(file_item['name'])
                    st.session_state[f"lote_drive_file_id_{i}"] = file_item['id']
                with col_name:
                    default_name = file_item['name'].replace('.csv', '')
                    st.text_input(f"Nombre {i+1}", value=default_name, key=f"lote_name_{i}", label_visibility="collapsed")
                with col_status:
                    site_key = f"site_{i}"
                    if site_key in st.session_state['lote_site_data']:
                        data_entry = st.session_state['lote_site_data'][site_key]
                        if data_entry.get('ok'):
                            st.success(f"OK — AC Load: {data_entry['avg_load']} W | Energy: {data_entry['energy_cons']} kWh")
                        else:
                            st.error(data_entry.get('error', 'Error desconocido'))
                    else:
                        st.empty()

    st.markdown("---")
    btn_col1, btn_col2, _ = st.columns([2, 2, 3])

    with btn_col1:
        btn_extraer = st.button("EXTRAER INFORMACIÓN", type="primary", use_container_width=True)
    with btn_col2:
        btn_generar = st.button("GENERAR RESULTADOS", type="secondary", use_container_width=True)

    # -----------------------------------------------------------------------------------
    # ================== EXTRACCIÓN DE INFORMACIÓN (TIGO GT MODIFICADO) =================
    # -----------------------------------------------------------------------------------
    if btn_extraer:
        nombres = [st.session_state.get(f"lote_name_{i}", "").strip() for i in range(int(n_sitios))]
        nombres_validos = [n for n in nombres if n]

        if not nombres_validos:
            st.warning("Ingresa al menos un nombre de sitio antes de extraer.")
        else:
            with st.spinner("Conectando con Google Sheets y descargando datos del TIGO GT..."):
                try:
                    scopes_lote = [
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"
                    ]
                    creds_lote = Credentials.from_service_account_info(
                        dict(st.secrets["gcp_service_account"]), scopes=scopes_lote
                    )
                    client_lote = gspread.authorize(creds_lote)

                    sheet_tigo_url = "https://docs.google.com/spreadsheets/d/1TR6bd4JHGWQUkWacnCoCTkybriJaWA6k1G2o96MA4cU/edit"
                    sh_tigo = client_lote.open_by_url(sheet_tigo_url)
                    ws_tigo = sh_tigo.worksheet("TIGO GT")
                    
                    all_tigo_data = ws_tigo.get_all_values()

                    # Mapear inicio de bloques ignorando celdas irrelevantes
                    site_row_map = {}
                    for r_idx, row in enumerate(all_tigo_data):
                        if len(row) > 0 and row[0].strip() != "":
                            label = row[0].strip()
                            if label in nombres_validos:
                                site_row_map[label] = r_idx

                    st.session_state['lote_site_data'] = {}

                    for i in range(int(n_sitios)):
                        site_nombre = st.session_state.get(f"lote_name_{i}", "").strip()
                        site_key = f"site_{i}"

                        if not site_nombre:
                            continue

                        result = {'ok': False, 'nombre': site_nombre, 'error': ''}

                        if site_nombre in site_row_map:
                            r_idx = site_row_map[site_nombre]
                            
                            try:
                                avg_load_ext = "0"
                                energy_cons_ext = "0"
                                
                                # Extraer Total AC site load y Site energy consumption (se encuentran filas abajo)
                                for offset in range(1, 20):
                                    if r_idx + offset < len(all_tigo_data):
                                        row_check = all_tigo_data[r_idx + offset]
                                        if len(row_check) > 1:
                                            lbl = row_check[0].strip()
                                            if lbl == "Total AC site load (W)":
                                                avg_load_ext = row_check[1]
                                            elif lbl == "Site energy consumption (kWh/month)":
                                                energy_cons_ext = row_check[1]
                                                
                                result['avg_load'] = avg_load_ext
                                result['energy_cons'] = energy_cons_ext

                                float_matrix = []
                                cov_monthly = []
                                es_monthly = []
                                ru_monthly = []

                                # Extraer Matriz PV y KPIs mensuales dinámicos (12 meses a partir de r_idx+2)
                                for offset in range(2, 14):
                                    if r_idx + offset < len(all_tigo_data):
                                        row_mat = all_tigo_data[r_idx + offset]
                                        
                                        # Matriz PV (B a la Y)
                                        row_floats = []
                                        for hi in range(1, 25):
                                            if hi < len(row_mat) and row_mat[hi].strip() != '':
                                                try: row_floats.append(float(row_mat[hi].replace(',', '').strip()))
                                                except: row_floats.append(0.0)
                                            else:
                                                row_floats.append(0.0)
                                        float_matrix.append(row_floats)
                                        
                                        # Función segura para limpiar numéricos y porcentajes
                                        def get_kpi(idx):
                                            if idx < len(row_mat) and row_mat[idx].strip() != '':
                                                raw = row_mat[idx].strip()
                                                if '%' in raw:
                                                    try: return float(raw.replace('%', '').replace(',', ''))
                                                    except: return 0.0
                                                else:
                                                    try:
                                                        parsed = float(raw.replace(',', ''))
                                                        # Si es cobertura expresada en decimal (ej. 0.61), convertimos a 61.0%
                                                        if idx == 54 and parsed > 0 and parsed <= 1.0:
                                                            parsed *= 100.0
                                                        return parsed
                                                    except: return 0.0
                                            return 0.0
                                            
                                        ru_monthly.append(get_kpi(53)) # Real utilizable solar energy (BB)
                                        cov_monthly.append(get_kpi(54)) # Coverage (%) (BC)
                                        es_monthly.append(get_kpi(55)) # Energy Saved (BD)
                                        
                                    else:
                                        float_matrix.append([0.0] * 24)
                                        ru_monthly.append(0.0)
                                        cov_monthly.append(0.0)
                                        es_monthly.append(0.0)

                                result['baseline_matrix'] = pd.DataFrame(float_matrix, index=meses_lote, columns=horas_lote)
                                result['coverage_monthly'] = cov_monthly
                                result['energy_saved_monthly'] = es_monthly
                                result['real_utilizable_monthly'] = ru_monthly
                                
                                balance_ok = True
                                matrix_ok = True
                            except Exception as ex:
                                result['error'] = f"Error leyendo KPIs o matriz: {ex}"
                                balance_ok = False
                                matrix_ok = False
                        else:
                            result['error'] = f"'{site_nombre}' no encontrado en la columna A del TIGO GT."
                            balance_ok = False
                            matrix_ok = False

                        result['ok'] = balance_ok and matrix_ok
                        if not result['ok'] and not result.get('error'):
                            result['error'] = "Fallo en extracción."

                        st.session_state['lote_site_data'][site_key] = result

                    st.rerun()

                except Exception as e:
                    import traceback
                    st.error(f"Error de conexión con Google Sheets: {e}")
                    st.code(traceback.format_exc())

    # GENERAR RESULTADOS (MATEMÁTICAS)
    if btn_generar:
        resultados_lista = []
        sitios_procesados = 0
        sitios_saltados = 0

        progress_bar = st.progress(0, text="Procesando sitios...")

        for i in range(int(n_sitios)):
            site_key = f"site_{i}"
            site_nombre = st.session_state.get(f"lote_name_{i}", "").strip()
            site_data = st.session_state['lote_site_data'].get(site_key)

            archivo_manual = st.session_state.get(f"lote_file_{i}")
            drive_file_id = st.session_state.get(f"lote_drive_file_id_{i}")

            progress_bar.progress((i + 1) / int(n_sitios), text=f"Procesando {site_nombre or f'Sitio {i+1}'}...")

            if (archivo_manual is None and drive_file_id is None) or site_data is None or not site_data.get('ok'):
                sitios_saltados += 1
                continue

            try:
                archivo_final = None

                if archivo_manual is not None:
                    archivo_manual.seek(0)
                    archivo_final = archivo_manual
                elif drive_file_id is not None:
                    scopes_drive = ["https://www.googleapis.com/auth/drive"]
                    creds_drive = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes_drive)
                    drive_service = build('drive', 'v3', credentials=creds_drive)
                    
                    request = drive_service.files().get_media(fileId=drive_file_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    fh.seek(0)
                    archivo_final = fh

                df_lote = pd.read_csv(archivo_final)
                df_lote.columns = [c.strip() for c in df_lote.columns]

                if 'Timestamp' not in df_lote.columns:
                    sitios_saltados += 1
                    continue

                df_lote['Timestamp'] = pd.to_datetime(df_lote['Timestamp'])
                df_lote.sort_values('Timestamp', inplace=True)

                for c in df_lote.columns:
                    if c != 'Timestamp':
                        if df_lote[c].dtype == 'object':
                            df_lote[c] = df_lote[c].astype(str).str.replace(',', '').str.strip()
                        df_lote[c] = pd.to_numeric(df_lote[c], errors='coerce')

                # --- Auto-detección ---
                dig_cols_l = find_cols(df_lote, ['Digital'])
                edge_offline_cols_l = find_cols(df_lote, ['Edge', 'Offline'])
                edge_col_l = edge_offline_cols_l[0] if edge_offline_cols_l else None
                load_cols_l = find_cols(df_lote, ['Load', 'Power'], exclude=['Meter'])
                mains_cols_l = list(set(find_cols(df_lote, ['Mains', 'Power']) + find_cols(df_lote, ['Grid', 'Power'])))
                pv_cols_l = list(set(
                    find_cols(df_lote, ['Array', 'Power'], exclude=['Charger', 'Charge']) +
                    find_cols(df_lote, ['PV', 'Power'], exclude=['Charger', 'Charge']) +
                    find_cols(df_lote, ['Inverter', 'Array', 'Power'])
                ))
                solar_cp_cols_l = [c for c in df_lote.columns if ('Charger Power' in c or 'Charge Power' in c) and 'Solar' in c]
                batt_cols_l = find_cols(df_lote, ['Battery', 'Power'], exclude=['Bank', 'Module'])
                batt_bank_p_cols_l = find_cols(df_lote, ['Battery', 'Bank', 'Power'])
                batt_soc_cols_l = find_cols(df_lote, ['Battery', 'SoC'])
                meter_cols_l = find_cols(df_lote, ['Meter', 'Power'])

                # --- Cálculos matemáticos y Rango de Fechas ---
                df_calc_l = df_lote.copy()
                df_calc_l['delta_h'] = df_calc_l['Timestamp'].diff().dt.total_seconds().div(3600).fillna(0)
                total_duration_h_l = df_calc_l['delta_h'].sum()

                start_date_l = df_lote['Timestamp'].min().date()
                end_date_l = df_lote['Timestamp'].max().date()
                
                # Identificamos el mes modal en la muestra (0 = Enero, 11 = Diciembre)
                mode_month_idx = df_lote['Timestamp'].dt.month.mode()[0] - 1
                dias_analizados_l = total_duration_h_l / 24.0 if total_duration_h_l > 0 else 1.0

                max_load_l, avg_load_l = 0.0, 0.0
                if load_cols_l:
                    total_load_p_l = df_lote[load_cols_l].sum(axis=1)
                    max_load_l = total_load_p_l.max()
                    avg_load_l = total_load_p_l[total_load_p_l >= 0.5].mean()
                    if pd.isna(avg_load_l): avg_load_l = 0.0

                max_mains_l, avg_mains_l = 0.0, 0.0
                if mains_cols_l:
                    total_mains_p_l = df_lote[mains_cols_l].sum(axis=1)
                    max_mains_l = total_mains_p_l.max()
                    avg_mains_l = total_mains_p_l[total_mains_p_l >= 0.5].mean()
                    if pd.isna(avg_mains_l): avg_mains_l = 0.0
                else:
                    total_mains_p_l = pd.Series([0.0] * len(df_calc_l))

                energia_carga_total_l = 0.0
                if meter_cols_l:
                    energia_carga_total_l = (df_calc_l[meter_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()
                elif load_cols_l:
                    energia_carga_total_l = (df_calc_l[load_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()
                potencia_rango_l = energia_carga_total_l / total_duration_h_l if total_duration_h_l > 0 else 0.0

                col_di2_l = next((c for c in dig_cols_l if "2" in c), None)
                col_di3_l = next((c for c in dig_cols_l if "3" in c), None)

                total_load_for_diff_l = (
                    df_calc_l[meter_cols_l].sum(axis=1) if meter_cols_l else
                    (df_calc_l[load_cols_l].sum(axis=1) if load_cols_l else pd.Series([0.0] * len(df_calc_l)))
                )

                mask_valid_comm_l = (df_calc_l[edge_col_l] == 0) if edge_col_l else pd.Series([True] * len(df_calc_l))
                total_duration_h_valid_l = df_calc_l.loc[mask_valid_comm_l, 'delta_h'].sum()

                grid_availability_pct_l = 0.0
                if col_di2_l:
                    mask_grid_disp_l = (df_calc_l[col_di2_l] > 0) & mask_valid_comm_l
                    t_grid_disp_l = df_calc_l.loc[mask_grid_disp_l, 'delta_h'].sum()
                    grid_availability_pct_l = (t_grid_disp_l / total_duration_h_valid_l * 100) if total_duration_h_valid_l > 0 else 0.0

                e_grid_l, e_gen_l, t_grid_l, t_gen_l, e_extra_grid_l = 0.0, 0.0, 0.0, 0.0, 0.0
                if col_di2_l and col_di3_l:
                    mask_grid_l = (df_calc_l[col_di2_l] > 0) & (total_mains_p_l > 0.5)
                    mask_gen_l = (df_calc_l[col_di2_l] == 0) & (df_calc_l[col_di3_l] > 0) & (total_mains_p_l > 0.5)
                    e_grid_l = (total_mains_p_l[mask_grid_l] * df_calc_l.loc[mask_grid_l, 'delta_h']).sum()
                    e_gen_l = (total_mains_p_l[mask_gen_l] * df_calc_l.loc[mask_gen_l, 'delta_h']).sum()
                    t_grid_l = df_calc_l.loc[mask_grid_l, 'delta_h'].sum()
                    t_gen_l = df_calc_l.loc[mask_gen_l, 'delta_h'].sum()
                    diff_grid_l = total_mains_p_l[mask_grid_l] - total_load_for_diff_l[mask_grid_l]
                    e_extra_grid_l = (diff_grid_l[diff_grid_l > 0] * df_calc_l.loc[mask_grid_l, 'delta_h'][diff_grid_l > 0]).sum()
                elif mains_cols_l:
                    mask_grid_l = total_mains_p_l > 0.5
                    e_grid_l = (total_mains_p_l[mask_grid_l] * df_calc_l.loc[mask_grid_l, 'delta_h']).sum()
                    t_grid_l = df_calc_l.loc[mask_grid_l, 'delta_h'].sum()
                    diff_grid_l = total_mains_p_l[mask_grid_l] - total_load_for_diff_l[mask_grid_l]
                    e_extra_grid_l = (diff_grid_l[diff_grid_l > 0] * df_calc_l.loc[mask_grid_l, 'delta_h'][diff_grid_l > 0]).sum()

                # Solar Real
                e_solar_inv_l, e_solar_ctrl_l = 0.0, 0.0
                if pv_cols_l: e_solar_inv_l = (df_calc_l[pv_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()
                if solar_cp_cols_l: e_solar_ctrl_l = (df_calc_l[solar_cp_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()
                total_solar_real_l = e_solar_inv_l + e_solar_ctrl_l

                # Batería y Autoconsumo
                batt_source_cols_l = batt_bank_p_cols_l if batt_bank_p_cols_l else batt_cols_l
                e_load_meter_l = 0.0
                if meter_cols_l:
                    e_load_meter_l = (df_calc_l[meter_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()
                elif load_cols_l:
                    e_load_meter_l = (df_calc_l[load_cols_l].sum(axis=1) * df_calc_l['delta_h']).sum()

                p_solar_inst_l = 0.0
                if pv_cols_l: p_solar_inst_l = df_calc_l[pv_cols_l].sum(axis=1).fillna(0)
                if solar_cp_cols_l:
                    p_solar_inst_l = (p_solar_inst_l if not isinstance(p_solar_inst_l, float) else pd.Series([0.0]*len(df_calc_l))) + df_calc_l[solar_cp_cols_l].sum(axis=1).fillna(0)
                p_mains_inst_l = df_calc_l[mains_cols_l].sum(axis=1).fillna(0) if mains_cols_l else pd.Series([0.0]*len(df_calc_l))
                p_load_inst_l = (df_calc_l[meter_cols_l].sum(axis=1).fillna(0) if meter_cols_l else
                                 (df_calc_l[load_cols_l].sum(axis=1).fillna(0) if load_cols_l else pd.Series([0.0]*len(df_calc_l))))
                if isinstance(p_solar_inst_l, float): p_solar_inst_l = pd.Series([0.0]*len(df_calc_l))

                p_bat_inst_l = df_calc_l[batt_source_cols_l].sum(axis=1).fillna(0) if batt_source_cols_l else pd.Series([0.0]*len(df_calc_l))
                p_perdidas_inst_l = (p_solar_inst_l + p_mains_inst_l - p_bat_inst_l - p_load_inst_l).clip(lower=0)
                e_autoconsumo_l = (p_perdidas_inst_l * df_calc_l['delta_h']).sum()

                denom_load_l = e_load_meter_l if e_load_meter_l > 0 else 1.0
                kpi_ahorro_l = (1 - (e_grid_l / denom_load_l)) * 100
                kpi_solar_cov_l = (total_solar_real_l / denom_load_l) * 100
                kpi_gen_dep_l = (e_gen_l / denom_load_l) * 100

                avg_soc_max_l, avg_soc_min_l, avg_dod_l = 0.0, 0.0, 0.0
                uso_txt_l = "N/A"
                if batt_soc_cols_l and not df_lote[batt_soc_cols_l].dropna(how='all').empty:
                    soc_series_l = df_lote[batt_soc_cols_l].mean(axis=1)
                    daily_soc_l = soc_series_l.groupby(df_lote['Timestamp'].dt.date)
                    avg_soc_min_l = daily_soc_l.min().mean()
                    avg_soc_max_l = daily_soc_l.max().mean()
                    avg_dod_l = avg_soc_max_l - avg_soc_min_l
                    if avg_dod_l < 20: uso_txt_l = "Subutilizada"
                    elif avg_dod_l > 80: uso_txt_l = "Ciclo Profundo"
                    else: uso_txt_l = "Ciclo Saludable"

                # ================= ASIGNACIÓN DINÁMICA DE KPIs MES A MES =================

                # Total AC site load (W)
                try: avg_site_load_l = float(str(site_data.get('avg_load', 0)).replace(',', '').strip())
                except: avg_site_load_l = 0.0
                
                # Site energy consumption (kWh/month)
                try: energy_cons_val_l = float(str(site_data.get('energy_cons', 0)).replace(',', '').strip())
                except: energy_cons_val_l = 0.0

                # Load Coverage (Real) dinámico
                cov_monthly_arr = site_data.get('coverage_monthly', [0.0]*12)
                cov_val_l = cov_monthly_arr[mode_month_idx]

                # Ahorro Esperado Mensual dinámico (Energy Saved)
                es_monthly_arr = site_data.get('energy_saved_monthly', [0.0]*12)
                ahorro_esp_mensual_l = es_monthly_arr[mode_month_idx]

                # Solar Esperado = Real utilizable solar energy diario * dias analizados
                ru_monthly_arr = site_data.get('real_utilizable_monthly', [0.0]*12)
                ru_daily = ru_monthly_arr[mode_month_idx]
                total_solar_esperado_l = ru_daily * dias_analizados_l
                
                # ==========================================================================

                ahorro_real_periodo_l = e_load_meter_l * (kpi_ahorro_l / 100.0)
                ahorro_real_mensual_proj_l = (ahorro_real_periodo_l / dias_analizados_l) * 30.0
                deficit_mensual_l = ahorro_esp_mensual_l - ahorro_real_mensual_proj_l
                cumplimiento_pct_l = (ahorro_real_mensual_proj_l / ahorro_esp_mensual_l * 100.0) if ahorro_esp_mensual_l > 0 else 0.0

                fila = {
                    "Sitio": site_nombre,
                    "Fecha Reporte": pd.Timestamp.now(tz='America/Guatemala').strftime("%Y-%m-%d %H:%M"),
                    "Rango Inicio": str(start_date_l),
                    "Rango Fin": str(end_date_l),
                    "Carga Max (kW)": round(max_load_l, 2),
                    "Carga Promedio (kW)": round(avg_load_l, 2),
                    "Potencia Rango (kW)": round(potencia_rango_l, 2),
                    "Avg. site load (W)": avg_site_load_l,
                    "Carga (Meter) (kWh)": round(e_load_meter_l, 2),
                    "Site energy cons. (kWh/month)": round(energy_cons_val_l, 2),
                    "Solar Real (kWh)": round(total_solar_real_l, 2),
                    "Solar Esperado (kWh)": round(total_solar_esperado_l, 2),
                    "Ahorro Red (%)": round(kpi_ahorro_l, 2),
                    "Cobertura Solar (%)": round(kpi_solar_cov_l, 2),
                    "Load Coverage (Real)": round(cov_val_l, 2),
                    "Ahorro Esperado": round(ahorro_esp_mensual_l, 2),
                    "Ahorro Real": round(ahorro_real_mensual_proj_l, 2),
                    "Déficit Mensual": round(deficit_mensual_l, 2),
                    "Cumplimiento": round(cumplimiento_pct_l, 2),
                    "Mains Max (kW)": round(max_mains_l, 2),
                    "Mains Promedio (kW)": round(avg_mains_l, 2),
                    "Energía Red (kWh)": round(e_grid_l, 2),
                    "Energía Gen (kWh)": round(e_gen_l, 2),
                    "Tiempo Red (h)": round(t_grid_l, 2),
                    "Tiempo Gen (h)": round(t_gen_l, 2),
                    "Disponibilidad Red (%)": round(grid_availability_pct_l, 2),
                    "Uso Generador (%)": round(kpi_gen_dep_l, 2),
                    "Extra de Red (kWh)": round(e_extra_grid_l, 2),
                    "Autoconsumo (kWh)": round(e_autoconsumo_l, 2),
                    "SoC Max (%)": round(avg_soc_max_l, 2),
                    "SoC Min (%)": round(avg_soc_min_l, 2),
                    "DoD (%)": round(avg_dod_l, 2),
                    "Estado Batería": uso_txt_l,
                }
                resultados_lista.append(fila)
                sitios_procesados += 1

            except Exception as e_site:
                st.warning(f"Error procesando '{site_nombre}': {e_site}")
                sitios_saltados += 1

        progress_bar.empty()

        if resultados_lista:
            st.session_state['lote_resultados'] = pd.DataFrame(resultados_lista)
            st.success(f"Procesamiento completo: {sitios_procesados} sitio(s) procesados, {sitios_saltados} saltado(s). Ve a la pestaña 'Resultados en Tabla'.")
        else:
            st.error("No se pudo procesar ningún sitio. Verifica que los CSVs estén cargados y que la extracción haya sido exitosa.")

# -----------------------------------------------------------------------
# PESTAÑA 2: RESULTADOS EN TABLA (Y EXPORTACIÓN CON HTML)
# -----------------------------------------------------------------------
with tab_resultados:
    st.markdown("#### Resultados del Lote")
    if st.session_state.get('lote_resultados') is not None and not st.session_state['lote_resultados'].empty:
        df_res = st.session_state['lote_resultados']
        
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Sitios procesados", len(df_res))
        r2.metric("Cobertura Solar Prom.", f"{df_res['Cobertura Solar (%)'].mean():.1f}%")
        r3.metric("Cumplimiento Prom.", f"{df_res['Cumplimiento'].mean():.1f}%")
        r4.metric("Solar Real Total", f"{df_res['Solar Real (kWh)'].sum():.1f} kWh")

        st.markdown("---")
        st.dataframe(df_res, use_container_width=True, height=500)

        st.markdown("---")
        st.markdown("#### Exportar a Google Sheets")

        exp_c1, exp_c2, exp_c3 = st.columns(3)
        with exp_c1: lote_sheet_url = st.text_input("URL del Google Sheet:", value="https://docs.google.com/spreadsheets/d/1WmxMv9I6dMG8Hlf3M8xkV3pc4z2m0wtn-OO6A2MREkM/edit?gid=0#gid=0", key="lote_sheet_url")
        with exp_c2: lote_sheet_tab = st.text_input("Nombre de la pestaña (Hoja):", value="Data Exporter", key="lote_sheet_tab")
        with exp_c3: lote_drive_folder = st.text_input("ID de carpeta de Google Drive:", value="1cWPibQBXlrThIBWEjyU7rf_LjtW7KUv-", key="lote_drive_folder")

        if st.button("Exportar datos a Google Sheets", type="primary"):
            if not lote_sheet_url or not lote_drive_folder:
                st.warning("Completa la URL del Sheet y el ID de Drive.")
            else:
                try:
                    with st.spinner("Generando reportes HTML individuales, subiendo a Drive y exportando a Sheets..."):
                        scopes_exp = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                        creds_exp = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes_exp)
                        drive_svc = build('drive', 'v3', credentials=creds_exp)
                        
                        res_lookup = {row["Sitio"]: row for _, row in df_res.iterrows()}
                        links_por_sitio = {}

                        n_sitios_exp = int(st.session_state.get("lote_n_sitios", 0))

                        for i in range(n_sitios_exp):
                            nombre_exp = st.session_state.get(f"lote_name_{i}", "").strip()
                            archivo_manual_exp = st.session_state.get(f"lote_file_{i}")
                            drive_file_id_exp = st.session_state.get(f"lote_drive_file_id_{i}")

                            if (archivo_manual_exp is None and drive_file_id_exp is None) or not nombre_exp or nombre_exp not in res_lookup:
                                continue

                            row_r = res_lookup[nombre_exp]
                            site_data_exp = st.session_state['lote_site_data'].get(f"site_{i}", {})
                            if not site_data_exp.get('ok'): continue

                            archivo_final_exp = None
                            if archivo_manual_exp is not None:
                                archivo_manual_exp.seek(0)
                                archivo_final_exp = archivo_manual_exp
                            else:
                                request = drive_svc.files().get_media(fileId=drive_file_id_exp)
                                fh = io.BytesIO()
                                downloader = MediaIoBaseDownload(fh, request)
                                done = False
                                while not done: status, done = downloader.next_chunk()
                                fh.seek(0)
                                archivo_final_exp = fh

                            df_exp = pd.read_csv(archivo_final_exp)
                            df_exp.columns = [c.strip() for c in df_exp.columns]
                            df_exp['Timestamp'] = pd.to_datetime(df_exp['Timestamp'])
                            df_exp.sort_values('Timestamp', inplace=True)
                            
                            for c in df_exp.columns:
                                if c != 'Timestamp':
                                    if df_exp[c].dtype == 'object': df_exp[c] = df_exp[c].astype(str).str.replace(',', '').str.strip()
                                    df_exp[c] = pd.to_numeric(df_exp[c], errors='coerce')

                            # Detección de columnas
                            dig_e = find_cols(df_exp, ['Digital'])
                            edge_e_cols = find_cols(df_exp, ['Edge', 'Offline'])
                            edge_e = edge_e_cols[0] if edge_e_cols else None
                            load_e = find_cols(df_exp, ['Load', 'Power'], exclude=['Meter'])
                            mains_e = list(set(find_cols(df_exp, ['Mains', 'Power']) + find_cols(df_exp, ['Grid', 'Power'])))
                            pv_e = list(set(
                                find_cols(df_exp, ['Array', 'Power'], exclude=['Charger', 'Charge']) +
                                find_cols(df_exp, ['PV', 'Power'], exclude=['Charger', 'Charge']) +
                                find_cols(df_exp, ['Inverter', 'Array', 'Power'])
                            ))
                            solar_cp_e = [c for c in df_exp.columns if ('Charger Power' in c or 'Charge Power' in c) and 'Solar' in c]
                            batt_e = find_cols(df_exp, ['Battery', 'Power'], exclude=['Bank', 'Module'])
                            batt_bank_e = find_cols(df_exp, ['Battery', 'Bank', 'Power'])
                            batt_soc_e = find_cols(df_exp, ['Battery', 'SoC'])
                            meter_e = find_cols(df_exp, ['Meter', 'Power'])
                            batt_src_e = batt_bank_e if batt_bank_e else batt_e

                            df_calc_e = df_exp.copy()
                            df_calc_e['delta_h'] = df_calc_e['Timestamp'].diff().dt.total_seconds().div(3600).fillna(0)

                            # Recuperación de variables 
                            max_load_e = float(row_r["Carga Max (kW)"])
                            avg_load_e = float(row_r["Carga Promedio (kW)"])
                            potencia_rango_e = float(row_r["Potencia Rango (kW)"])
                            max_mains_e = float(row_r["Mains Max (kW)"])
                            avg_mains_e = float(row_r["Mains Promedio (kW)"])
                            e_grid_e = float(row_r["Energía Red (kWh)"])
                            e_gen_e = float(row_r["Energía Gen (kWh)"])
                            t_grid_e = float(row_r["Tiempo Red (h)"])
                            t_gen_e = float(row_r["Tiempo Gen (h)"])
                            pct_grid_e = float(row_r["Disponibilidad Red (%)"])
                            pct_grid_time_e = (t_grid_e / (t_grid_e + t_gen_e) * 100) if (t_grid_e + t_gen_e) > 0 else 0.0
                            pct_gen_time_e = (t_gen_e / (t_grid_e + t_gen_e) * 100) if (t_grid_e + t_gen_e) > 0 else 0.0

                            e_solar_inv_e = (df_calc_e[pv_e].sum(axis=1) * df_calc_e['delta_h']).sum() if pv_e else 0.0
                            e_solar_ctrl_e = (df_calc_e[solar_cp_e].sum(axis=1) * df_calc_e['delta_h']).sum() if solar_cp_e else 0.0
                            total_solar_real_e = float(row_r["Solar Real (kWh)"]) 
                            total_solar_esperado_e = float(row_r["Solar Esperado (kWh)"])
                            diferencia_kwh_e = total_solar_esperado_e - total_solar_real_e
                            rendimiento_pct_e = float(row_r.get("Solar Real (kWh)", 0)) / total_solar_esperado_e * 100 if total_solar_esperado_e > 0 else 0.0
                            e_load_meter_e = float(row_r["Carga (Meter) (kWh)"])
                            
                            e_batt_disch_e, e_batt_chg_e, e_batt_chg_solar_e, e_batt_chg_mains_e = 0.0, 0.0, 0.0, 0.0

                            p_solar_inst_e = pd.Series([0.0]*len(df_calc_e), index=df_calc_e.index)
                            if pv_e: p_solar_inst_e = p_solar_inst_e + df_calc_e[pv_e].sum(axis=1).fillna(0)
                            if solar_cp_e: p_solar_inst_e = p_solar_inst_e + df_calc_e[solar_cp_e].sum(axis=1).fillna(0)
                            p_load_inst_e = df_calc_e[meter_e].sum(axis=1).fillna(0) if meter_e else (df_calc_e[load_e].sum(axis=1).fillna(0) if load_e else pd.Series([0.0]*len(df_calc_e), index=df_calc_e.index))

                            if batt_src_e:
                                total_batt_p_e = df_calc_e[batt_src_e].sum(axis=1)
                                e_batt_disch_e = (total_batt_p_e[total_batt_p_e < 0].abs() * df_calc_e.loc[total_batt_p_e < 0, 'delta_h']).sum()

                                mask_carga_e = total_batt_p_e > 0
                                if mask_carga_e.any():
                                    p_carga_inst_e = total_batt_p_e[mask_carga_e]
                                    p_solar_inst_carga_e = p_solar_inst_e[mask_carga_e]
                                    p_load_inst_carga_e = p_load_inst_e[mask_carga_e]
                                    delta_h_carga_e = df_calc_e.loc[mask_carga_e, 'delta_h']

                                    excedente_solar_e = (p_solar_inst_carga_e - p_load_inst_carga_e).clip(lower=0)
                                    p_carga_from_solar_e = np.minimum(p_carga_inst_e, excedente_solar_e)
                                    p_carga_from_mains_e = p_carga_inst_e - p_carga_from_solar_e

                                    e_batt_chg_solar_e = (p_carga_from_solar_e * delta_h_carga_e).sum()
                                    e_batt_chg_mains_e = (p_carga_from_mains_e * delta_h_carga_e).sum()

                                e_batt_chg_e = e_batt_chg_solar_e + e_batt_chg_mains_e
                                
                            e_mains_total_e = e_grid_e + e_gen_e
                            e_autoconsumo_e = float(row_r["Autoconsumo (kWh)"])
                            kpi_ahorro_e = float(row_r["Ahorro Red (%)"])
                            kpi_solar_cov_e = float(row_r["Cobertura Solar (%)"])
                            kpi_gen_dep_e = float(row_r["Uso Generador (%)"])
                            e_extra_grid_e = float(row_r["Extra de Red (kWh)"])
                            avg_soc_max_e = float(row_r["SoC Max (%)"])
                            avg_soc_min_e = float(row_r["SoC Min (%)"])
                            avg_dod_e = float(row_r["DoD (%)"])
                            uso_txt_e = str(row_r["Estado Batería"])
                            energy_cons_val_e = float(row_r["Site energy cons. (kWh/month)"])
                            avg_site_load_e = str(row_r["Avg. site load (W)"])
                            ahorro_esp_e = float(row_r["Ahorro Esperado"])
                            ahorro_real_e = float(row_r["Ahorro Real"])
                            deficit_e = float(row_r["Déficit Mensual"])
                            cumplimiento_e = float(row_r["Cumplimiento"])
                            load_cov_e = float(row_r["Load Coverage (Real)"])
                            start_date_e = row_r["Rango Inicio"]
                            end_date_e = row_r["Rango Fin"]

                            titulo_dif_e = "Energía Perdida" if diferencia_kwh_e > 0 else "Energía Excedente"
                            val_dif_str_e = f"{diferencia_kwh_e:.1f}" if diferencia_kwh_e > 0 else f"{abs(diferencia_kwh_e):.1f}"
                            color_dif_hex_e = '#ef4444' if diferencia_kwh_e > 0 else '#10b981'
                            color_pr_hex_e = '#10b981' if rendimiento_pct_e >= 100 else '#f59e0b'
                            color_dod_hex_e = '#10b981' if uso_txt_e == 'Ciclo Saludable' else '#ef4444'
                            texto_aud_dif_e = "Déficit Mensual" if deficit_e > 0 else "Superávit Mensual"
                            color_aud_dif_e = '#ef4444' if deficit_e > 0 else '#10b981'
                            color_aud_cump_e = '#10b981' if cumplimiento_e >= 95 else ('#f59e0b' if cumplimiento_e >= 85 else '#ef4444')

                            # --- GENERACIÓN DE GRÁFICAS PARA EL HTML ---
                            pie_e_html_e = ""
                            pie_t_html_e = ""
                            shadow_html_e = ""
                            clear_sky_html_e = ""
                            semanas_html_e = ""
                            perdidas_html_e = ""
                            efi_html_e = ""
                            modos_kpi_html_e = ""
                            energia_potencial_area_e = 0.0

                            # Gráficos de Pastel
                            labels_e = ['Red Comercial', 'Generador']
                            colors_pie = ['#2979FF', '#FF1744']
                            fig_pe = go.Figure(data=[go.Pie(labels=labels_e, values=[e_grid_e, e_gen_e], hole=.6, marker_colors=colors_pie)])
                            fig_pe.update_layout(height=250, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                            pie_e_html_e = fig_pe.to_html(full_html=False, include_plotlyjs='cdn')

                            fig_pt = go.Figure(data=[go.Pie(labels=labels_e, values=[t_grid_e, t_gen_e], hole=.6, marker_colors=colors_pie)])
                            fig_pt.update_layout(height=250, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                            pie_t_html_e = fig_pt.to_html(full_html=False, include_plotlyjs=False)

                            # Análisis de Sombras
                            if pv_e or solar_cp_e:
                                df_sh_e = df_exp.copy()
                                df_sh_e['Time_Only'] = df_sh_e['Timestamp'].apply(lambda d: d.replace(year=2000, month=1, day=1))
                                cols_grp_e = [c for c in (pv_e + solar_cp_e + batt_soc_e) if c in df_sh_e.columns]
                                df_sh_grp_e = df_sh_e.groupby('Time_Only')[cols_grp_e].mean().reset_index()
                                fig_sh_e = make_subplots(specs=[[{"secondary_y": True}]])
                                cs_e = px.colors.qualitative.Set1
                                idx_cs = 0
                                for col_sh in pv_e + solar_cp_e:
                                    if col_sh in df_sh_grp_e.columns and df_sh_grp_e[col_sh].max() > 0:
                                        y_s = df_sh_grp_e[col_sh].rolling(10, center=True, min_periods=1).mean()
                                        fig_sh_e.add_trace(go.Scatter(x=df_sh_grp_e['Time_Only'], y=y_s, mode='lines', name=col_sh, line_shape='spline', line=dict(color=cs_e[idx_cs % len(cs_e)], width=3)), secondary_y=False)
                                        idx_cs += 1
                                if batt_soc_e:
                                    soc_cols_ok = [c for c in batt_soc_e if c in df_sh_grp_e.columns]
                                    if soc_cols_ok:
                                        soc_m = df_sh_grp_e[soc_cols_ok].mean(axis=1).rolling(10, center=True, min_periods=1).mean()
                                        fig_sh_e.add_trace(go.Scatter(x=df_sh_grp_e['Time_Only'], y=soc_m, mode='lines', name='SoC Promedio (%)', line_shape='spline', line=dict(color='#00E676', width=2.5, dash='dot')), secondary_y=True)
                                fig_sh_e.update_layout(height=450, paper_bgcolor='#262730', plot_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.2), hovermode="x unified", title="Curva de Ajuste Spline (Sombra Estructural vs SoC)")
                                shadow_html_e = fig_sh_e.to_html(full_html=False, include_plotlyjs=False)

                            # Clear Sky y Baseline
                            df_sky_e = df_exp.copy()
                            df_sky_e['P_solar_total'] = 0.0
                            if pv_e: df_sky_e['P_solar_total'] += df_sky_e[pv_e].sum(axis=1).fillna(0)
                            if solar_cp_e: df_sky_e['P_solar_total'] += df_sky_e[solar_cp_e].sum(axis=1).fillna(0)
                            df_sky_e['Time_Only'] = df_sky_e['Timestamp'].apply(lambda d: d.replace(year=2000, month=1, day=1))
                            df_sky_e['Date_Str'] = df_sky_e['Timestamp'].dt.date.astype(str)
                            df_sky_e['Hour_Decimal'] = df_sky_e['Timestamp'].dt.hour + df_sky_e['Timestamp'].dt.minute/60.0
                            df_env_e = df_sky_e.groupby('Time_Only').agg(P_solar_total=('P_solar_total','max'), Hour_Decimal=('Hour_Decimal','first')).reset_index()
                            
                            fig_csky_e = go.Figure()
                            for ds_e in sorted(df_sky_e['Date_Str'].unique()):
                                df_d_e = df_sky_e[df_sky_e['Date_Str'] == ds_e]
                                if not df_d_e.empty and df_d_e['P_solar_total'].max() > 0.1:
                                    fig_csky_e.add_trace(go.Scatter(x=df_d_e['Time_Only'], y=df_d_e['P_solar_total'], mode='lines', line=dict(color='rgba(150,150,150,0.25)', width=1.5), showlegend=False, hoverinfo='skip'))
                            fig_csky_e.add_trace(go.Scatter(x=df_env_e['Time_Only'], y=df_env_e['P_solar_total'], mode='lines', name="Máximo Absoluto Real", line_shape='linear', line=dict(color='rgba(255,214,0,0.4)', width=2)))
                            
                            df_env_e['P_teorico'] = df_env_e['P_solar_total'].rolling(12, center=True, min_periods=1).mean()
                            umbral_e = df_env_e['P_solar_total'].max() * 0.02
                            df_env_e['P_teorico'] = np.where(df_env_e['P_teorico'] < umbral_e, 0, df_env_e['P_teorico'])
                            fig_csky_e.add_trace(go.Scatter(x=df_env_e['Time_Only'], y=df_env_e['P_teorico'], mode='lines', name="Perfil Esperado (Empírico)", line_shape='spline', line=dict(color='#FF1744', width=3.5, dash='dashdot')))

                            cols_consumo_e = meter_e if meter_e else load_e
                            if cols_consumo_e:
                                df_sky_e['P_consumo_total'] = df_sky_e[cols_consumo_e].sum(axis=1).fillna(0)
                                df_consumo_avg_e = df_sky_e.groupby('Time_Only')['P_consumo_total'].mean().reset_index()
                                window_consumo_e = max(3, len(df_consumo_avg_e) // 48)
                                df_consumo_avg_e['P_consumo_suave'] = df_consumo_avg_e['P_consumo_total'].rolling(window=window_consumo_e, center=True, min_periods=1).mean()
                                fig_csky_e.add_trace(go.Scatter(x=df_consumo_avg_e['Time_Only'], y=df_consumo_avg_e['P_consumo_suave'], mode='lines', name="Consumo Promedio (AC)", line_shape='spline', line=dict(color='#00E676', width=3, dash='dot')))
                                
                            df_bl_e = site_data_exp.get('baseline_matrix')
                            bl_valid_e = False
                            baseline_times_e = None
                            baseline_vals_e = None
                            month_name_e = ""
                            meses_exp = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
                            
                            if df_bl_e is not None and not df_exp.empty:
                                mode_month_e = df_sky_e['Timestamp'].dt.month.mode()[0]
                                midx_e = mode_month_e - 1
                                month_name_e = meses_exp[midx_e]
                                bl_vals_e = df_bl_e.iloc[midx_e, :].values.astype(float)
                                if np.sum(bl_vals_e) > 0.1:
                                    baseline_times_e = np.array([0.0] + [h + 0.5 for h in range(24)] + [23.999])
                                    baseline_vals_e = np.array([0.0] + list(bl_vals_e) + [0.0])
                                    bl_valid_e = True
                                    bl_times_plot_e = [pd.Timestamp(year=2000, month=1, day=1, hour=int(h), minute=int((h%1)*60)) for h in baseline_times_e]
                                    fig_csky_e.add_trace(go.Scatter(x=bl_times_plot_e, y=baseline_vals_e, mode='lines', name=f"Baseline Esperado ({month_name_e})", line=dict(color='yellow', width=3, dash='dash')))
                                    energia_potencial_area_e = float(np.sum(baseline_vals_e))

                            fig_csky_e.update_layout(height=500, paper_bgcolor='#262730', plot_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor='center'), hovermode="x unified", title="Potencial Solar Máximo vs Baseline")
                            clear_sky_html_e = fig_csky_e.to_html(full_html=False, include_plotlyjs=False)

                            # Análisis Semanal
                            df_wk_e = df_exp.copy()
                            df_wk_e['Date'] = df_wk_e['Timestamp'].dt.date.astype(str)
                            df_wk_e['Time_Only'] = df_wk_e['Timestamp'].apply(lambda d: d.replace(year=2000, month=1, day=1))
                            df_wk_e['Hour_Decimal'] = df_wk_e['Timestamp'].dt.hour + df_wk_e['Timestamp'].dt.minute/60.0
                            df_wk_e['YearWeek'] = df_wk_e['Timestamp'].dt.strftime('%Y - Semana %V')
                            df_wk_e['delta_h'] = df_wk_e['Hour_Decimal'].diff().fillna(0)
                            df_wk_e['P_Solar_Total'] = 0.0
                            if pv_e: df_wk_e['P_Solar_Total'] += df_wk_e[pv_e].sum(axis=1).fillna(0)
                            if solar_cp_e: df_wk_e['P_Solar_Total'] += df_wk_e[solar_cp_e].sum(axis=1).fillna(0)
                            df_wk_e['P_Solar_Suave'] = df_wk_e['P_Solar_Total'].rolling(5, center=True, min_periods=1).mean()
                            colors_wk = px.colors.qualitative.Plotly
                            
                            for wk_e in sorted(df_wk_e['YearWeek'].unique()):
                                df_w = df_wk_e[df_wk_e['YearWeek'] == wk_e].copy()
                                unique_days_e = sorted(df_w['Date'].unique())
                                fig_wk_tot = make_subplots(specs=[[{"secondary_y": False}]])
                                for ii_e, day_e in enumerate(unique_days_e):
                                    df_d = df_w[df_w['Date'] == day_e]
                                    c_e = colors_wk[ii_e % len(colors_wk)]
                                    y_s_e = df_d['P_Solar_Suave'].values
                                    if bl_valid_e and len(df_d) > 0:
                                        day_tf = df_d['Time_Only'].dt.hour + df_d['Time_Only'].dt.minute/60.0
                                        bl_i = np.interp(day_tf, baseline_times_e, baseline_vals_e)
                                        fig_wk_tot.add_trace(go.Scatter(x=df_d['Time_Only'], y=bl_i, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
                                        fig_wk_tot.add_trace(go.Scatter(x=df_d['Time_Only'], y=np.maximum(y_s_e, bl_i), mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(0,230,118,0.1)', showlegend=False, hoverinfo='skip'))
                                        fig_wk_tot.add_trace(go.Scatter(x=df_d['Time_Only'], y=bl_i, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
                                        fig_wk_tot.add_trace(go.Scatter(x=df_d['Time_Only'], y=np.minimum(y_s_e, bl_i), mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255,82,82,0.15)', showlegend=False, hoverinfo='skip'))
                                    fig_wk_tot.add_trace(go.Scatter(x=df_d['Time_Only'], y=y_s_e, mode='lines', name=day_e, line=dict(color=c_e, width=2.5)))
                                if bl_valid_e:
                                    bl_tp_e = [pd.Timestamp(year=2000, month=1, day=1, hour=int(h), minute=int((h%1)*60)) for h in baseline_times_e]
                                    fig_wk_tot.add_trace(go.Scatter(x=bl_tp_e, y=baseline_vals_e, mode='lines', name=f"Baseline ({month_name_e})", line=dict(color='yellow', width=3.5, dash='dash')))
                                fig_wk_tot.update_layout(title=f"Total Producción vs Baseline - {wk_e}", xaxis=dict(tickformat="%H:%M"), yaxis=dict(title="Potencia (kW)"), height=500, paper_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.2), hovermode="x unified")
                                semanas_html_e += fig_wk_tot.to_html(full_html=False, include_plotlyjs=False)

                                batt_src_wk_e = batt_bank_e if batt_bank_e else batt_e
                                cols_cons_wk_e = meter_e if meter_e else load_e
                                if batt_src_wk_e or cols_cons_wk_e:
                                    fig_bs_e = go.Figure()
                                    for ii_e2, day_e2 in enumerate(unique_days_e):
                                        df_d2 = df_w[df_w['Date'] == day_e2]
                                        c_e2 = colors_wk[ii_e2 % len(colors_wk)]
                                        if batt_src_wk_e:
                                            p_batt_e2 = df_d2[batt_src_wk_e].sum(axis=1).rolling(window=5, center=True, min_periods=1).mean()
                                            fig_bs_e.add_trace(go.Scatter(x=df_d2['Time_Only'], y=p_batt_e2, mode='lines', name=f"{day_e2} - Bat BMS", legendgroup=day_e2, line=dict(color=c_e2, width=2.5)))
                                        if (pv_e or solar_cp_e) and cols_cons_wk_e:
                                            p_sol_e2 = pd.Series(0.0, index=df_d2.index)
                                            if pv_e: p_sol_e2 = p_sol_e2 + df_d2[pv_e].sum(axis=1).fillna(0)
                                            if solar_cp_e: p_sol_e2 = p_sol_e2 + df_d2[solar_cp_e].sum(axis=1).fillna(0)
                                            p_ld_e2 = df_d2[cols_cons_wk_e].sum(axis=1).fillna(0)
                                            p_sb_e2 = (p_sol_e2 - p_ld_e2).clip(lower=0).rolling(window=5, center=True, min_periods=1).mean()
                                            fig_bs_e.add_trace(go.Scatter(x=df_d2['Time_Only'], y=p_sb_e2, mode='lines', name=f"{day_e2} - Solar->Bat", legendgroup=day_e2, line=dict(color=c_e2, width=2, dash='dash')))
                                    fig_bs_e.update_layout(title=f"Potencia Baterías (BMS) vs Solar Dedicado a Baterías - {wk_e}", xaxis=dict(tickformat="%H:%M"), yaxis=dict(title="Potencia (kW)"), height=500, paper_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.2), hovermode="x unified")
                                    semanas_html_e += fig_bs_e.to_html(full_html=False, include_plotlyjs=False)

                            # Eficiencia y Pérdidas
                            df_eff_e = df_exp[['Timestamp']].copy()
                            df_eff_e['delta_h'] = df_calc_e['delta_h']
                            df_eff_e['P_solar'] = 0.0
                            if pv_e: df_eff_e['P_solar'] += df_exp[pv_e].sum(axis=1).fillna(0)
                            if solar_cp_e: df_eff_e['P_solar'] += df_exp[solar_cp_e].sum(axis=1).fillna(0)
                            df_eff_e['P_mains'] = df_exp[mains_e].sum(axis=1).fillna(0) if mains_e else 0.0
                            df_eff_e['P_bat'] = df_exp[batt_src_e].sum(axis=1).fillna(0) if batt_src_e else 0.0
                            df_eff_e['P_load'] = df_exp[meter_e].sum(axis=1).fillna(0) if meter_e else (df_exp[load_e].sum(axis=1).fillna(0) if load_e else 0.0)
                            df_eff_e['P_perdidas'] = (df_eff_e['P_solar'] + df_eff_e['P_mains'] - df_eff_e['P_bat'] - df_eff_e['P_load']).clip(lower=0)
                            df_eff_e['P_perdidas_suave'] = df_eff_e['P_perdidas'].rolling(20, center=True, min_periods=1).mean()
                            df_eff_e['P_load_suave'] = df_eff_e['P_load'].rolling(20, center=True, min_periods=1).mean()
                            df_eff_e['P_in_total'] = df_eff_e['P_solar'] + df_eff_e['P_mains'] + np.where(df_eff_e['P_bat'] < -0.5, abs(df_eff_e['P_bat']), 0)
                            df_eff_e['Eficiencia'] = np.where(df_eff_e['P_in_total'] > 0.1, ((df_eff_e['P_in_total'] - df_eff_e['P_perdidas']) / df_eff_e['P_in_total']) * 100, np.nan)
                            df_eff_e['Eficiencia'] = df_eff_e['Eficiencia'].clip(upper=100, lower=0)
                            df_eff_e['Eficiencia_suave'] = df_eff_e['Eficiencia'].rolling(20, center=True, min_periods=1).mean()

                            conds_e = [
                                (df_eff_e['P_mains'] > 1.0),
                                (df_eff_e['P_mains'] <= 1.0) & (df_eff_e['P_solar'] < 0.1) & (df_eff_e['P_bat'] < -0.1),
                                (df_eff_e['P_mains'] <= 1.0) & (df_eff_e['P_solar'] <= df_eff_e['P_load']) & (df_eff_e['P_bat'] < -0.1),
                                (df_eff_e['P_mains'] <= 1.0) & (df_eff_e['P_solar'] >= df_eff_e['P_load'])
                            ]
                            choices_e = ['Modo Híbrido (Red/Gen)', 'Modo Batería', 'Modo Solar + Batería', 'Modo Solar']
                            df_eff_e['Modo'] = np.select(conds_e, choices_e, default='Apagado / Standby')
                            df_eff_e['E_perdidas'] = df_eff_e['P_perdidas'] * df_eff_e['delta_h']

                            first_day_e = df_eff_e['Timestamp'].dt.date.min()
                            df_eff_day_e = df_eff_e[df_eff_e['Timestamp'].dt.date == first_day_e].copy()
                            df_eff_day_e['Modo_Grp'] = (df_eff_day_e['Modo'] != df_eff_day_e['Modo'].shift()).cumsum()
                            bg_colors_chart_e = {'Modo Híbrido (Red/Gen)': 'rgba(41, 121, 255, 0.15)', 'Modo Solar': 'rgba(255, 214, 0, 0.15)', 'Modo Solar + Batería': 'rgba(255, 152, 0, 0.15)', 'Modo Batería': 'rgba(171, 71, 188, 0.15)'}

                            def apply_mode_shading_e(fig, df_day):
                                for m_name, m_color in bg_colors_chart_e.items():
                                    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=15, color=m_color.replace('0.15', '1')), name=m_name))
                                for g, chunk in df_day.groupby('Modo_Grp'):
                                    modo = chunk['Modo'].iloc[0]
                                    if modo in bg_colors_chart_e:
                                        fig.add_vrect(x0=chunk['Timestamp'].iloc[0], x1=chunk['Timestamp'].iloc[-1], fillcolor=bg_colors_chart_e[modo], opacity=1, layer="below", line_width=0)

                            fig_perd_e = make_subplots(specs=[[{"secondary_y": True}]])
                            fig_perd_e.add_trace(go.Scatter(x=df_eff_day_e['Timestamp'], y=df_eff_day_e['P_perdidas_suave'], mode='lines', name="Pérdidas (kW)", line=dict(color='white', width=2.5)), secondary_y=False)
                            fig_perd_e.add_trace(go.Scatter(x=df_eff_day_e['Timestamp'], y=df_eff_day_e['P_load_suave'], mode='lines', name="Carga AC (kW)", line=dict(color='#4FC3F7', width=1.5, dash='dash')), secondary_y=True)
                            apply_mode_shading_e(fig_perd_e, df_eff_day_e) 
                            fig_perd_e.update_layout(height=400, paper_bgcolor='#262730', plot_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.2), hovermode="x unified", title=f"Pérdidas vs Carga AC - {first_day_e}")
                            perdidas_html_e = fig_perd_e.to_html(full_html=False, include_plotlyjs=False)

                            fig_efi_e = make_subplots(specs=[[{"secondary_y": True}]])
                            fig_efi_e.add_trace(go.Scatter(x=df_eff_day_e['Timestamp'], y=df_eff_day_e['Eficiencia_suave'], mode='lines', name="Eficiencia (%)", line=dict(color='#00E676', width=2.5)), secondary_y=False)
                            fig_efi_e.add_trace(go.Scatter(x=df_eff_day_e['Timestamp'], y=df_eff_day_e['P_load_suave'], mode='lines', name="Carga AC (kW)", line=dict(color='#4FC3F7', width=1.5, dash='dash')), secondary_y=True)
                            apply_mode_shading_e(fig_efi_e, df_eff_day_e) 
                            fig_efi_e.update_layout(height=400, paper_bgcolor='#262730', plot_bgcolor='#262730', font=dict(color='#FAFAFA'), legend=dict(orientation="h", y=-0.2), hovermode="x unified", title=f"Eficiencia vs Carga AC - {first_day_e}")
                            efi_html_e = fig_efi_e.to_html(full_html=False, include_plotlyjs=False)

                            resumen_modos_e = df_eff_e.groupby('Modo').agg(Perdida_Media=('P_perdidas','mean'), Perdida_Total_kWh=('E_perdidas','sum'), Eficiencia_Media=('Eficiencia','mean')).reset_index()
                            modos_colores_e = {'Modo Híbrido (Red/Gen)': '#2979FF', 'Modo Solar': '#FFD600', 'Modo Solar + Batería': '#FF9F1C', 'Modo Batería': '#AB47BC'}
                            for _, mrow_e in resumen_modos_e.iterrows():
                                if mrow_e['Modo'] == 'Apagado / Standby': continue
                                ct_e = modos_colores_e.get(mrow_e['Modo'], 'white')
                                modos_kpi_html_e += f"""<div class="kpi-card" style="border-top: 3px solid {ct_e};"><h3 style="font-size:11px;">{mrow_e['Modo']}</h3><div class="value">{mrow_e['Perdida_Total_kWh']:.1f} kWh</div><p>Promedio: {mrow_e['Perdida_Media']:.2f} kW</p><p style="color:#10b981;font-weight:bold;">{mrow_e['Eficiencia_Media']:.1f}% Efi.</p></div>"""
                            
                            # --- ARMAR HTML CON TEMPLATE COMPLETO ---
                            html_site = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{nombre_exp} - Reporte</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        :root {{ --bg: #0b0f19; --surface: #171c28; --border: #2d3748; --text: #f8fafc; --text-muted: #94a3b8; --accent: #38bdf8; --success: #10b981; --danger: #ef4444; --warning: #f59e0b; --solar: #FFD600; --grid: #2979FF; --load: #00E676; --batt: #AB47BC; --gen: #FF1744; }}
        body {{ background-color: var(--bg); color: var(--text); font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 2rem; line-height: 1.5; }}
        .report-container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }}
        .header h1 {{ margin: 0; color: var(--accent); font-size: 32px; text-transform: uppercase; letter-spacing: 2px; }}
        .header p {{ color: var(--text-muted); margin-top: 0.5rem; font-size: 16px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
        .kpi-card {{ background: rgba(23,28,40,0.7); padding: 1.2rem; border-radius: 12px; border: 1px solid var(--border); text-align: center; }}
        .kpi-card h3 {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin: 0 0 0.5rem 0; letter-spacing: 1px; }}
        .kpi-card .value {{ font-size: 22px; font-weight: 800; color: var(--text); }}
        .kpi-card p {{ margin: 5px 0 0 0; font-size: 11px; color: var(--text-muted); }}
        .section {{ background: var(--surface); padding: 1.5rem; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 2rem; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }}
        .section-title {{ font-size: 18px; margin-top: 0; margin-bottom: 1.5rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; text-transform: uppercase; }}
        .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header"><h1>{nombre_exp} - Análisis Energético</h1><p>Fechas: <b>{start_date_e}</b> al <b>{end_date_e}</b></p></div>

        <div class="section"><h2 class="section-title">Estadísticas de Potencia Promedio/Máxima (kW)</h2>
            <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr);">
                <div class="kpi-card" style="border-top: 3px solid var(--load);"><h3>Carga Máxima</h3><div class="value">{max_load_e:.2f}</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--load);"><h3>Carga Promedio</h3><div class="value">{avg_load_e:.2f}</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--load);"><h3>Potencia Rango</h3><div class="value">{potencia_rango_e:.2f}</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--grid);"><h3>Red/Mains Máxima</h3><div class="value">{max_mains_e:.2f}</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--grid);"><h3>Red/Mains Promedio</h3><div class="value">{avg_mains_e:.2f}</div></div>
            </div>
        </div>

        <div class="section"><h2 class="section-title">Consumo de Energía y Tiempos</h2>
            <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr);">
                <div class="kpi-card" style="border-top: 3px solid var(--grid);"><h3>Energía Red</h3><div class="value">{e_grid_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--gen);"><h3>Energía Gen</h3><div class="value">{e_gen_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top: 3px solid var(--grid);"><h3>Tiempo Red</h3><div class="value">{t_grid_e:.1f} h</div><p>{pct_grid_time_e:.1f}%</p></div>
                <div class="kpi-card" style="border-top: 3px solid var(--gen);"><h3>Tiempo Gen</h3><div class="value">{t_gen_e:.1f} h</div><p>{pct_gen_time_e:.1f}%</p></div>
                <div class="kpi-card" style="border-top: 3px solid var(--success);"><h3>Disponibilidad Red</h3><div class="value">{pct_grid_e:.1f}%</div><p>Física (Sensor DI2)</p></div>
            </div>
            <div class="charts-row"><div>{pie_e_html_e}</div><div>{pie_t_html_e}</div></div>
        </div>

        <div class="section"><h2 class="section-title">Auditoría de Ahorro y Cumplimiento</h2>
            <h3 style="font-size:14px;color:var(--text-muted);margin-bottom:10px;">DATOS DE DISEÑO (SHEETS)</h3>
            <div class="kpi-grid" style="grid-template-columns: repeat(3, 1fr);">
                <div class="kpi-card" style="border-top:3px solid var(--text-muted);"><h3>Avg. site load</h3><div class="value">{avg_site_load_e} W</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--text-muted);"><h3>Site energy cons.</h3><div class="value">{energy_cons_val_e:.1f} kWh/mo</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--text-muted);"><h3>Load Coverage</h3><div class="value">{load_cov_e:.1f}%</div></div>
            </div>
            <h3 style="font-size:14px;color:var(--text-muted);margin-bottom:10px;">AUDITORÍA DE AHORRO (PROYECCIÓN A 30 DÍAS)</h3>
            <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr);">
                <div class="kpi-card" style="border-top:3px solid var(--grid);"><h3>Ahorro Esperado</h3><div class="value">{ahorro_esp_e:.1f} <span style="font-size:12px;">kWh/mo</span></div></div>
                <div class="kpi-card" style="border-top:3px solid var(--solar);"><h3>Ahorro Real</h3><div class="value">{ahorro_real_e:.1f} <span style="font-size:12px;">kWh/mo</span></div></div>
                <div class="kpi-card" style="border-top:3px solid {color_aud_dif_e};"><h3>{texto_aud_dif_e}</h3><div class="value" style="color:{color_aud_dif_e};">{abs(deficit_e):.1f} <span style="font-size:12px;">kWh/mo</span></div></div>
                <div class="kpi-card" style="border-top:3px solid {color_aud_cump_e};"><h3>Cumplimiento</h3><div class="value" style="color:{color_aud_cump_e};">{cumplimiento_e:.1f}%</div></div>
            </div>
        </div>

        <div class="section"><h2 class="section-title">Rendimiento Solar y Balance Energético</h2>
            <h3 style="font-size:14px;color:var(--text-muted);margin-bottom:10px;">PRODUCCIÓN FÍSICA</h3>
            <div class="kpi-grid" style="grid-template-columns: repeat(3, 1fr);">
                <div class="kpi-card" style="border-top:3px solid var(--solar);"><h3>Solar Inversor (Real)</h3><div class="value">{e_solar_inv_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--solar);"><h3>Solar Ctrl (Real)</h3><div class="value">{e_solar_ctrl_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--solar);background:rgba(255,214,0,0.1);"><h3>Solar Total (Real)</h3><div class="value" style="color:var(--solar);">{total_solar_real_e:.1f} kWh</div></div>
            </div>
            <h3 style="font-size:14px;color:var(--text-muted);margin-bottom:10px;">ANÁLISIS VS BASELINE</h3>
            <div class="kpi-grid" style="grid-template-columns: repeat(3, 1fr);">
                <div class="kpi-card" style="border-top:3px solid var(--text-muted);"><h3>Solar Esperado</h3><div class="value">{total_solar_esperado_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid {color_dif_hex_e};"><h3>{titulo_dif_e}</h3><div class="value" style="color:{color_dif_hex_e};">{val_dif_str_e} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid {color_pr_hex_e};"><h3>Performance Ratio (PR)</h3><div class="value" style="color:{color_pr_hex_e};">{rendimiento_pct_e:.1f}%</div></div>
            </div>
            <h3 style="font-size:14px;color:var(--text-muted);margin-bottom:10px;">INDICADORES GLOBALES</h3>
            <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr);">
                <div class="kpi-card" style="border-top:3px solid var(--load);"><h3>Carga Total (AC)</h3><div class="value">{e_load_meter_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--batt);"><h3>Energía Desc. Bat.</h3><div class="value">{e_batt_disch_e:.1f} kWh</div><p>Carga Total: {e_batt_chg_e:.1f} kWh</p></div>
                <div class="kpi-card" style="border-top:3px solid var(--text-muted); padding: 1rem 0.5rem;">
                    <h3>Origen Energía Para Carga de Baterías</h3>
                    <div style="display: flex; justify-content: space-around; margin-top: 8px;">
                        <div><div class="value" style="color: var(--solar); font-size: 18px;">{e_batt_chg_solar_e:.1f}</div><p>Solar</p></div>
                        <div><div class="value" style="color: var(--grid); font-size: 18px;">{e_batt_chg_mains_e:.1f}</div><p>Red</p></div>
                    </div>
                </div>
                <div class="kpi-card" style="border-top:3px solid var(--grid);"><h3>Mains Total</h3><div class="value">{e_mains_total_e:.1f} kWh</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--gen);"><h3>Autoconsumo Sist.</h3><div class="value">{e_autoconsumo_e:.1f} kWh</div></div>
            </div>
            <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:0;">
                <div class="kpi-card" style="border-top:3px solid var(--success);"><h3>% Ahorro Red</h3><div class="value">{kpi_ahorro_e:.1f}%</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--solar);"><h3>% Cobertura Solar</h3><div class="value">{kpi_solar_cov_e:.1f}%</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--danger);"><h3>% Uso Generador</h3><div class="value">{kpi_gen_dep_e:.1f}%</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--grid);"><h3>Extra de Red</h3><div class="value">{e_extra_grid_e:.1f} kWh</div></div>
            </div>
        </div>

        <div class="section"><h2 class="section-title">Salud del Almacenamiento (Baterías)</h2>
            <div class="kpi-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom:0;">
                <div class="kpi-card" style="border-top:3px solid var(--batt);"><h3>SoC Máx. Promedio</h3><div class="value">{avg_soc_max_e:.1f}%</div></div>
                <div class="kpi-card" style="border-top:3px solid var(--batt);"><h3>SoC Mín. Promedio</h3><div class="value">{avg_soc_min_e:.1f}%</div></div>
                <div class="kpi-card" style="border-top:3px solid {color_dod_hex_e};"><h3>Descarga (DoD)</h3><div class="value" style="color:{color_dod_hex_e};">{avg_dod_e:.1f}%</div><p>{uso_txt_e}</p></div>
            </div>
        </div>

        <div class="section"><h2 class="section-title">Análisis de Eficiencia y Pérdidas Dinámicas</h2>
            <div class="kpi-grid">{modos_kpi_html_e}</div>
            <div class="charts-row"><div>{perdidas_html_e}</div><div>{efi_html_e}</div></div>
        </div>

        <div class="section"><h2 class="section-title">Clear Sky y Potencial de Energía</h2>
            <p style="color:var(--text-muted);margin-bottom:2rem;">Energía total potencial del período analizado: <b>{energia_potencial_area_e:.1f} kWh</b></p>
            {clear_sky_html_e}
        </div>
        <div class="section"><h2 class="section-title">Análisis de Sombras (Curva de Ajuste Spline)</h2>{shadow_html_e}</div>
        <div class="section"><h2 class="section-title">Análisis de Generación Solar Semanal</h2>{semanas_html_e}</div>
    </div>
</body>
</html>"""

                            html_bytes_s = html_site.encode('utf-8')
                            media_s = MediaIoBaseUpload(io.BytesIO(html_bytes_s), mimetype='text/html', resumable=True)
                            file_meta_s = {'name': f"Reporte_{nombre_exp.replace(' ', '_')}.html", 'mimeType': 'text/html', 'parents': [lote_drive_folder]}
                            drive_file_s = drive_svc.files().create(body=file_meta_s, media_body=media_s, fields='id, webViewLink', supportsAllDrives=True).execute()
                            drive_svc.permissions().create(fileId=drive_file_s['id'], body={'type': 'anyone', 'role': 'reader'}, supportsAllDrives=True).execute()
                            links_por_sitio[nombre_exp] = drive_file_s.get('webViewLink', '')

                        df_export_lote = df_res.copy()
                        df_export_lote["Link Reporte HTML"] = df_export_lote["Sitio"].map(links_por_sitio).fillna("")

                        client_exp = gspread.authorize(creds_exp)
                        sh_exp = client_exp.open_by_url(lote_sheet_url)
                        ws_exp = sh_exp.worksheet(lote_sheet_tab)
                        existing_exp = ws_exp.get_all_values()
                        
                        if not existing_exp:
                            set_with_dataframe(ws_exp, df_export_lote)
                            st.success("Hoja inicializada con exportación exitosa.")
                        else:
                            next_row_exp = len(existing_exp) + 1
                            set_with_dataframe(ws_exp, df_export_lote, row=next_row_exp, include_column_header=False)
                            st.success(f"Filas añadidas desde la fila {next_row_exp}.")

                except Exception as e_exp:
                    st.error(f"Error durante la exportación: {e_exp}")
    else:
        st.info("Aún no hay resultados. Ve a la pestaña 'Cargar Sitios', carga los archivos y presiona 'GENERAR RESULTADOS'.")

    # =========================================================================
    # PESTAÑA 3: DATOS GLOBALES
    # =========================================================================
    with tab_globales:
        st.markdown("### Dashboard Global de Sitios")
        st.markdown("Conecta con el historial de reportes en Google Sheets para visualizar el estado actual de todos los sitios.")

        st.markdown("#### Configuración de Origen de Datos")
        lote_sheet_url = st.text_input(
            "URL del Google Sheet (Historial de Reportes):",
            value="https://docs.google.com/spreadsheets/d/1WmxMv9I6dMG8Hlf3M8xkV3pc4z2m0wtn-OO6A2MREkM/edit?gid=0#gid=0",
            key="glob_sheet_url"
        )
        lote_sheet_tab = st.text_input(
            "Nombre de la pestaña (Hoja):",
            value="Data Exporter",
            key="glob_sheet_tab"
        )

        btn_global = st.button("Actualizar Dashboard Global", type="primary", use_container_width=True)

        if btn_global:
            if not lote_sheet_url or not lote_sheet_tab:
                st.warning("Por favor, ingresa la URL del Sheet y el nombre de la pestaña.")
            else:
                try:
                    with st.spinner("Conectando con Google Sheets y descargando historial de reportes..."):
                        scopes_glob = [
                            "https://www.googleapis.com/auth/spreadsheets",
                            "https://www.googleapis.com/auth/drive"
                        ]
                        creds_glob = Credentials.from_service_account_info(
                            dict(st.secrets["gcp_service_account"]), scopes=scopes_glob
                        )
                        client_glob = gspread.authorize(creds_glob)

                        sh_glob = client_glob.open_by_url(lote_sheet_url)
                        ws_glob = sh_glob.worksheet(lote_sheet_tab)
                        records_glob = ws_glob.get_all_records()

                        if not records_glob:
                            st.warning("La hoja no contiene registros.")
                        else:
                            df_glob = pd.DataFrame(records_glob)

                            if 'Fecha Reporte' in df_glob.columns:
                                df_glob['Fecha Reporte'] = pd.to_datetime(df_glob['Fecha Reporte'], errors='coerce')
                                df_glob.sort_values('Fecha Reporte', ascending=False, inplace=True)
                            
                            if 'Sitio' in df_glob.columns:
                                df_glob = df_glob.drop_duplicates(subset=['Sitio'], keep='first')
                            
                            float_cols = ['Ahorro Red (%)', 'Cobertura Solar (%)', 'Cumplimiento', 'Ahorro Esperado (kWh)', 'Déficit Mensual', 'Carga Promedio (kW)', 'SoC Max (%)', 'DoD (%)', 'Load Coverage (Real)', 'Avg. site load (W)']
                            for fc in float_cols:
                                if fc in df_glob.columns:
                                    df_glob[fc] = pd.to_numeric(df_glob[fc].astype(str).str.replace('%', '').str.replace(',', '').str.strip(), errors='coerce').fillna(0.0)

                            st.session_state['df_global_dashboard'] = df_glob
                            st.rerun()

                except gspread.exceptions.WorksheetNotFound:
                    st.error(f"No se encontró una pestaña llamada '{lote_sheet_tab}'.")
                except Exception as e_glob:
                    import traceback
                    st.error(f"Error de conexión: {e_glob}")
                    st.code(traceback.format_exc())

        if 'df_global_dashboard' in st.session_state and st.session_state['df_global_dashboard'] is not None:
            df_dash = st.session_state['df_global_dashboard']



            st.markdown("---")

            n_sitios_dash = len(df_dash)
            
            # Cálculos de promedios seguros
            prom_ahorro_estimado = df_dash['Load Coverage (Real)'].mean() if 'Load Coverage (Real)' in df_dash.columns else 0.0
            prom_ahorro_real = df_dash['Ahorro Red (%)'].mean() if 'Ahorro Red (%)' in df_dash.columns else 0.0
            prom_cumplimiento = df_dash['Cumplimiento'].mean() if 'Cumplimiento' in df_dash.columns else (df_dash['Cumplimiento (%)'].mean() if 'Cumplimiento (%)' in df_dash.columns else 0.0)
            prom_dod = df_dash['DoD (%)'].mean() if 'DoD (%)' in df_dash.columns else 0.0

            # Renderizado en 5 columnas
            kpi_c1, kpi_c2, kpi_c3, kpi_c4, kpi_c5 = st.columns(5)
            with kpi_c1:
                st.metric("Sitios Activos", n_sitios_dash)
            with kpi_c2:
                st.metric("Prom. Ahorro Estimado", f"{prom_ahorro_estimado:.1f}%", help="Meta de diseño (Load Coverage)")
            with kpi_c3:
                st.metric("Prom. Ahorro Real", f"{prom_ahorro_real:.1f}%", help="Ahorro real logrado vs Red")
            with kpi_c4:
                st.metric("Prom. Cumplimiento", f"{prom_cumplimiento:.1f}%")
            with kpi_c5:
                st.metric("Promedio DoD", f"{prom_dod:.1f}%", help="Profundidad de Descarga global de baterías")
            
            
            #######################

            st.markdown("---")

            chart_c1, chart_c2 = st.columns(2)

            with chart_c1:
                st.markdown("##### Ahorro vs Cobertura Solar")
                if 'Ahorro Red (%)' in df_dash.columns and 'Cobertura Solar (%)' in df_dash.columns and 'Sitio' in df_dash.columns:
                    fig_g1 = px.scatter(
                        df_dash,
                        x='Cobertura Solar (%)',
                        y='Ahorro Red (%)',
                        hover_name='Sitio',
                        title="Ahorro Red vs Cobertura Solar",
                        trendline="ols",                   
                        trendline_scope="overall",         
                        trendline_color_override="rgba(150, 150, 150, 0.5)"   # <-- Gris opacado
                    )
                    fig_g1.update_layout(
                        paper_bgcolor='#FFFFFF',           
                        plot_bgcolor='#FFFFFF',            
                        font=dict(color='black'),                  # Texto negro puro
                        xaxis=dict(showgrid=False, color='black'), # Eje X negro
                        yaxis=dict(showgrid=True, gridcolor='black', color='black'), # Cuadrícula y Eje Y en negro
                        height=450
                    )
                    st.plotly_chart(fig_g1, use_container_width=True, theme=None)
                else:
                    st.warning("Faltan columnas necesarias para esta grafica.")

            with chart_c2:
                st.markdown("##### Cumplimiento vs Impacto")
                if 'Cumplimiento (%)' in df_dash.columns and 'Ahorro Esperado (kWh)' in df_dash.columns and 'Sitio' in df_dash.columns:
                    color_col = 'Déficit Mensual' if 'Déficit Mensual' in df_dash.columns else None

                    fig_g2 = px.scatter(
                        df_dash,
                        x='Ahorro Esperado (kWh)',
                        y='Cumplimiento (%)',
                        hover_name='Sitio',
                        color=color_col if color_col else None,
                        color_continuous_scale='RdYlGn_r' if color_col else None,
                        title="Cumplimiento vs Ahorro Esperado",
                        trendline="ols",                   
                        trendline_scope="overall",         
                        trendline_color_override="rgba(150, 150, 150, 0.5)"   # <-- Gris opacado
                    )
                    fig_g2.update_layout(
                        paper_bgcolor='#FFFFFF',
                        plot_bgcolor='#FFFFFF',
                        font=dict(color='black'),
                        xaxis=dict(showgrid=False, color='black', tickfont=dict(color='black'), title_font=dict(color='black')),
                        yaxis=dict(showgrid=True, gridcolor='black', color='black', tickfont=dict(color='black'), title_font=dict(color='black')),
                        height=450
                    )
                    st.plotly_chart(fig_g2, use_container_width=True, theme=None)
                else:
                    st.warning("Faltan columnas necesarias para esta grafica.")

###################################################

# --- NUEVA FILA DE GRÁFICAS ---
            st.markdown("---")
            chart_c3, chart_c4 = st.columns(2)

            with chart_c3:
                st.markdown("##### SoC Máximo vs Profundidad de Descarga (DoD)")
                if 'SoC Max (%)' in df_dash.columns and 'DoD (%)' in df_dash.columns and 'Sitio' in df_dash.columns:
                    
                    color_bat = 'Estado Batería' if 'Estado Batería' in df_dash.columns else None

                    fig_g3 = px.scatter(
                        df_dash,
                        x='SoC Max (%)',
                        y='DoD (%)',
                        hover_name='Sitio',
                        color=color_bat,
                        color_discrete_map={
                            "Ciclo Saludable": "#00E676", 
                            "Subutilizada": "#2979FF", 
                            "Ciclo Profundo": "#FF5252"
                        },
                        title="Salud del Banco: SoC Max vs DoD",
                        trendline="ols",                   
                        trendline_scope="overall",         
                        trendline_color_override="rgba(150, 150, 150, 0.5)"   # <-- Gris opacado
                    )
                    fig_g3.update_layout(
                        paper_bgcolor='#FFFFFF',
                        plot_bgcolor='#FFFFFF',
                        font=dict(color='black'),
                        xaxis=dict(showgrid=False, color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="SoC Máximo Promedio (%)"),
                        yaxis=dict(showgrid=True, gridcolor='black', color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="Profundidad de Descarga (DoD) (%)"),
                        height=450
                    )
                    st.plotly_chart(fig_g3, use_container_width=True, theme=None)
                else:
                    st.warning("Faltan las columnas de Batería (SoC Max / DoD) para esta gráfica.")

##########
            with chart_c4:
                st.markdown("##### Ahorro Red (%) vs Profundidad de Descarga (DoD)")
                if 'Ahorro Red (%)' in df_dash.columns and 'DoD (%)' in df_dash.columns and 'Sitio' in df_dash.columns:
                    
                    color_bat = 'Estado Batería' if 'Estado Batería' in df_dash.columns else None

                    fig_g4 = px.scatter(
                        df_dash,
                        x='Ahorro Red (%)',
                        y='DoD (%)',
                        hover_name='Sitio',
                        color=color_bat,
                        color_discrete_map={
                            "Ciclo Saludable": "#00E676", 
                            "Subutilizada": "#2979FF", 
                            "Ciclo Profundo": "#FF5252"
                        },
                        trendline="ols",                   # 1. Activa la línea de tendencia
                        trendline_scope="overall",         # 2. Una sola línea central para todos los puntos
                        trendline_color_override="rgba(150, 150, 150, 0.5)",  # 3. Color de la línea para que resalte
                        title="Impacto: Ahorro vs Uso de Batería"
                    )
                    fig_g4.update_layout(
                        paper_bgcolor='#FFFFFF',
                        plot_bgcolor='#FFFFFF',
                        font=dict(color='black'),
                        xaxis=dict(showgrid=False, color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="Ahorro Real vs Red (%)"),
                        yaxis=dict(showgrid=True, gridcolor='black', color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="Profundidad de Descarga (DoD) (%)"),
                        height=450
                    )
                    st.plotly_chart(fig_g4, use_container_width=True, theme=None)
                else:
                    st.warning("Faltan las columnas exactas (Ahorro Red (%) / DoD (%)) para esta gráfica.")

            ##################################
            
#####################################################
# --- SECCIÓN DE CORRELACIÓN DISEÑO VS REAL ---

#####################################################
            # --- SECCIÓN DE CORRELACIÓN DISEÑO VS REAL ---
            
            st.markdown("##### Correlación: Carga de Diseño vs Carga Real")
            
            if 'Avg. site load (W)' in df_dash.columns and 'Carga Promedio (kW)' in df_dash.columns and 'Sitio' in df_dash.columns:
                
                df_dash['Carga Diseño (kW)'] = df_dash['Avg. site load (W)'] / 1000.0
                
                # 1. Crear el gráfico con línea de tendencia en ROJO
                fig_g5 = px.scatter(
                    df_dash,
                    x='Carga Diseño (kW)',
                    y='Carga Promedio (kW)',
                    hover_name='Sitio',
                    title="Carga Teórica vs Carga Real Consumida",
                    trendline="ols",                   
                    trendline_scope="overall",         
                    trendline_color_override="red"  # <-- Línea de tendencia en ROJO
                )
                
                max_val = max(df_dash['Carga Diseño (kW)'].max(), df_dash['Carga Promedio (kW)'].max())
                if max_val == 0: max_val = 1 
                
                # 2. Agregar la línea de referencia ideal (1:1) en AZUL
                fig_g5.add_shape(
                    type="line", 
                    line=dict(dash='dash', color="blue", width=2), # <-- Línea 1:1 en AZUL (antes estaba blanca)
                    x0=0, y0=0, x1=max_val, y1=max_val
                )
                
                # 3. Anotación de la línea ideal también en AZUL
                fig_g5.add_annotation(
                    x=max_val*0.85, 
                    y=max_val*0.85, 
                    text="Ideal 1:1 (Real = Diseño)", 
                    showarrow=False, 
                    yshift=15, 
                    font=dict(color="blue", size=12) # <-- Texto en AZUL (antes estaba blanco)
                )

                # 4. Layout 100% blanco y negro
                fig_g5.update_layout(
                    paper_bgcolor='#FFFFFF',
                    plot_bgcolor='#FFFFFF',
                    font=dict(color='black'),
                    xaxis=dict(showgrid=False, color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="Carga de Diseño (kW)"),
                    yaxis=dict(showgrid=True, gridcolor='black', color='black', tickfont=dict(color='black'), title_font=dict(color='black'), title="Carga Real Promedio (kW)"),
                    height=450
                )
                
                # 5. Desactivar tema de Streamlit
                st.plotly_chart(fig_g5, use_container_width=True, theme=None)
            else:
                st.warning("Faltan las columnas de carga (Avg. site load (W) / Carga Promedio (kW)) para generar esta gráfica.")


#####################################################
            # --- OPCIÓN 3: DUMBBELL PLOT (RANGOS) ---
            
            st.markdown("##### Brecha de Diseño (Dumbbell Plot)")
            
            if 'Avg. site load (W)' in df_dash.columns and 'Carga Promedio (kW)' in df_dash.columns and 'Sitio' in df_dash.columns:
                
                df_dash['Carga Diseño (kW)'] = df_dash['Avg. site load (W)'] / 1000.0
                
                fig_g5 = go.Figure()
                
                # Dibujar las líneas conectando ambos puntos (en gris oscuro/negro para que resalte en fondo blanco)
                for i, row in df_dash.iterrows():
                    fig_g5.add_trace(go.Scatter(
                        x=[row['Sitio'], row['Sitio']],
                        y=[row['Carga Diseño (kW)'], row['Carga Promedio (kW)']],
                        mode='lines', line=dict(color='#333333', width=2), showlegend=False, hoverinfo='skip'
                    ))

                # Puntos de Diseño
                fig_g5.add_trace(go.Scatter(
                    x=df_dash['Sitio'], y=df_dash['Carga Diseño (kW)'],
                    mode='markers', name='Diseño',
                    # Se agregó una línea negra alrededor del punto amarillo para que no se pierda en el blanco
                    marker=dict(color='#FFD600', size=10, symbol='circle', line=dict(color='black', width=1)) 
                ))
                
                # Puntos Reales
                fig_g5.add_trace(go.Scatter(
                    x=df_dash['Sitio'], y=df_dash['Carga Promedio (kW)'],
                    mode='markers', name='Real',
                    marker=dict(color='#00E676', size=10, symbol='diamond', line=dict(color='black', width=1))
                ))

                # Actualización de layout para fondo blanco y letras negras absolutas
                fig_g5.update_layout(
                    title=dict(text="Brecha entre Expectativa (Diseño) y Realidad", font=dict(color='black')),
                    paper_bgcolor='#FFFFFF',
                    plot_bgcolor='#FFFFFF',
                    font=dict(color='black'),
                    xaxis=dict(showgrid=False, color='black', tickangle=-45, tickfont=dict(color='black'), title_font=dict(color='black')),
                    yaxis=dict(showgrid=True, gridcolor='black', color='black', title="Potencia (kW)", tickfont=dict(color='black'), title_font=dict(color='black')),
                    legend=dict(orientation="h", y=1.1, font=dict(color='black')),
                    hovermode='x unified',
                    hoverlabel=dict(font=dict(color='black'), bgcolor='#FFFFFF'),
                    height=450
                )
                
                # Se desactiva el tema de Streamlit para proteger los colores
                st.plotly_chart(fig_g5, use_container_width=True, theme=None)
            else:
                st.warning("Faltan las columnas de carga para generar esta gráfica.")

#####################################################


            ##################################

        
            st.markdown("---")
            st.markdown("##### Tabla de Datos (Reporte mas reciente por sitio)")
            st.dataframe(df_dash, use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------
# PESTAÑA 4: REGISTRO HISTÓRICO
# -----------------------------------------------------------------------
with tab_historico:
    st.markdown("### Registro Histórico por Sitio")
    hist_sheet_url = st.text_input("URL del Google Sheet:", value="https://docs.google.com/spreadsheets/d/1WmxMv9I6dMG8Hlf3M8xkV3pc4z2m0wtn-OO6A2MREkM/edit?gid=0#gid=0", key="hist_sheet_url")
    hist_sheet_tab = st.text_input("Nombre de la pestaña:", value="Data Exporter", key="hist_sheet_tab")

    if st.button("Cargar Historial", type="primary"):
        if not hist_sheet_url or not hist_sheet_tab:
            st.warning("Completa la URL y la pestaña.")
        else:
            try:
                with st.spinner("Descargando historial..."):
                    scopes_hist = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                    creds_hist = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes_hist)
                    client_hist = gspread.authorize(creds_hist)
                    ws_hist = client_hist.open_by_url(hist_sheet_url).worksheet(hist_sheet_tab)
                    records_hist = ws_hist.get_all_records()

                    if records_hist:
                        df_hist = pd.DataFrame(records_hist)
                        if 'Fecha Reporte' in df_hist.columns:
                            df_hist['Fecha Reporte'] = pd.to_datetime(df_hist['Fecha Reporte'], errors='coerce')
                            df_hist.sort_values('Fecha Reporte', ascending=True, inplace=True)
                        
                        # Limpieza para que las gráficas del historial no fallen
                        columnas_numericas_hist = [
                            'Carga Promedio (kW)', 'Solar Real (kWh)', 'Ahorro Red (%)', 
                            'Cobertura Solar (%)', 'Ahorro Real (kWh)', 'Cumplimiento (%)'
                        ]
                        for col in columnas_numericas_hist:
                            if col in df_hist.columns:
                                df_hist[col] = pd.to_numeric(df_hist[col].astype(str).str.replace('%', '').str.replace(',', '').str.strip(), errors='coerce').fillna(0.0)

                        st.session_state['df_historico_full'] = df_hist
                        st.rerun()
            except Exception as e_hist:
                st.error(f"Error de conexión: {e_hist}")

    if 'df_historico_full' in st.session_state and st.session_state['df_historico_full'] is not None:
        df_hist_full = st.session_state['df_historico_full']
        if 'Sitio' in df_hist_full.columns:
            sitios_disponibles = sorted(df_hist_full['Sitio'].dropna().unique().tolist())
            sitio_sel = st.selectbox("Selecciona un sitio:", options=sitios_disponibles, key="hist_sitio_sel")
            df_sitio = df_hist_full[df_hist_full['Sitio'] == sitio_sel].copy()

            if not df_sitio.empty:
                x_col = 'Fecha Reporte' if 'Fecha Reporte' in df_sitio.columns else None
                
                # Gráfica Principal
                metrica = 'Cumplimiento (%)'
                if metrica in df_sitio.columns:
                    fig_h = go.Figure(go.Scatter(x=df_sitio[x_col], y=df_sitio[metrica], mode='lines+markers', name=metrica))
                    fig_h.update_layout(title=metrica, paper_bgcolor='#262730', font=dict(color='#FAFAFA'))
                    st.plotly_chart(fig_h, use_container_width=True)

                st.markdown("---")

                n_reportes = len(df_sitio)
                fecha_min = df_sitio['Fecha Reporte'].min() if 'Fecha Reporte' in df_sitio.columns else "N/A"
                fecha_max = df_sitio['Fecha Reporte'].max() if 'Fecha Reporte' in df_sitio.columns else "N/A"

                info_c1, info_c2, info_c3 = st.columns(3)
                info_c1.metric("Reportes encontrados", n_reportes)
                info_c2.metric("Primer reporte", str(fecha_min)[:10] if fecha_min != "N/A" else "N/A")
                info_c3.metric("Último reporte", str(fecha_max)[:10] if fecha_max != "N/A" else "N/A")

                st.markdown("---")

                # LISTA EXACTA PARA LAS GRÁFICAS INFERIORES
                metricas_plot = [
                    ('Carga Promedio (kW)',  '#00E676', 'kW'),
                    ('Solar Real (kWh)',      '#FFD600', 'kWh'),
                    ('Ahorro Red (%)',        '#2979FF', '%'),
                    ('Cobertura Solar (%)',   '#FF9F1C', '%'),
                    ('Ahorro Real (kWh)',     '#00B4D8', 'kWh'),
                    ('Cumplimiento (%)',      '#AB47BC', '%'),
                ]

                for m_nombre, color, unidad in metricas_plot:
                    if m_nombre not in df_sitio.columns:
                        st.warning(f"Columna '{m_nombre}' no encontrada en el historial.")
                        continue

                    df_plot = df_sitio[[x_col, m_nombre]].dropna() if x_col else df_sitio[[m_nombre]].dropna()

                    if df_plot.empty:
                        st.info(f"Sin datos numéricos para graficar: {m_nombre}")
                        continue

                    fig_h = go.Figure()
                    fig_h.add_trace(go.Scatter(
                        x=df_plot[x_col] if x_col else list(range(len(df_plot))),
                        y=df_plot[m_nombre],
                        mode='lines+markers',
                        name=m_nombre,
                        line=dict(color=color, width=2.5),
                        marker=dict(size=8, color=color),
                        hovertemplate=f'<b>{m_nombre}</b><br>Fecha: %{{x}}<br>Valor: %{{y:.2f}} {unidad}<extra></extra>'
                    ))

                    fig_h.update_layout(
                        title=dict(text=m_nombre, font=dict(size=15, color='#FAFAFA')),
                        paper_bgcolor='#262730',
                        plot_bgcolor='#262730',
                        font=dict(color='#FAFAFA'),
                        height=300,
                        margin=dict(l=10, r=10, t=45, b=10),
                        xaxis=dict(showgrid=False, color='#FAFAFA', tickformat='%Y-%m-%d' if x_col else '', tickangle=-30),
                        yaxis=dict(showgrid=True, gridcolor='#444444', color='#FAFAFA', title=unidad),
                        hovermode='x unified',
                        hoverlabel=dict(font=dict(color='#FAFAFA')),
                        showlegend=False
                    )

                    with st.container(border=True):
                        st.plotly_chart(fig_h, use_container_width=True, key=f"hist_{sitio_sel}_{m_nombre}")
