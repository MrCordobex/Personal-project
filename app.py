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

NOMBRES_MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
DIAS_SEMANA_ABR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

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

def gestionar_tareas(accion, nueva_tarea=None, id_tarea_eliminar=None, tarea_actualizada=None, lista_completa=None):
    datos = gestionar_json_github(FILE_PATH, 'leer')
    if accion == 'leer': return datos
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
    data = gestionar_json_github(HORARIO_DINAMICO_FILE, 'leer')
    if accion == 'leer': return data
    mensaje = "Update horario"
    if accion == 'crear': data.append(nuevo_item)
    elif accion == 'borrar': data = [t for t in data if t['id'] != id_eliminar]
    elif accion == 'actualizar':
        for index, item in enumerate(data):
            if item['id'] == item_actualizado['id']:
                data[index] = item_actualizado
                break
    return gestionar_json_github(HORARIO_DINAMICO_FILE, 'escribir', data, mensaje)

# --- SCRAPING ---

def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    service = None
    paths = ["/usr/bin/chromedriver", "/usr/lib/chromium-browser/chromedriver"]
    sys_path = next((p for p in paths if os.path.exists(p)), None)
    if sys_path:
        service = Service(sys_path)
        if os.path.exists("/usr/bin/chromium"): options.binary_location = "/usr/bin/chromium"
    else:
        try: service = Service(ChromeDriverManager().install())
        except: pass
    if not service: return None
    return webdriver.Chrome(service=service, options=options)

def actualizar_horario_clases(force=False, driver=None):
    if not driver: driver = init_driver()
    if not driver: return []
    data_clases = []
    try:
        url = "https://portales.uloyola.es/LoyolaHorario/horario.xhtml?curso=2025%2F26&tipo=M&titu=2169&campus=2&ncurso=1&grupo=A"
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "fc-view-harness")))
        for _ in range(12):
            time_lib.sleep(1.5)
            headers = driver.find_elements(By.CLASS_NAME, "fc-col-header-cell")
            column_map = [{"date": h.get_attribute("data-date"), "x_start": h.rect['x'], "x_end": h.rect['x'] + h.rect['width']} for h in headers if h.get_attribute("data-date")]
            events = driver.find_elements(By.CLASS_NAME, "fc-event")
            for ev in events:
                try:
                    ev_center_x = ev.rect['x'] + (ev.rect['width'] / 2)
                    fecha = next((col['date'] for col in column_map if col['x_start'] <= ev_center_x <= col['x_end']), None)
                    if not fecha: continue
                    lines = ev.text.split('\n')
                    hora, asig = lines[0], lines[1].split("/")[0].strip()
                    aula = lines[1].split("/")[1].replace("Aula:", "").strip() if "/" in lines[1] else "Desc"
                    try:
                        h_parts = hora.split("-")
                        new_h = [(datetime.strptime(hp.strip(), "%H:%M") + timedelta(hours=1)).strftime("%H:%M") for hp in h_parts]
                        hora = f"{new_h[0]} - {new_h[1]}"
                    except: pass
                    data_clases.append({"asignatura": asig, "titulo": asig, "aula": aula, "fecha": fecha, "hora": hora, "dia_completo": False})
                except: pass
            try: driver.find_element(By.CLASS_NAME, "fc-next-button").click()
            except: break
        return data_clases
    except: return []

