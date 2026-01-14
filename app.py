import streamlit as st
from github import Github, GithubException
import json
import pandas as pd
from datetime import datetime, date

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Academic Task Planner",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONFIGURACIÓN DE USUARIO (CAMBIAR ESTO) ---
# Nombre del repositorio donde se guardará el archivo tareas.json
REPO_NAME = "MrCordobex/Personal-project"  # <-- ¡ACTUALIZA ESTO CON TU REPO!
FILE_PATH = "tareas.json"

# --- ESTRUCTURA DE HORARIO FIJO (Editable) ---
# Adapta esto con tus asignaturas reales
HORARIO_FIJO = {
    0: [ # Lunes
        {"hora": "09:00 - 11:00", "asignatura": "Desarrollo Web", "aula": "1.4"},
        {"hora": "11:30 - 13:30", "asignatura": "Bases de Datos", "aula": "2.1"},
    ],
    1: [ # Martes
        {"hora": "09:00 - 11:00", "asignatura": "Inteligencia Artificial", "aula": "1.4"},
    ],
    2: [ # Miércoles
        {"hora": "10:00 - 12:00", "asignatura": "Redes de Computadores", "aula": "Lab 3"},
    ],
    3: [ # Jueves
        {"hora": "09:00 - 11:00", "asignatura": "Desarrollo Web", "aula": "1.4"},
        {"hora": "15:00 - 17:00", "asignatura": "Ingeniería Software", "aula": "2.2"},
    ],
    4: [ # Viernes
        {"hora": "09:00 - 11:00", "asignatura": "Inglés Técnico", "aula": "Online"},
    ],
    5: [], # Sábado
    6: []  # Domingo
}

COLORES_PRIORIDAD = {
    "Importante": "orange",
    "Urgente": "red",
    "Normal": "green"
}

# --- GESTIÓN DE PERSISTENCIA (GITHUB) ---

def obtener_conexion_repo():
    """Conecta con la API de GitHub usando el token almacenado en secrets."""
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            st.error("❌ Falta el Token en Secrets (.streamlit/secrets.toml).")
            return None
        
        token = st.secrets["GITHUB_TOKEN"]
        g = Github(token)
        return g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"Error conectando a GitHub: {e}")
        return None

def gestionar_tareas(accion, nueva_tarea=None, id_tarea_eliminar=None, tarea_actualizada=None):
    """
    Gestiona el CRUD de tareas en el archivo JSON de GitHub.
    accion: 'leer', 'crear', 'borrar', 'actualizar'
    """
    repo = obtener_conexion_repo()
    if not repo:
        return [] if accion == 'leer' else False

    try:
        # Intentar leer el archivo existente
        try:
            contents = repo.get_contents(FILE_PATH)
            datos = json.loads(contents.decoded_content.decode())
        except GithubException:
            # Si no existe, inicializamos lista vacía create_file luego
            datos = []
            contents = None

        if accion == 'leer':
            return datos

        elif accion == 'crear' and nueva_tarea:
            datos.append(nueva_tarea)
            mensaje = f"Nueva tarea: {nueva_tarea['titulo']}"
        
        elif accion == 'borrar' and id_tarea_eliminar is not None:
            datos = [t for t in datos if t.get('id') != id_tarea_eliminar]
            mensaje = f"Borrar tarea ID: {id_tarea_eliminar}"

        elif accion == 'actualizar' and tarea_actualizada:
            # Reemplazar la tarea con el mismo ID
            datos = [t if t.get('id') != tarea_actualizada['id'] else tarea_actualizada for t in datos]
            mensaje = f"Actualizar tarea: {tarea_actualizada['titulo']}"
        
        else:
            return False

        # Guardar cambios
        json_content = json.dumps(datos, indent=4)
        if contents:
            repo.update_file(contents.path, mensaje, json_content, contents.sha)
        else:
            repo.create_file(FILE_PATH, "Inicializar tareas.json", json_content)
        
        # Limpiar caché para reflejar cambios inmediatos
        # st.cache_data.clear() # Si usáramos cache, aquí se limpiaría
        return True

    except Exception as e:
        st.error(f"Error operando en GitHub ({accion}): {e}")
        return False

