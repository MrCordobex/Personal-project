import streamlit as st
from github import Github, GithubException
import json
import pandas as pd
from datetime import datetime, date, timedelta, time
import calendar
import pytz
import os
import re

# --- LIBRARIES FOR SCRAPING ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time as time_lib

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="AutoGestor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTES ---
REPO_NAME = "MrCordobex/Personal-project"
TIMEZONE = pytz.timezone("Europe/Madrid")
FILE_PATH = "tareas.json"
HORARIO_FILE = "horario_clases.json"
FUTBOL_FILE = "horario_futbol.json"
HORARIO_DINAMICO_FILE = "horario.json"

COLORES_PRIORIDAD = {
    "Importante": "orange",
    "Urgente": "red",
    "Normal": "green"
}

COLORES_TIPO = {
    "Examen": "#FF4B4B",
    "Entrega": "#FFA500",
    "Estudio": "#1E90FF",
    "Lectura": "#9370DB",
    "Otro": "#808080",
    "Clase": "#2E8B57"
}

def get_madrid_time():
    return datetime.now(TIMEZONE)

def get_madrid_date():
    return get_madrid_time().date()

# --- GESTIÓN DE PERSISTENCIA (GITHUB) ----

def obtener_conexion_repo():
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            st.error("❌ Falta el Token en Secrets.")
            return None
        token = st.secrets["GITHUB_TOKEN"]
        g = Github(token)
        return g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"Error conectando a GitHub: {e}")
        return None

def gestionar_json_github(archivo, accion, datos_nuevos=None, mensaje_commit="Update"):
    """Función genérica para leer/escribir cualquier JSON en GitHub"""
    repo = obtener_conexion_repo()
    if not repo: return [] if accion == 'leer' else False

    try:
        try:
            contents = repo.get_contents(archivo)
            datos = json.loads(contents.decoded_content.decode())
        except:
            datos = []
            contents = None

        if accion == 'leer':
            return datos
        
        elif accion == 'escribir':
            json_content = json.dumps(datos_nuevos, indent=4, ensure_ascii=False)
            if contents:
                repo.update_file(contents.path, mensaje_commit, json_content, contents.sha)
            else:
                repo.create_file(archivo, f"Init {archivo}", json_content)
            return True
    except Exception as e:
        st.error(f"Error en GitHub ({archivo}): {e}")
        return [] if accion == 'leer' else False

# Wrappers para mantener compatibilidad con tu código existente
def gestionar_tareas(accion, nueva_tarea=None, id_tarea_eliminar=None, tarea_actualizada=None, lista_completa=None):
    if accion == 'leer': return gestionar_json_github(FILE_PATH, 'leer')
    
    datos = gestionar_json_github(FILE_PATH, 'leer')
    mensaje = "Update tareas"
    
    if accion == 'crear':
        datos.append(nueva_tarea)
        mensaje = f"Nueva tarea: {nueva_tarea['titulo']}"
    elif accion == 'borrar':
        datos = [t for t in datos if t.get('id') != id_tarea_eliminar]
        mensaje = f"Borrar tarea ID: {id_tarea_eliminar}"
    elif accion == 'actualizar':
        datos = [t if t.get('id') != tarea_actualizada['id'] else tarea_actualizada for t in datos]
        mensaje = f"Actualizar: {tarea_actualizada['titulo']}"
    elif accion == 'guardar_todo':
        datos = lista_completa
        mensaje = "Limpieza automática"
    
    return gestionar_json_github(FILE_PATH, 'escribir', datos, mensaje)

def gestionar_horario(accion, nuevo_item=None, id_eliminar=None, item_actualizado=None):
    if accion == 'leer': return gestionar_json_github(HORARIO_DINAMICO_FILE, 'leer')
    
    data = gestionar_json_github(HORARIO_DINAMICO_FILE, 'leer')
    mensaje = "Update horario dinamico"
    
    if accion == 'crear':
        data.append(nuevo_item)
    elif accion == 'borrar':
        data = [t for t in data if t['id'] != id_eliminar]
    elif accion == 'actualizar':
        for index, item in enumerate(data):
            if item['id'] == item_actualizado['id']:
                data[index] = item_actualizado
                break
    
    return gestionar_json_github(HORARIO_DINAMICO_FILE, 'escribir', data, mensaje)

