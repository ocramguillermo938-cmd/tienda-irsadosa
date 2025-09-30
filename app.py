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

@st.cache_data(ttl=5)
def cargar_datos():
    registros = ws.get_all_records()
    df = pd.DataFrame(registros)  # 👈 ya no fuerzas strings
    if df.empty:
        df = pd.DataFrame(columns=COLUMNAS)
    for c in COLUMNAS:
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

if st.button("🔄 Refrescar datos"):
    cargar_datos.clear()  # limpia la caché
    st.rerun()            # vuelve a correr la app

df = cargar_datos()

# Normaliza precios como float
if not df.empty:
    df["PRECIOS MAYO"] = pd.to_numeric(df["PRECIOS MAYO"], errors="coerce")

# ---------------- Búsqueda manual o archivo ----------------
st.subheader("Buscar artículos")

# --- OPCIÓN 1: Input manual ---
input_str = st.text_input("Ingresa los números de artículo separados por comas (ej. 38459582,92692284):")

# --- OPCIÓN 2: Subir archivo ---
archivo_subido = st.file_uploader("Sube un archivo Excel con los números debajo del titulo NUMERO DE ARTICULO", type=["xlsx"])

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

    # 🔎 Buscar duplicados por NUMERO DE ARTICULO
    duplicados = df_resultados[df_resultados.duplicated("NUMERO DE ARTICULO", keep=False)]

    if not duplicados.empty:
        st.warning("⚠️ Se encontraron artículos repetidos:")
        st.dataframe(duplicados)

        for idx, row in duplicados.iterrows():
            num_str = str(row["NUMERO DE ARTICULO"]).strip()
            desc = row["DESCRIPCION DEL ARTICULO"]

            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"{num_str} - {desc}")
            with col2:
                if st.button(f"🗑 Eliminar duplicado", key=f"del_dup_{idx}"):
                    try:
                        # 🔹 Eliminar fila directamente en Google Sheets
                        cell = ws.find(num_str)
                        if cell:
                            ws.delete_rows(cell.row)
                            cargar_datos.clear()
                            st.success(f"✅ Duplicado de {num_str} eliminado correctamente.")
                            st.rerun()
                        else:
                            st.error(f"❌ No se encontró {num_str} en la hoja.")
                    except Exception as e:
                        st.error(f"⚠️ Error al eliminar {num_str}: {e}")
    else:
        st.info("No hay duplicados en los resultados.")


# --- Mostrar no encontrados ---
# ---------------- Artículos no encontrados (expander + form + autofocus) ----------------
if no_encontrados:
    st.subheader("Artículos no encontrados:")
    st.write(", ".join(no_encontrados))

    for nuevo in no_encontrados:
        chk_key = f"chk_add_{nuevo}"
        exp_key = f"exp_add_{nuevo}"
        form_key = f"form_add_{nuevo}"

        # Estado inicial para el expander (solo control interno, no ligado al checkbox)
        if exp_key not in st.session_state:
            st.session_state[exp_key] = False

        # Checkbox para decidir si se abre el expander
        chk_val = st.checkbox(f" ➕ Agregar artículo {nuevo}?", key=chk_key)
        if chk_val:
            st.session_state[exp_key] = True

        # Expander controlado por session_state
        with st.expander(f"Agregar {nuevo}", expanded=st.session_state[exp_key]):
            # Hack para autofocus en el campo de descripción
            st.markdown(
                f"""
                <script>
                setTimeout(function(){{
                    var el = window.parent.document.querySelector('input[id="desc_{nuevo}"]');
                    if(el) el.focus();
                }}, 300);
                </script>
                """,
                unsafe_allow_html=True
            )

            with st.form(key=form_key):
                descripcion = st.text_input("Descripción", key=f"desc_{nuevo}")
                precio = st.text_input("Precio", key=f"precio_{nuevo}")
                divisa = st.selectbox("Divisa", ["USD", "MXN", "EUR"], key=f"divisa_{nuevo}")
                submitted = st.form_submit_button("Confirmar agregar")

                if submitted:
                    try:
                        precio_val = float(str(precio).replace(",", ".").strip())
                    except Exception:
                        st.error(f"❌ Precio inválido para {nuevo}: '{precio}'")
                        precio_val = None

                    if precio_val is not None:
                        try:
                            upsert_articulo(nuevo, descripcion, precio_val, divisa)
                            st.success(f"✅ Artículo {nuevo} agregado correctamente.")

                            # Reset de estados sin tocar widgets existentes
                            st.session_state[exp_key] = False
                            st.rerun()


                        except Exception as e:
                            st.error(f"⚠️ Error al guardar {nuevo}: {e}")



st.divider()
st.caption("IRSADOSA · Streamlit")

