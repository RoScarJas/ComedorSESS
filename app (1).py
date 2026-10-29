import streamlit as st
import pandas as pd
from datetime import date, datetime
import io
import time
import json
import os
from google import genai

# --- CONFIGURACIÓN DE APIS Y SECRETOS ---
# La API Key se obtiene de manera estrictamente interna e invisible para el usuario
GEMINI_API_KEY_DEFAULT = ''
if 'GEMINI_API_KEY' in st.secrets:
    GEMINI_API_KEY_DEFAULT = st.secrets['GEMINI_API_KEY']
elif os.environ.get('GEMINI_API_KEY'):
    GEMINI_API_KEY_DEFAULT = os.environ.get('GEMINI_API_KEY')

# --- SISTEMA DE PERSISTENCIA DE DATOS LOCAL ---
DB_FILE = 'data_comedor.json'

def cargar_datos():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                datos = json.load(f)
                if 'estudiantes_bloqueados' in datos:
                    datos['estudiantes_bloqueados'] = set(datos['estudiantes_bloqueados'])
                return datos
        except Exception as e:
            st.error(f'Error al cargar la base de datos: {e}')
    return {}

def guardar_datos():
    try:
        datos_a_guardar = {
            'estudiantes': st.session_state.estudiantes,
            'productos': st.session_state.productos,
            'transacciones': st.session_state.transacciones,
            'estudiantes_bloqueados': list(st.session_state.estudiantes_bloqueados)
        }
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(datos_a_guardar, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f'Error al guardar la base de datos: {e}')

# Intentar importar reportlab de forma segura
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Configuración de la página
st.set_page_config(page_title='Control de Deudas - Comedor', layout='wide')
st.title('🍴 Control de Cuentas con Asesor Financiero IA')

# Inicializar estados de la sesión cargando desde el archivo JSON si existe
datos_persistidos = cargar_datos()

if 'estudiantes' not in st.session_state:
    st.session_state.estudiantes = datos_persistidos.get('estudiantes', {})
if 'productos' not in st.session_state:
    st.session_state.productos = datos_persistidos.get('productos', {
        'Almuerzo Completo': 2000.00,
        'Desayuno': 1200.00,
        'Bebida': 600.00,
        'Snack': 800.00
    })
if 'transacciones' not in st.session_state:
    st.session_state.transacciones = datos_persistidos.get('transacciones', [])
if 'estudiantes_bloqueados' not in st.session_state:
    st.session_state.estudiantes_bloqueados = datos_persistidos.get('estudiantes_bloqueados', set())
if 'alerta_activa' not in st.session_state:
    st.session_state.alerta_activa = None

# Función de Reporte PDF
def generar_pdf_deudores(datos_estudiantes):
    if not REPORTLAB_AVAILABLE:
        return None
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        'Titulo',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e3d59'),
        alignment=1
    )
    story.append(Paragraph('Reporte de Estudiantes Adeudados - Comedor', titulo_style))
    story.append(Spacer(1, 20))
    deudores = [est for est in datos_estudiantes if est['Deuda Pendiente (₡)'] > 0]
    if len(deudores) == 0:
        story.append(Paragraph('No existen deudas pendientes.', styles['Normal']))
    else:
        tabla_datos = [['Estudiante', 'Teléfono', 'Consumido', 'Pagado', 'Deuda Pendiente']]
        for d in deudores:
            tabla_datos.append([
                d['Estudiante'],
                d['Teléfono'],
                f"₡{d['Total Consumido (₡)']:,.2f}",
                f"₡{d['Total Pagado (₡)']:,.2f}",
                f"₡{d['Deuda Pendiente (₡)']:,.2f}"
            ])
        t = Table(tabla_datos, colWidths=[150, 100, 100, 100, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3d59')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dddddd')),
        ]))
        story.append(t)
    doc.build(story)
    buffer.seek(0)
    return buffer

# Definir el Diálogo Emergente Obligatorio de Alerta del Asesor IA
@st.dialog('🚨 Alerta de Riesgo - Asesor Financiero IA')
def mostrar_alerta_dialog(mensaje_alerta, estudiante_implicado):
    st.warning('🛑 Alerta sobre cuenta bajo análisis solicitado.')
    st.markdown(mensaje_alerta)
    st.markdown('---')
    st.subheader('¿Qué acción desea tomar el administrador?')

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        if st.button('👍 Acatar y Bloquear Crédito'):
            st.session_state.estudiantes_bloqueados.add(estudiante_implicado)
            st.session_state.alerta_activa = None
            guardar_datos()
            st.success(f'Se ha suspendido temporalmente el crédito para {estudiante_implicado}.')
            st.rerun()
    with col_opt2:
        if st.button('⚠️ Ignorar Recomendación (Cerrar)'):
            st.session_state.alerta_activa = None
            st.rerun()