# --- FUNCIONES DE SCRAPING ---

def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    service = None
    possible_paths = ["/usr/bin/chromedriver", "/usr/lib/chromium-browser/chromedriver"]
    system_driver_path = next((p for p in possible_paths if os.path.exists(p)), None)
    
    if system_driver_path:
        service = Service(system_driver_path)
        if os.path.exists("/usr/bin/chromium"): options.binary_location = "/usr/bin/chromium"
    else:
        try: service = Service(ChromeDriverManager().install())
        except: pass

    if not service: return None
    return webdriver.Chrome(service=service, options=options)

def actualizar_horario_clases(force=False, driver=None):
    if not driver:
        driver = init_driver()
        driver_propio = True
    else: driver_propio = False
        
    if not driver: return []
    
    data_clases = []
    try:
        url = "https://portales.uloyola.es/LoyolaHorario/horario.xhtml?curso=2025%2F26&tipo=M&titu=2169&campus=2&ncurso=1&grupo=A"
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "fc-view-harness")))
        
        for _ in range(12):
            time_lib.sleep(1.5)
            headers = driver.find_elements(By.CLASS_NAME, "fc-col-header-cell")
            column_map = [{"date": h.get_attribute("data-date"), "x_start": h.rect['x'], "x_end": h.rect['x'] + h.rect['width']} for h in headers if h.get_attribute("data-date")]
            events = driver.find_elements(By.CLASS_NAME, "fc-event")
            
            for ev in events:
                try:
                    ev_center_x = ev.rect['x'] + (ev.rect['width'] / 2)
                    fecha_clase = next((col['date'] for col in column_map if col['x_start'] <= ev_center_x <= col['x_end']), None)
                    if not fecha_clase: continue
                    
                    full_text = ev.text 
                    lines = full_text.split('\n')
                    hora_text = lines[0] if lines else ""
                    content_text = lines[1] if len(lines) > 1 else ""

                    parts = content_text.split("/")
                    asig = parts[0].strip()
                    aula = parts[1].replace("Aula:", "").strip() if len(parts) > 1 else "Desconocido"
                    
                    try:
                        h_parts = hora_text.split("-")
                        new_times = [(datetime.strptime(hp.strip(), "%H:%M") + timedelta(hours=1)).strftime("%H:%M") for hp in h_parts]
                        hora_text = f"{new_times[0]} - {new_times[1]}"
                    except: pass

                    data_clases.append({"asignatura": asig, "titulo": asig, "aula": aula, "fecha": fecha_clase, "hora": hora_text, "dia_completo": False})
                except: pass
            
            try:
                driver.find_element(By.CLASS_NAME, "fc-next-button").click()
            except: break

        if driver_propio: driver.quit()
        return data_clases
    except Exception as e:
        if driver_propio: driver.quit()
        return []

def actualizar_horario_sevilla(driver=None):
    if not driver:
        driver = init_driver()
        driver_propio = True
    else: driver_propio = False
    if not driver: return []
    
    data_futbol = []
    try:
        url = "https://www.laliga.com/clubes/sevilla-fc/proximos-partidos"
        driver.get(url)
        time_lib.sleep(2)
        try:
            btns = driver.find_elements(By.TAG_NAME, "button")
            for b in btns:
                if any(x in b.text.lower() for x in ["aceptar", "accept", "consentir"]):
                    b.click()
                    break
        except: pass
        
        filas = driver.find_elements(By.TAG_NAME, "tr")
        for fila in filas:
            if "more-info" in fila.get_attribute("class"): continue
            try:
                txt = fila.text
                match_f = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", txt)
                if not match_f: continue
                fecha_iso = f"{match_f.group(3)}-{match_f.group(2)}-{match_f.group(1)}"
                
                match_h = re.search(r"(\d{2}:\d{2})", txt)
                hora_txt = match_h.group(1) if match_h else None
                
                lineas = [l.strip() for l in txt.split('\n') if l.strip()]
                idx_vs = next((i for i, l in enumerate(lineas) if l.upper() == "VS"), -1)
                
                if idx_vs > 0:
                    loc, vis = lineas[idx_vs-1], lineas[idx_vs+1]
                    ubicacion = "Casa" if "sevilla" in loc.lower() else "Fuera"
                    data_futbol.append({
                        "titulo": f"{loc} vs {vis}", "asignatura": "Fútbol", "aula": ubicacion,
                        "fecha": fecha_iso, "hora": hora_txt, "dia_completo": not bool(hora_txt), "es_futbol": True
                    })
            except: pass
        if driver_propio: driver.quit()
        return data_futbol
    except:
        if driver_propio: driver.quit()
        return []