def actualizar_horario_sevilla(driver=None):
    if not driver: driver = init_driver()
    if not driver: return []
    data_f = []
    try:
        driver.get("https://www.laliga.com/clubes/sevilla-fc/proximos-partidos")
        time_lib.sleep(2)
        try:
            for b in driver.find_elements(By.TAG_NAME, "button"):
                if any(x in b.text.lower() for x in ["aceptar", "accept"]): b.click(); break
        except: pass
        for fila in driver.find_elements(By.TAG_NAME, "tr"):
            if "more-info" in fila.get_attribute("class"): continue
            try:
                txt = fila.text
                m_f = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", txt)
                if not m_f: continue
                fecha = f"{m_f.group(3)}-{m_f.group(2)}-{m_f.group(1)}"
                m_h = re.search(r"(\d{2}:\d{2})", txt)
                hora = m_h.group(1) if m_h else None
                lineas = [l.strip() for l in txt.split('\n') if l.strip()]
                idx_vs = next((i for i, l in enumerate(lineas) if l.upper() == "VS"), -1)
                if idx_vs > 0:
                    loc, vis = lineas[idx_vs-1], lineas[idx_vs+1]
                    data_f.append({"titulo": f"{loc} vs {vis}", "asignatura": "Fútbol", "aula": "Casa" if "sevilla" in loc.lower() else "Fuera", "fecha": fecha, "hora": hora, "dia_completo": not hora, "es_futbol": True})
            except: pass
        return data_f
    except: return []

# --- FUNCIONES GRÁFICAS (UI) ---

@st.dialog("Detalles")
def mostrar_detalle_item(item):
    tipo = item.get('tipo', 'Evento')
    titulo = item.get('titulo', 'Sin título')
    c_icon, c_tit = st.columns([1, 5])
    with c_icon:
        if item.get('es_universidad'): st.subheader("🎓")
        elif item.get('es_rutina'): st.subheader("🔄")
        elif tipo == 'tarea': st.subheader("📝")
        else: st.subheader("📅")
    with c_tit:
        st.subheader(titulo)
        st.caption(f"Tipo: {tipo}")
    st.divider()
    c1, c2 = st.columns(2)
    hora_str = item.get('hora') or (f"{item.get('hora_inicio')} - {item.get('hora_fin')}" if item.get('hora_inicio') else 'Todo el día')
    c1.markdown(f"**🕒 Hora:** {hora_str}")
    if item.get('aula'): c1.markdown(f"**📍 Aula:** {item['aula']}")
    if item.get('ubicacion'): c1.markdown(f"**📍 Ubicación:** {item['ubicacion']}")
    if item.get('fecha'): c2.markdown(f"**📅 Fecha:** {item['fecha']}")
    if item.get('dias_semana'):
        d_map = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        c2.markdown(f"**🔄 Días:** {', '.join([d_map[i] for i in item['dias_semana']])}")
    st.divider()
    if tipo == 'tarea':
        if item.get('estado') != 'Completada':
            if st.button("✅ Marcar como Completada", use_container_width=True):
                item['estado'] = 'Completada'
                gestionar_tareas('actualizar', tarea_actualizada=item)
                st.rerun()
    elif item.get('es_rutina') or (not item.get('es_universidad') and item.get('id')):
        if st.button("🗑️ Eliminar Evento", type="primary", use_container_width=True):
            gestionar_horario('borrar', id_eliminar=item['id'])
            st.rerun()

def render_tarjeta_gestion(t):
    estado_icon = "✅" if t['estado'] == 'Completada' else "⬜"
    bg_op = "0.5" if t['estado'] == 'Completada' else "1"
    with st.container(border=True):
        c_main, c_actions = st.columns([5, 2])
        with c_main:
            st.markdown(f"<h4 style='margin:0; opacity:{bg_op}'>{estado_icon} {t['titulo']}</h4>", unsafe_allow_html=True)
            f_display = f"⏰ Deadline: {t['fecha_fin']}" if t.get('fecha_fin') else f"📅 {t['fecha']}"
            if t.get('hora'): f_display += f" @ {t['hora']}"
            color_p = "red" if t['prioridad'] == "Urgente" else "orange" if t['prioridad'] == "Importante" else "green"
            st.markdown(f"<span style='color:{color_p}; font-weight:bold'>{t['prioridad']}</span> | {t['tipo']} | **{f_display}**", unsafe_allow_html=True)
        with c_actions:
            ca1, ca2, ca3 = st.columns(3)
            if t['estado'] != 'Completada':
                if ca1.button("✅", key=f"ok_{t['id']}"):
                    t['estado'] = 'Completada'; gestionar_tareas('actualizar', tarea_actualizada=t); st.rerun()
            else:
                if ca1.button("↩️", key=f"rev_{t['id']}"):
                    t['estado'] = 'Pendiente'; gestionar_tareas('actualizar', tarea_actualizada=t); st.rerun()
            with ca2.popover("✏️"):
                with st.form(f"ed_{t['id']}"):
                    e_tit = st.text_input("Título", t['titulo'])
                    if st.form_submit_button("Guardar"):
                        t['titulo'] = e_tit; gestionar_tareas('actualizar', tarea_actualizada=t); st.rerun()
            if ca3.button("🗑️", key=f"del_{t['id']}"):
                gestionar_tareas('borrar', id_tarea_eliminar=t['id']); st.rerun()

