import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ---------------- Configuración de página ----------------
st.set_page_config(
    page_title="Tienda IRSADOSA",
    page_icon="assets/logo.png",
    layout="centered"
)

st.markdown(
    """
    <h1 style="text-align:center;">
      Consulta de precios <span style="color:red;">IR</span><span style="color:blue;">SADOSA</span>
    </h1>
    """,
    unsafe_allow_html=True,
)

# ---------------- Conexión a Google Sheets ----------------
@st.cache_resource
def conectar_hoja():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(st.secrets["sheets"]["SHEET_ID"])
    ws = sh.worksheet(st.secrets["sheets"]["SHEET_NAME"])
    return ws

ws = conectar_hoja()

# ---------------- Utilidades de datos ----------------
COLUMNAS = ["NUMERO DE ARTICULO", "DESCRIPCION DEL ARTICULO", "PRECIOS MAYO", "DIVISA"]

@st.cache_data(ttl=60)
def cargar_datos():
    registros = ws.get_all_records()
    df = pd.DataFrame(registros, dtype=str)
    if df.empty:
        df = pd.DataFrame(columns=COLUMNAS)
    for c in COLUMNAS:  # asegura que siempre estén las columnas
        if c not in df.columns:
            df[c] = ""
    return df

def upsert_articulo(num, desc, precio, divisa):
    """Actualiza si existe (col A), si no existe agrega al final."""
    num = str(num).strip()
    desc = str(desc).strip()
    divisa = str(divisa).strip().upper()

    # Precio: soporta coma o punto
    precio_str = str(precio).replace(",", ".").strip()
    try:
        precio_val = float(precio_str)
    except ValueError:
        raise ValueError(f"Precio inválido: {precio}")

    try:
        cell = ws.find(num)
        if cell and cell.col == 1:
            ws.update_cell(cell.row, 2, desc)
            ws.update_cell(cell.row, 3, precio_val)
            ws.update_cell(cell.row, 4, divisa)
        else:
            ws.append_row([num, desc, precio_val, divisa], value_input_option="USER_ENTERED")
    except gspread.exceptions.CellNotFound:
        ws.append_row([num, desc, precio_val, divisa], value_input_option="USER_ENTERED")

    cargar_datos.clear()  # refresca caché

df = cargar_datos()

# ---------------- Búsqueda manual o archivo ----------------
st.subheader("Buscar artículos")

# --- OPCIÓN 1: Input manual ---
input_str = st.text_input("Ingresa los números de artículo separados por comas (ej. 123,456,789):")

# --- OPCIÓN 2: Subir archivo ---
archivo_subido = st.file_uploader("O sube un archivo Excel con los números", type=["xlsx"])

numeros = []

if input_str:
    numeros = [x.strip() for x in input_str.split(",")]

elif archivo_subido:
    try:
        df_upload = pd.read_excel(archivo_subido, dtype=str)
        if "NUMERO DE ARTICULO" in df_upload.columns:
            numeros = df_upload["NUMERO DE ARTICULO"].dropna().tolist()
        else:
            st.error("❌ El archivo debe tener una columna llamada 'NUMERO DE ARTICULO'")
    except Exception as e:
        st.error(f"⚠️ Error al leer el archivo: {e}")

# 🔹 Inicializamos listas siempre (para evitar NameError)
resultados = []
no_encontrados = []

# Procesar números si hay alguno
if numeros:
    for num in numeros:
        match = df[df["NUMERO DE ARTICULO"] == num]
        if not match.empty:
            resultados.append(match)
        else:
            no_encontrados.append(num)

# --- Mostrar resultados encontrados ---
if resultados:
    st.subheader("Resultados encontrados:")
    df_resultados = pd.concat(resultados)
    st.dataframe(df_resultados)

    # --- OPCIÓN PARA ELIMINAR CON BOTÓN ---
    st.write("### Eliminar artículos:")

    for idx, row in df_resultados.iterrows():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"{row['NUMERO DE ARTICULO']} - {row['DESCRIPCION DEL ARTICULO']}")
        with col2:
            if st.button(f"🗑 Eliminar", key=f"del_{idx}"):
               num_str = str(row["NUMERO DE ARTICULO"]).strip()
               st.warning(f"¿Seguro que deseas eliminar {num_str}?")
               if st.button(f"✅ Confirmar {num_str}", key=f"confirm_{idx}"):
                   try:
                       cell = ws.find(num_str)
                       if cell:
                           ws.delete_rows(cell.row)
                           cargar_datos.clear()
                           st.success(f"✅ Artículo {num_str} eliminado correctamente.")
                           st.rerun()
                       else:
                           st.error(f"❌ No se encontró el artículo {num_str} en Google Sheets.")
                   except Exception as e:
                       st.error(f"⚠️ Error al eliminar {num_str}: {e}")

# --- Mostrar no encontrados ---
if no_encontrados:
    st.subheader("Artículos no encontrados")
    st.write(", ".join(map(str, no_encontrados)))

    for nuevo in no_encontrados:
        with st.expander(f"Agregar {nuevo}", expanded=False):
            descripcion = st.text_input(f"Descripción para {nuevo}", key=f"desc_{nuevo}")
            precio = st.text_input(f"Precio para {nuevo}", key=f"precio_{nuevo}", help="Acepta coma o punto.")
            divisa = st.selectbox(f"Divisa para {nuevo}", ["MXN", "USD"], key=f"div_{nuevo}")

            if st.button(f"Confirmar agregar {nuevo}", key=f"add_{nuevo}"):
                if not descripcion or not precio:
                    st.error("Completa descripción y precio.")
                else:
                    try:
                        add_or_update_articulo(nuevo, descripcion, precio, divisa)
                        st.success(f"✅ Artículo {nuevo} agregado/actualizado correctamente.")
                        st.rerun()
                    except ValueError as ve:
                        st.error(f"Precio inválido: {ve}")
                    except Exception as e:
                        st.error(f"⚠️ Error al guardar {nuevo}: {e}")

                    # Agregar a Google Sheets
                    try:
                        ws.append_row([
                            str(nuevo),
                            descripcion,
                            float_precio
                        ])
                        cargar_datos.clear()
                        st.success(f"✅ Artículo {nuevo} agregado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Error al agregar: {e}")

st.divider()
st.caption("IRSADOSA · Streamlit")