# Sidebar
with st.sidebar:
    st.header('⚙️ Configuración')

    # Selector de modelo (Uso exclusivo de gemini-3.5-flash)
    modelo_seleccionado = st.selectbox('Modelo Gemini', ['gemini-3.5-flash'])

    # --- SISTEMA DE EXPORTACIÓN / IMPORTACIÓN DE DATOS (COPIA DE SEGURIDAD) ---
    st.markdown('---')
    st.subheader('💾 Respaldo de Datos')

    # Preparar el archivo JSON actual para descarga
    actual_datos = {
        'estudiantes': st.session_state.estudiantes,
        'productos': st.session_state.productos,
        'transacciones': st.session_state.transacciones,
        'estudiantes_bloqueados': list(st.session_state.estudiantes_bloqueados)
    }
    json_string = json.dumps(actual_datos, ensure_ascii=False, indent=4)

    st.download_button(
        label='📥 Exportar Base de Datos (JSON)',
        data=json_string,
        file_name='copia_seguridad_comedor.json',
        mime='application/json'
    )

    # Importar un archivo guardado previamente
    archivo_subido = st.file_uploader('📤 Importar copia de seguridad (JSON)', type=['json'])
    if archivo_subido is not None:
        try:
            datos_cargados = json.load(archivo_subido)
            st.session_state.estudiantes = datos_cargados.get('estudiantes', {})
            st.session_state.productos = datos_cargados.get('productos', {})
            st.session_state.transacciones = datos_cargados.get('transacciones', [])
            st.session_state.estudiantes_bloqueados = set(datos_cargados.get('estudiantes_bloqueados', []))
            guardar_datos()
            st.success('¡Base de datos restaurada con éxito!')
            st.rerun()
        except Exception as e:
            st.error(f'Error al cargar el archivo de respaldo: {e}')

    st.markdown('---')
    st.subheader('👥 Registrar Estudiante')
    nuevo_estudiante = st.text_input('Nombre del Estudiante').strip()
    telefono_estudiante = st.text_input('Número de Teléfono').strip()
    deuda_inicial = st.number_input('Deuda Inicial (₡)', min_value=0.0, value=0.0, step=500.0)
    if st.button('Registrar Estudiante'):
        if not nuevo_estudiante:
            st.error('❌ El nombre del estudiante es obligatorio. No se permite registrar al deudor sin esta información.')
        elif not telefono_estudiante:
            st.error('❌ Falta el número de teléfono. No se permite registrar al deudor sin esta información.')
        else:
            # Validación de nombres duplicados (case-insensitive para evitar duplicaciones por formato)
            estudiantes_existentes_lower = [nombre.lower() for nombre in st.session_state.estudiantes.keys()]
            if nuevo_estudiante.lower() in estudiantes_existentes_lower:
                st.error(f'❌ Error: Ya existe un deudor registrado con el nombre "{nuevo_estudiante}".')
            else:
                st.session_state.estudiantes[nuevo_estudiante] = {
                    'telefono': telefono_estudiante,
                    'consumido': deuda_inicial,
                    'pagado': 0.0
                }
                guardar_datos()
                st.success(f'{nuevo_estudiante} registrado con éxito.')
                st.rerun()

    st.markdown('---')
    st.subheader('🍔 Agregar/Actualizar Producto')
    nuevo_producto = st.text_input('Nombre del Producto/Servicio').strip()
    precio_producto = st.number_input('Precio (₡)', min_value=1.0, value=1000.0, step=100.0)
    if st.button('Guardar Producto'):
        if nuevo_producto:
            st.session_state.productos[nuevo_producto] = precio_producto
            guardar_datos()
            st.success(f'Producto {nuevo_producto} guardado a ₡{precio_producto:,.2f}')
            st.rerun()

# Consulta manual para el Asesor IA con try/except y manejo robusto
def consultar_asesor_ia_manual(estudiante, nueva_deuda):
    if not GEMINI_API_KEY_DEFAULT:
        st.error('❌ Error: La API Key de Gemini no está configurada en los secretos del servidor o variables de entorno.')
        return

    historial_estudiante = [t for t in st.session_state.transacciones if t['Estudiante'] == estudiante]
    historial_texto = str(historial_estudiante[-8:])

    system_prompt = 'Eres un Asesor de Riesgo de Crédito y Cobranza para un Comedor Universitario. Tu única función es analizar la cuenta de un estudiante bajo demanda del administrador, y justificar si se le debe suspender el crédito basándose en su saldo acumulado e historial (ejemplo de riesgo mayor a ₡10,000). Escribe de manera profesional, asertiva y concisa en colones costarricenses (₡).'
    query_user = f'El estudiante {estudiante} tiene una deuda acumulada de ₡{nueva_deuda:,.2f}. Su historial de consumo y abonos es: {historial_texto}. Analiza si amerita congelarle el crédito temporalmente y da tu recomendación directa.'
    prompt_completo = system_prompt + "\n\n" + query_user

    max_intentos = 3
    espera_inicial = 2
    for intento in range(max_intentos):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY_DEFAULT)
            response = client.models.generate_content(
                model=modelo_seleccionado,
                contents=prompt_completo,
            )
            resultado = response.text
            st.session_state.alerta_activa = {'mensaje': resultado, 'estudiante': estudiante}
            st.rerun()
            return
        except Exception as e:
            if intento == max_intentos - 1:
                st.error(f'⚠️ Error al invocar la API de Gemini: {str(e)}')
            else:
                tiempo_espera = espera_inicial * (intento + 1)
                st.warning(f'Intento {intento+1} fallido. Reintentando...')
                time.sleep(tiempo_espera)