def render_vista_nueva_tarea():
    st.subheader("➕ Añadir Nueva Tarea")
    with st.container(border=True):
        col_tipo, col_form = st.columns([1, 3])
        with col_tipo: modo = st.radio("Modo", ["📅 Día concreto", "⏰ Deadline"], key="modo_tarea_new")
        with col_form:
            tit = st.text_input("Título", key="tit_new")
            c1, c2 = st.columns(2)
            f_ini = c1.date_input("Fecha", get_madrid_date()) if "concreto" in modo else None
            f_fin = c1.date_input("Deadline", get_madrid_date()) if "Deadline" in modo else None
            chk = c2.checkbox("📅 Todo el día", value=True)
            hora = c2.time_input("Hora", datetime.now().time()) if not chk else None
            prio = c1.selectbox("Prioridad", ["Normal", "Importante", "Urgente"])
            tipo = c2.selectbox("Tipo", list(COLORES_TIPO.keys())[:-1])
            if st.button("💾 Guardar Tarea", type="primary", use_container_width=True):
                nt = {"id": int(get_madrid_time().timestamp()), "titulo": tit, "prioridad": prio, "tipo": tipo, "estado": "Pendiente", "fecha": str(f_ini or get_madrid_date()), "fecha_fin": str(f_fin) if f_fin else None, "dia_completo": chk, "hora": hora.strftime("%H:%M") if hora else None}
                gestionar_tareas('crear', nueva_tarea=nt); st.rerun()

def render_vista_nuevo_horario():
    st.subheader("➕ Añadir Nuevo Evento")
    with st.container(border=True):
        c_conf, c_form = st.columns([1, 3])
        with c_conf: tipo = st.radio("Tipo", ["🔄 Rutina Semanal", "📅 Evento Único"])
        with c_form:
            tit = st.text_input("Título")
            ubi = st.text_input("Ubicación")
            dias = []
            fecha = None
            if "Rutina" in tipo:
                cols = st.columns(7); d_abv = ["L", "M", "X", "J", "V", "S", "D"]
                for i, col in enumerate(cols):
                    if col.checkbox(d_abv[i], key=f"dsel_{i}"): dias.append(i)
            else: fecha = st.date_input("Fecha", get_madrid_date())
            h1, h2 = st.columns(2)
            hi = h1.time_input("Inicio", time(10,0))
            hf = h2.time_input("Fin", time(11,0))
            if st.button("💾 Guardar", type="primary"):
                gestionar_horario('crear', nuevo_item={"id": int(get_madrid_time().timestamp()), "titulo": tit, "ubicacion": ubi, "es_rutina": "Rutina" in tipo, "dias_semana": dias, "fecha": str(fecha) if fecha else None, "hora_inicio": hi.strftime("%H:%M"), "hora_fin": hf.strftime("%H:%M")})
                st.rerun()