# --- VISTAS (SIN CAMBIOS) ---
# [Aquí se mantienen tus funciones render_vista_... tal cual las enviaste]
# [Por brevedad, asumo que están definidas como en tu código original]

def render_vista_nueva_tarea():
    st.subheader("➕ Añadir Nueva Tarea")
    with st.container(border=True):
        col_tipo, col_form = st.columns([1, 3])
        with col_tipo:
            st.info("Configuración Básica")
            modo_tarea = st.radio("Modo de Tarea", ["📅 Día concreto", "⏰ Deadline"], key="modo_tarea_new")
        with col_form:
            st.markdown("##### Estancia de Datos")
            tit = st.text_input("Título de la tarea", key="tit_new")
            c1, c2 = st.columns(2)
            if "Deadline" in modo_tarea:
                f_fin = c1.date_input("Fecha Límite (Deadline)", get_madrid_date(), key="date_deadline_new")
                f_ini = None
            else:
                f_ini = c1.date_input("Fecha de Realización", get_madrid_date(), key="date_fix_new")
                f_fin = None
            chk_dia_completo = c2.checkbox("📅 Todo el día", value=True, key="chk_all_day_new")
            hora_seleccionada = None
            if not chk_dia_completo:
                hora_defecto = datetime.now().time().replace(minute=0, second=0)
                hora_seleccionada = c2.time_input("Hora", hora_defecto, step=900, key="time_new")
            prio = c1.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], key="prio_new")
            tipo = c2.selectbox("Tipo / Asignatura", list(COLORES_TIPO.keys())[:-1], key="type_new")
            if st.button("💾 Guardar Tarea", type="primary", use_container_width=True):
                if not tit: st.error("⚠️ El título es obligatorio.")
                else:
                    nt = {
                        "id": int(get_madrid_time().timestamp()), "titulo": tit, "prioridad": prio, 
                        "tipo": tipo, "estado": "Pendiente", "fecha": str(f_ini) if f_ini else str(get_madrid_date()), 
                        "fecha_fin": str(f_fin) if f_fin else None, "dia_completo": chk_dia_completo,
                        "hora": str(hora_seleccionada.strftime("%H:%M")) if hora_seleccionada else None
                    }
                    gestionar_tareas('crear', nueva_tarea=nt)
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Tarea guardada correctamente"}
                    st.rerun()