# Evaluar si hay una alerta de IA pendiente para forzar el diálogo
if st.session_state.alerta_activa:
    mostrar_alerta_dialog(st.session_state.alerta_activa['mensaje'], st.session_state.alerta_activa['estudiante'])

# Layout Principal
col1, col2 = st.columns([1, 1])

with col1:
    st.header('💸 Registrar Consumo (Anotar a Cuenta)')
    if st.session_state.estudiantes:
        with st.form('form_consumo'):
            estudiante_sel = st.selectbox('Selecciona Estudiante', list(st.session_state.estudiantes.keys()))
            producto_sel = st.selectbox('Selecciona Producto', list(st.session_state.productos.keys()))
            cantidad = st.number_input('Cantidad', min_value=1, value=1)
            submit_cobro = st.form_submit_button('Confirmar Consumo')

            if submit_cobro:
                if estudiante_sel in st.session_state.estudiantes_bloqueados:
                    st.error(f'❌ ERROR: El crédito para {estudiante_sel} está SUSPENDIDO por recomendación del Asesor IA.')
                else:
                    total_cobrar = st.session_state.productos[producto_sel] * cantidad
                    st.session_state.estudiantes[estudiante_sel]['consumido'] += total_cobrar

                    st.session_state.transacciones.append({
                        'Fecha': date.today().strftime('%Y-%m-%d'),
                        'Estudiante': estudiante_sel,
                        'Detalle': f'{producto_sel} (x{cantidad})',
                        'Monto (₡)': total_cobrar,
                        'Tipo': 'Consumo'
                    })
                    guardar_datos()
                    st.success('Consumo registrado con éxito.')
                    st.rerun()

    st.header('💵 Registrar Pago (Abono)')
    if st.session_state.estudiantes:
        with st.form('form_pago'):
            estudiante_pago = st.selectbox('Estudiante que Paga', list(st.session_state.estudiantes.keys()))
            monto_pago = st.number_input('Monto (₡)', min_value=1.0, value=1000.0)
            submit_pago = st.form_submit_button('Registrar Pago')

            if submit_pago:
                st.session_state.estudiantes[estudiante_pago]['pagado'] += monto_pago
                st.session_state.transacciones.append({
                    'Fecha': date.today().strftime('%Y-%m-%d'),
                    'Estudiante': estudiante_pago,
                    'Detalle': 'Abono a Cuenta',
                    'Monto (₡)': monto_pago,
                    'Tipo': 'Pago'
                })

                deuda_restante = st.session_state.estudiantes[estudiante_pago]['consumido'] - st.session_state.estudiantes[estudiante_pago]['pagado']
                if deuda_restante < 5000.0 and estudiante_pago in st.session_state.estudiantes_bloqueados:
                    st.session_state.estudiantes_bloqueados.remove(estudiante_pago)
                    st.info(f'🎉 El crédito de {estudiante_pago} ha sido reactivado automáticamente al reducir su deuda.')

                guardar_datos()
                st.success('Abono registrado.')
                st.rerun()

with col2:
    st.header('📋 Estado de Cuentas')
    datos_estudiantes = []
    if st.session_state.estudiantes:
        for nombre, valores in st.session_state.estudiantes.items():
            deuda_total = valores['consumido'] - valores['pagado']
            estado = '❌ SUSPENDIDO' if nombre in st.session_state.estudiantes_bloqueados else '✅ Activo'
            datos_estudiantes.append({
                'Estudiante': nombre,
                'Teléfono': valores.get('telefono', 'No registrado'),
                'Deuda Pendiente (₡)': deuda_total,
                'Total Consumido (₡)': valores['consumido'],
                'Total Pagado (₡)': valores['pagado'],
                'Estado de Crédito': estado
            })
        df_estudiantes = pd.DataFrame(datos_estudiantes)
        st.dataframe(df_estudiantes.style.format({
            'Total Consumido (₡)': '₡{:,.2f}',
            'Total Pagado (₡)': '₡{:,.2f}',
            'Deuda Pendiente (₡)': '₡{:,.2f}'
        }), use_container_width=True)

        st.subheader('🔍 Consulta Proactiva al Asesor IA')
        estudiante_analizar = st.selectbox('Selecciona el estudiante que deseas analizar:', list(st.session_state.estudiantes.keys()))
        if st.button('🤖 Consultar Asesor Financiero IA'):
            valores_e = st.session_state.estudiantes[estudiante_analizar]
            deuda_e = valores_e['consumido'] - valores_e['pagado']
            consultar_asesor_ia_manual(estudiante_analizar, deuda_e)
    else:
        st.write('No hay estudiantes registrados.')

# Historial de Transacciones
st.header('📝 Historial de Transacciones')
if st.session_state.transacciones:
    df_trans = pd.DataFrame(st.session_state.transacciones)
    st.dataframe(df_trans.iloc[::-1], use_container_width=True)