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

# ---------------- Búsqueda manual ----------------
st.subheader("Búsqueda manual")
input_str = st.text_input("Ingresa números de artículo separados por comas (ej. 123,456,789)")

if input_str:
    numeros = [x.strip() for x in input_str.split(",") if x.strip()]
    encontrados, faltantes = [], []

    for n in numeros:
        m = df[df["NUMERO DE ARTICULO"] == n]
        (encontrados if not m.empty else faltantes).append(m if not m.empty else n)

    if encontrados:
        st.success("Resultados encontrados:")
        st.dataframe(pd.concat(encontrados), use_container_width=True)

    if faltantes:
        st.warning("No están en la lista: " + ", ".join(faltantes))
        st.info("Puedes agregarlos aquí mismo:")

        for n in faltantes:
            with st.expander(f"Agregar {n}", expanded=False):
                desc = st.text_input(f"Descripción para {n}", key=f"desc_{n}")
                precio = st.text_input(f"Precio para {n}", key=f"precio_{n}")
                divisa = st.selectbox(f"Divisa para {n}", ["MXN", "USD"], key=f"divisa_{n}")
                if st.button(f"Confirmar agregar/actualizar {n}", key=f"ok_{n}"):
                    try:
                        upsert_articulo(n, desc, precio, divisa)
                        st.success(f"{n} guardado correctamente.")
                    except Exception as e:
                        st.error(f"Error guardando {n}: {e}")

# ---------------- Carga masiva ----------------
st.divider()
st.subheader("Carga masiva (Excel/CSV) opcional")

archivo = st.file_uploader(
    "Sube un archivo con al menos la columna: NUMERO DE ARTICULO",
    type=["xlsx", "xls", "csv"]
)

if archivo is not None:
    try:
        # Leer archivo según formato
        if archivo.name.lower().endswith(".csv"):
            df_up = pd.read_csv(archivo, dtype=str)
        else:
            df_up = pd.read_excel(archivo, dtype=str)

        # Normalizar nombres de columnas
        df_up.columns = [c.strip().upper() for c in df_up.columns]

        # Verificar si está la columna principal
        if "NUMERO DE ARTICULO" not in df_up.columns:
            st.error("El archivo debe contener la columna: NUMERO DE ARTICULO")
        else:
            procesadas, errores = 0, []

            for _, row in df_up.iterrows():
                try:
                    numero_articulo = row["NUMERO DE ARTICULO"].strip()

                    # Valores opcionales
                    descripcion = row.get("DESCRIPCION DEL ARTICULO", "").strip()
                    precio = row.get("PRECIOS MAYO", "").strip()
                    divisa = row.get("DIVISA", "").strip()

                    # Llamar función de inserción/actualización
                    upsert_articulo(numero_articulo, descripcion, precio, divisa)
                    procesadas += 1

                except Exception as e:
                    errores.append(f"{row.get('NUMERO DE ARTICULO','?')}: {e}")

            # Mensajes de resultado
            st.success(f"Carga completada. Filas procesadas: {procesadas}")
            if errores:
                st.warning("Algunas filas tuvieron errores:")
                for e in errores:
                    st.write("- ", e)

    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")

st.divider()
st.caption("IRSADOSA · Streamlit")