def render_vista_nuevo_horario():
    st.subheader("➕ Añadir Nuevo Evento u Horario")
    with st.container(border=True):
        c_conf, c_form = st.columns([1, 3])
        with c_conf:
            st.info("Tipo de Entrada")
            tipo_entrada = st.radio("¿Qué vas a añadir?", ["🔄 Rutina Semanal", "📅 Evento Único"], key="type_schedule")
        with c_form:
            titulo = st.text_input("Título / Asignatura", placeholder="Ej: Gimnasio, Matemáticas...")
            ubicacion = st.text_input("Ubicación / Aula", placeholder="Ej: Gofit, Aula 23, Online...")
            c1, c2 = st.columns(2)
            dias_seleccionados = []
            fecha_evento = None
            if "Rutina" in tipo_entrada:
                st.write("Selecciona los días:")
                cols_dias = st.columns(7)
                dias_abv = ["L", "M", "X", "J", "V", "S", "D"]
                for i, col in enumerate(cols_dias):
                    if col.checkbox(dias_abv[i], key=f"d_{i}"): dias_seleccionados.append(i)
            else:
                fecha_evento = st.date_input("Fecha del Evento", get_madrid_date())
            ch1, ch2, ch3 = st.columns([1, 1, 1])
            h_init = ch1.time_input("Hora Inicio", time(10,0))
            h_end = ch2.time_input("Hora Fin", time(11,0))
            if st.button("💾 Guardar Horario", type="primary", use_container_width=True):
                if not titulo: st.error("El título es obligatorio")
                elif "Rutina" in tipo_entrada and not dias_seleccionados: st.error("Selecciona un día")
                else:
                    nuevo_item = {
                        "id": int(get_madrid_time().timestamp()), "titulo": titulo, "ubicacion": ubicacion,
                        "tipo": "Rutina" if "Rutina" in tipo_entrada else "Evento", "es_rutina": "Rutina" in tipo_entrada,
                        "dias_semana": dias_seleccionados, "fecha": str(fecha_evento) if fecha_evento else None,
                        "hora_inicio": str(h_init.strftime("%H:%M")), "hora_fin": str(h_end.strftime("%H:%M"))
                    }
                    gestionar_horario('crear', nuevo_item=nuevo_item)
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Horario guardado"}
                    st.rerun()

# --- MAIN ---

def main():
    st.title("🎓 AutoGestor")

    # 1. Notificaciones
    if "mensaje_global" in st.session_state and st.session_state["mensaje_global"]:
        m = st.session_state["mensaje_global"]
        if m["tipo"] == "exito": st.success(m["texto"])
        else: st.error(m["texto"])
        st.session_state["mensaje_global"] = None

    # 2. CARGA DE DATOS (SIEMPRE DESDE GITHUB)
    tareas = gestionar_tareas('leer')
    horario_dinamico = gestionar_horario('leer')
    horario_clases_scraped = gestionar_json_github(HORARIO_FILE, 'leer')
    horario_futbol_scraped = gestionar_json_github(FUTBOL_FILE, 'leer')

    # 3. Sidebar
    with st.sidebar:
        st.header("👁️ Navegación")
        opciones = ["Diaria", "Semanal", "Mensual", "---", "➕ Nueva Tarea", "➕ Nuevo Evento/Horario", "📋 Gestionar Todas"]
        vista_actual = st.radio("Ir a:", opciones, index=0, label_visibility="collapsed")
        
        st.divider()
        st.header("📅 Control de Fecha")
        fecha_base = st.date_input("Fecha Base", get_madrid_date())

        if st.button("🔄 Actualizar Horario", use_container_width=True):
            with st.spinner("Scrapeando Loyola y Sevilla FC..."):
                driver = init_driver()
                if driver:
                    clases = actualizar_horario_clases(force=True, driver=driver)
                    gestionar_json_github(HORARIO_FILE, 'escribir', clases)
                    
                    futbol = actualizar_horario_sevilla(driver=driver)
                    gestionar_json_github(FUTBOL_FILE, 'escribir', futbol)
                    
                    driver.quit()
                    st.success("GitHub actualizado.")
                    st.rerun()

    # 4. Limpieza automática
    hoy = get_madrid_date()
    tareas_f = [t for t in tareas if not (t['estado'] == 'Completada' and (datetime.strptime(t.get('fecha_fin') or t.get('fecha'), "%Y-%m-%d").date() < hoy))]
    if len(tareas_f) != len(tareas):
        gestionar_tareas('guardar_todo', lista_completa=tareas_f)
        tareas = tareas_f

    # 5. Router de Vistas
    if vista_actual == "Diaria":
        render_vista_diaria(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "Semanal":
        render_vista_semanal(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "Mensual":
        render_vista_mensual(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista_actual == "➕ Nueva Tarea":
        render_vista_nueva_tarea()
    elif vista_actual == "➕ Nuevo Evento/Horario":
        render_vista_nuevo_horario()
    elif vista_actual == "📋 Gestionar Todas":
        render_vista_gestionar_todas(tareas)

# Nota: Asegúrate de incluir tus funciones render_vista_... 
# que ya tienes programadas para que el código sea funcional al 100%.

if __name__ == "__main__":
    main()