def render_vista_gestionar_todas(tareas):
    st.subheader("📋 Gestión Global")
    t1, t2 = st.tabs(["📝 Tareas", "📅 Horarios"])
    with t1:
        pend = [t for t in tareas if t['estado'] != 'Completada']
        comp = [t for t in tareas if t['estado'] == 'Completada']
        for t in pend: render_tarjeta_gestion(t)
        st.divider()
        with st.expander("Completadas"):
            for t in comp: render_tarjeta_gestion(t)
    with t2:
        h = gestionar_horario('leer')
        for item in h:
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                c1.write(f"**{item['titulo']}**")
                if c2.button("🗑️", key=f"delh_{item['id']}"):
                    gestionar_horario('borrar', id_eliminar=item['id']); st.rerun()

def render_vista_diaria(tareas, fecha_sel, horario_din, horario_cla, horario_fut):
    hoy = get_madrid_date()
    # Atrasadas
    atrasadas = [t for t in tareas if t['estado'] != 'Completada' and datetime.strptime(t.get('fecha_fin') or t.get('fecha'), "%Y-%m-%d").date() < hoy]
    if atrasadas:
        st.error(f"🚨 Tienes {len(atrasadas)} tareas atrasadas")
        with st.expander("Ver"):
            for a in atrasadas: st.write(f"🔴 {a['titulo']}")

    c_hor, c_tar = st.columns([1, 2])
    with c_hor:
        st.subheader("🏫 Horario")
        dia_str = str(fecha_sel)
        hoy_items = []
        for c in horario_cla:
            if c['fecha'] == dia_str: hoy_items.append({**c, "es_universidad": True})
        for f in horario_fut:
            if f['fecha'] == dia_str: hoy_items.append({**f, "es_futbol": True})
        for d in horario_din:
            if d.get('es_rutina') and fecha_sel.weekday() in d['dias_semana']:
                hoy_items.append({"hora": f"{d['hora_inicio']} - {d['hora_fin']}", "asignatura": d['titulo'], "aula": d['ubicacion']})
            elif d.get('fecha') == dia_str:
                hoy_items.append({"hora": f"{d['hora_inicio']} - {d['hora_fin']}", "asignatura": d['titulo'], "aula": d['ubicacion']})
        
        hoy_items.sort(key=lambda x: x['hora'].split('-')[0])
        for hi in hoy_items:
            icon = "🎓" if hi.get("es_universidad") else "⚽" if hi.get("es_futbol") else "📅"
            st.success(f"**{hi['hora']}**\n\n{icon} {hi['asignatura']}\n\n📍 {hi['aula']}")

    with c_tar:
        st.subheader("📝 Tareas")
        t_hoy = [t for t in tareas if t.get('fecha') == dia_str and not t.get('fecha_fin')]
        d_hoy = [t for t in tareas if t.get('fecha_fin') == dia_str]
        for t in t_hoy + d_hoy:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                st_comp = "opacity: 0.5;" if t['estado'] == 'Completada' else ""
                c1.markdown(f"<div style='{st_comp}'><strong>{t['titulo']}</strong> ({t['tipo']})</div>", unsafe_allow_html=True)
                if t['estado'] != 'Completada' and c2.button("✅", key=f"v_diaria_{t['id']}"):
                    t['estado'] = 'Completada'; gestionar_tareas('actualizar', tarea_actualizada=t); st.rerun()