# --- UI Y LÓGICA ---

def main():
    st.title("🎓 Academic Task Planner")

    # --- NOTIFICACIONES GLOBLALES ---
    # Mostrar mensaje si existe en session_state y luego limpiarlo
    if "mensaje_global" in st.session_state and st.session_state["mensaje_global"]:
        tipo = st.session_state["mensaje_global"]["tipo"]
        texto = st.session_state["mensaje_global"]["texto"]
        if tipo == "exito":
            st.success(texto)
        elif tipo == "error":
            st.error(texto)
        # Limpiar el mensaje para que no salga en la siguiente recarga
        st.session_state["mensaje_global"] = None

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("📅 Navegación")
        fecha_seleccionada = st.date_input("Selecciona una fecha", date.today())
        
        st.divider()
        st.info(f"Día seleccionado: **{fecha_seleccionada.strftime('%A')}**")
        
    # Cargar datos
    tareas = gestionar_tareas('leer')
    
    # Pestañas principales
    tab1, tab2, tab3 = st.tabs(["📌 Tareas de Hoy & Horario", "➕ Añadir Tarea", "📋 Todas las Tareas"])

    # --- TAB 1: Tareas de Hoy & Horario ---
    with tab1:
        col_horario, col_tareas = st.columns([1, 2])
        
        with col_horario:
            st.subheader("🏫 Horario")
            dia_semana = fecha_seleccionada.weekday() # 0=Lunes, 6=Domingo
            clases_hoy = HORARIO_FIJO.get(dia_semana, [])
            
            if clases_hoy:
                for clase in clases_hoy:
                    st.success(f"**{clase['hora']}**\n\n{clase['asignatura']}\n\n📍 {clase['aula']}")
            else:
                st.write("No hay clases programadas para este día.")

        with col_tareas:
            st.subheader(f"📝 Tareas para el {fecha_seleccionada}")
            
            # --- LÓGICA DE FILTRADO Y PRIORIDAD DINÁMICA ---
            tareas_hoy_list = []
            tareas_proximas_list = []
            
            hoy_real = date.today()

            for t in tareas:
                if t.get('estado') == 'Completada':
                    continue
                
                # --- NUEVA LÓGICA DE MODOS ---
                es_task_deadline = t.get('fecha_fin') is not None
                
                # Inicializar variables visuales
                es_urgente_auto = False
                dias_restantes_msg = ""
                delta_dias = 999
                
                if es_task_deadline:
                    # Lógica para tareas con DEADLINE
                    try:
                        d_fin = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                        delta_dias = (d_fin - hoy_real).days
                        
                        if delta_dias < 0:
                            dias_restantes_msg = f"🔴 Venció hace {abs(delta_dias)} días"
                            es_urgente_auto = True
                        elif delta_dias == 0:
                            dias_restantes_msg = "🟠 Vence HOY"
                            es_urgente_auto = True
                        else:
                            dias_restantes_msg = f"⏳ Quedan {delta_dias} días"
                            if delta_dias < 2:
                                es_urgente_auto = True
                    except:
                        pass
                else:
                    # Lógica para tareas de DÍA CONCRETO
                    # No hay countdown, solo se hacen este día
                    dias_restantes_msg = "" # No lleva countdown

                # Determinar Prioridad Visual
                prioridad_real = t.get('prioridad', 'Normal')
                if es_urgente_auto:
                    prioridad_visual = "Urgente" 
                    nota_urgencia = "🔥 (Auto-Urgente)"
                else:
                    prioridad_visual = prioridad_real
                    nota_urgencia = ""

                # Objeto enriched
                t_visual = t.copy()
                t_visual['prioridad_visual'] = prioridad_visual
                t_visual['color'] = COLORES_PRIORIDAD.get(prioridad_visual, "gray")
                t_visual['msg_tiempo'] = dias_restantes_msg
                t_visual['nota_urgencia'] = nota_urgencia
                
                # --- CLASIFICACIÓN EN COLAS ---
                
                if not es_task_deadline:
                    # Tarea de DÍA CONCRETO: Solo sale si fecha == fecha_seleccionada
                    if t.get('fecha') == str(fecha_seleccionada):
                        tareas_hoy_list.append(t_visual)
                else:
                    # Tarea de DEADLINE: Sale en "Próximas" siempre que no haya vencido (o sí, para alertar)
                    # Y solo si miramos HOY (para no ensuciar la vista de dias pasados/futuros)
                    if fecha_seleccionada == hoy_real:
                        tareas_proximas_list.append(t_visual)


            # --- RENDERIZADO ---
            
            def render_tarea(task):
                color = task['color']
                prio = task['prioridad_visual']
                msg = task['msg_tiempo']
                nota = task['nota_urgencia']
                
                with st.container(border=True):
                    cols = st.columns([4, 1])
                    # Título + Prioridad + Días Restantes
                    header_html = f"**{task['titulo']}** <span style='color:{color}'>({prio})</span> {nota}"
                    cols[0].markdown(header_html, unsafe_allow_html=True)
                    
                    detalles = f"🏷️ {task['tipo']}"
                    if msg:
                        detalles += f" | **{msg}**"
                        
                    cols[0].write(detalles)
                    
                    if cols[1].button("✅", key=f"check_tab1_{task['id']}"): # Key único
                        task['estado'] = 'Completada'
                        if gestionar_tareas('actualizar', tarea_actualizada=task):
                            st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "✅ Tarea completada."}
                        else:
                            st.session_state["mensaje_global"] = {"tipo": "error", "texto": "❌ Error al actualizar."}
                        st.rerun()

            if not tareas_hoy_list and not tareas_proximas_list:
                st.info("✅ Nada pendiente para hoy.")

            if tareas_hoy_list:
                st.markdown("### 📅 Tareas del Día")
                for t in tareas_hoy_list:
                    render_tarea(t)
            
            # Solo mostrar sección "En curso / Pendientes" si estamos viendo el día actual
            if tareas_proximas_list and fecha_seleccionada == date.today():
                st.markdown("### 🚑 Entregas y Deadlines")
                # Ordenar por urgencia (fecha fin más cercana)
                tareas_proximas_list.sort(key=lambda x: x.get('fecha_fin') or "9999-12-31")
                for t in tareas_proximas_list:
                    render_tarea(t)


    # --- TAB 2: Añadir Tarea ---
    with tab2:
        st.subheader("Nueva Tarea")
        
        modo_tarea = st.radio("¿Qué tipo de tarea es?", 
                              ["📅 Tarea para un día concreto", "⏰ Tarea con fecha límite (Deadline)"],
                              horizontal=True)
        
        with st.form("form_nueva_tarea"):
            titulo = st.text_input("Título")
            
            c1, c2 = st.columns(2)
            
            fecha_input = None
            fecha_fin_input = None
            
            if "día concreto" in modo_tarea:
                fecha_input = c1.date_input("Fecha de realización", date.today())
                c2.info("Esta tarea aparecerá SÓLO en el día seleccionado.")
            else:
                fecha_fin_input = c1.date_input("Fecha Límite (Deadline)", date.today())
                c2.warning("Esta tarea mostrará una cuenta atrás hasta que se complete.")
            
            c3, c4 = st.columns(2)
            prioridad = c3.selectbox("Prioridad", ["Normal", "Importante", "Urgente"])
            tipo = c4.selectbox("Tipo", ["Estudio", "Entrega", "Examen", "Lectura", "Otro"])
            
            submitted = st.form_submit_button("Guardar Tarea")
            
            if submitted and titulo:
                # Generar ID único simple (timestamp)
                nuevo_id = int(datetime.now().timestamp())
                
                nueva_tarea = {
                    "id": nuevo_id,
                    "titulo": titulo,
                    "prioridad": prioridad,
                    "tipo": tipo,
                    "estado": "Pendiente",
                    # Guardamos segun el modo:
                    "fecha": str(fecha_input) if fecha_input else str(date.today()), # Fecha creación o ejecución
                    "fecha_fin": str(fecha_fin_input) if fecha_fin_input else None
                }
                
                if gestionar_tareas('crear', nueva_tarea=nueva_tarea):
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Nueva tarea guardada correctamente en GitHub."}
                    st.rerun()
                else:
                    st.error("Error al guardar.") # Fallback si no recarga

    # --- TAB 3: Todas las Tareas (Gestión) ---
    with tab3:
        st.subheader("Gestión Global y Edición")
        
        # Convertir a DataFrame para mejor visualización si hay muchas
        if not tareas:
            st.info("No hay tareas registradas (o han sido eliminadas por antigüedad).")
        else:
            for t in tareas:
                # Calcular días restantes si hay deadline
                dias_restantes_str = ""
                if t.get('fecha_fin'):
                    try:
                        d_fin = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                        delta = (d_fin - date.today()).days
                        if delta < 0:
                            dias_restantes_str = "🔴 Vencida"
                        elif delta == 0:
                            dias_restantes_str = "🟠 Hoy"
                        else:
                            dias_restantes_str = f"🟢 Quedan {delta} días"
                    except:
                        pass

                titulo_expander = f"{t['titulo']} ({t['estado']}) {dias_restantes_str}"
                
                with st.expander(titulo_expander):
                    # Formulario de edición
                    with st.form(f"edit_{t['id']}"):
                        e_titulo = st.text_input("Título", t['titulo'])
                        
                        cols_edit = st.columns(2)
                        
                        # Detectar tipo para mostrar el campo de fecha adecuado
                        es_deadline = t.get('fecha_fin') is not None
                        
                        if es_deadline:
                            fecha_actual_obj = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                            e_fecha = cols_edit[0].date_input("Modificar Deadline", fecha_actual_obj)
                        else:
                            fecha_actual_obj = datetime.strptime(t['fecha'], "%Y-%m-%d").date()
                            e_fecha = cols_edit[0].date_input("Modificar Fecha", fecha_actual_obj)
                        
                        e_estado = cols_edit[1].selectbox("Estado", ["Pendiente", "Completada"], index=0 if t['estado']=="Pendiente" else 1)
                        e_prioridad = st.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], index=["Normal", "Importante", "Urgente"].index(t.get('prioridad', 'Normal')))
                        
                        col_save, col_del = st.columns([1, 4])
                        if col_save.form_submit_button("💾 Actualizar"):
                            t['titulo'] = e_titulo
                            t['estado'] = e_estado
                            t['prioridad'] = e_prioridad
                            # Actualizar fecha según el tipo
                            if es_deadline:
                                t['fecha_fin'] = str(e_fecha)
                            else:
                                t['fecha'] = str(e_fecha)
                                
                            if gestionar_tareas('actualizar', tarea_actualizada=t):
                                st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "✏️ Tarea actualizada en GitHub."}
                            else:
                                st.session_state["mensaje_global"] = {"tipo": "error", "texto": "❌ Error al actualizar en GitHub."}
                            st.rerun()
                            
                    if st.button("🗑️ Borrar Tarea", key=f"del_{t['id']}"):
                        if gestionar_tareas('borrar', id_tarea_eliminar=t['id']):
                            st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "🗑️ Tarea eliminada de GitHub."}
                        else:
                            st.session_state["mensaje_global"] = {"tipo": "error", "texto": "❌ Error al borrar en GitHub."}
                        st.rerun()

if __name__ == "__main__":
    main()