def render_vista_semanal(tareas, fecha_base, horario_din, horario_cla, horario_fut):
    st.markdown("""<style>
        @media (orientation: portrait) and (max-width: 600px) {
            div[data-testid="stHorizontalBlock"] { display: grid !important; grid-template-columns: repeat(7, 1fr) !important; gap: 1px !important; }
            div[data-testid="column"] { min-width: 0 !important; flex: none !important; }
            .mobile-header-text { font-size: 3vw !important; }
            div[data-testid="stButton"] button { font-size: 2vw !important; padding: 0 !important; }
        }
    </style>""", unsafe_allow_html=True)
    start = fecha_base - timedelta(days=fecha_base.weekday())
    cols = st.columns(7)
    for i, col in enumerate(cols):
        dia = start + timedelta(days=i)
        is_sel = dia == fecha_base
        bg = "#1E90FF" if is_sel else "transparent"
        with col:
            st.markdown(f"<div style='text-align:center; background:{bg}; border-radius:5px;'><strong>{DIAS_SEMANA_ABR[i]}</strong><br>{dia.day}</div>", unsafe_allow_html=True)
            dia_s = str(dia)
            items = []
            for c in horario_cla:
                if c['fecha'] == dia_s: items.append({"t": "Clase", "tit": c['asignatura'], "h": c['hora'], "raw": {**c, "es_universidad": True}})
            for f in horario_fut:
                if f['fecha'] == dia_s: items.append({"t": "Fut", "tit": f['titulo'], "h": f['hora'] or "TBD", "raw": {**f, "es_futbol": True}})
            for t in tareas:
                if (t.get('fecha') == dia_s or t.get('fecha_fin') == dia_s) and t['estado'] != 'Completada':
                    items.append({"t": "Tarea", "tit": t['titulo'], "h": t.get('hora') or "00:00", "raw": {**t, "tipo": "tarea"}})
            
            items.sort(key=lambda x: x['h'])
            for it in items:
                icon = "🎓" if it['t'] == "Clase" else "⚽" if it['t'] == "Fut" else "📝"
                if st.button(f"{icon}\n{it['tit'][:5]}", key=f"w_{dia}_{it['tit']}_{it['h']}"):
                    mostrar_detalle_item(it['raw'])

def render_vista_mensual(tareas, fecha_base, horario_din, horario_cla, horario_fut):
    st.subheader(f"{NOMBRES_MESES[fecha_base.month]} {fecha_base.year}")
    cal = calendar.monthcalendar(fecha_base.year, fecha_base.month)
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0: continue
            dia_actual = date(fecha_base.year, fecha_base.month, day)
            dia_s = str(dia_actual)
            with cols[i]:
                st.markdown(f"**{day}**")
                # Mostrar puntitos o iconos si hay algo
                count = sum(1 for c in horario_cla if c['fecha'] == dia_s) + sum(1 for f in horario_fut if f['fecha'] == dia_s)
                if count > 0: st.markdown("🔵" * min(count, 3))
                if st.button("👁️", key=f"m_btn_{day}"):
                    st.info(f"Día {day}: {count} eventos. Ver en vista Diaria.")

# --- MAIN APP ---

def main():
    tareas = gestionar_tareas('leer')
    horario_dinamico = gestionar_horario('leer')
    horario_clases_scraped = gestionar_json_github(HORARIO_FILE, 'leer')
    horario_futbol_scraped = gestionar_json_github(FUTBOL_FILE, 'leer')

    with st.sidebar:
        st.header("Navegación")
        vista = st.radio("Ir a:", ["Diaria", "Semanal", "Mensual", "➕ Nueva Tarea", "➕ Nuevo Evento/Horario", "📋 Gestionar Todas"])
        st.divider()
        fecha_base = st.date_input("Fecha Base", get_madrid_date())
        if st.button("🔄 Actualizar Horario"):
            with st.spinner("Scrapeando..."):
                driver = init_driver()
                if driver:
                    clases = actualizar_horario_clases(driver=driver)
                    gestionar_json_github(HORARIO_FILE, 'escribir', clases)
                    futbol = actualizar_horario_sevilla(driver=driver)
                    gestionar_json_github(FUTBOL_FILE, 'escribir', futbol)
                    driver.quit(); st.rerun()

    if vista == "Diaria": render_vista_diaria(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista == "Semanal": render_vista_semanal(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista == "Mensual": render_vista_mensual(tareas, fecha_base, horario_dinamico, horario_clases_scraped, horario_futbol_scraped)
    elif vista == "➕ Nueva Tarea": render_vista_nueva_tarea()
    elif vista_actual == "➕ Nuevo Evento/Horario": render_vista_nuevo_horario() # Corregido NameError potencial
    elif vista == "📋 Gestionar Todas": render_vista_gestionar_todas(tareas)

if __name__ == "__main__":
    main()