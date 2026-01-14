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
            
            # Fecha de referencia para cálculos (usamos fecha seleccionada o 'hoy' real para urgencia?)
            # El usuario navega con 'fecha_seleccionada', pero la urgencia ("quedan X días") 
            # suele ser relativa a la FECHA ACTUAL REAL, no a la fecha que estás mirando en el calendario.
            # Asumiremos HOY REAL para el cálculo de "quedan días" y urgencia.
            hoy_real = date.today()

            for t in tareas:
                if t.get('estado') == 'Completada':
                    continue
                
                # Calcular datos derivados
                es_urgente_auto = False
                dias_restantes_msg = ""
                delta_dias = 999
                
                if t.get('fecha_fin'):
                    try:
                        d_fin = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                        delta_dias = (d_fin - hoy_real).days
                        
                        if delta_dias < 0:
                            dias_restantes_msg = f"🔴 Venció hace {abs(delta_dias)} días"
                        elif delta_dias == 0:
                            dias_restantes_msg = "🟠 Vence HOY"
                            es_urgente_auto = True # Vence hoy -> Urgente
                        else:
                            dias_restantes_msg = f"⏳ Quedan {delta_dias} días"
                            if delta_dias < 2:
                                es_urgente_auto = True
                    except:
                        pass
                
                # Determinar Prioridad Visual
                prioridad_real = t.get('prioridad', 'Normal')
                if es_urgente_auto:
                    prioridad_visual = "Urgente" 
                    nota_urgencia = "🔥 (Auto-Urgente)"
                else:
                    prioridad_visual = prioridad_real
                    nota_urgencia = ""

                # Objeto enriquecido para visualizar
                t_visual = t.copy()
                t_visual['prioridad_visual'] = prioridad_visual
                t_visual['color'] = COLORES_PRIORIDAD.get(prioridad_visual, "gray")
                t_visual['msg_tiempo'] = dias_restantes_msg
                t_visual['nota_urgencia'] = nota_urgencia
                
                # Clasificar en listas (Según fecha objetivo original)
                fecha_tarea = t.get('fecha') # Fecha inicio/objetivo
                
                # Grupo 1: Tareas programadas ESPECÍFICAMENTE para la fecha seleccionada
                if fecha_tarea == str(fecha_seleccionada):
                    tareas_hoy_list.append(t_visual)
                # Grupo 2: Tareas que NO son de hoy, pero están vivas (tienen fecha fin futura o vigente)
                # Solo las mostramos si estamos viendo HOY en el calendario, para no saturar días pasados/futuros
                elif fecha_seleccionada == hoy_real and t.get('fecha_fin'):
                     # Mostrar si la fecha fin es hoy o futuro (y no está ya en la lista de hoy)
                     # Ojo: si fecha_tarea != hoy, pero fecha_fin >= hoy, es una tarea "en curso"
                     d_fin_obj = datetime.strptime(t['fecha_fin'], "%Y-%m-%d").date()
                     if d_fin_obj >= hoy_real:
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
                st.markdown("### 📅 Programadas para hoy")
                for t in tareas_hoy_list:
                    render_tarea(t)
            
            # Solo mostrar sección "En curso / Pendientes" si estamos viendo el día actual
            if tareas_proximas_list and fecha_seleccionada == hoy_real:
                st.markdown("### 🚑 Próximas Entregas / En Curso")
                # Ordenar por urgencia (fecha fin más cercana)
                tareas_proximas_list.sort(key=lambda x: x.get('fecha_fin') or "9999-12-31")
                for t in tareas_proximas_list:
                    render_tarea(t)


    # --- TAB 2: Añadir Tarea ---
    with tab2:
        st.subheader("Nueva Tarea")
        with st.form("form_nueva_tarea"):
            titulo = st.text_input("Título")
            c1, c2 = st.columns(2)
            fecha = c1.date_input("Fecha Objetivo", date.today())
            fecha_fin = c2.date_input("Deadline / Fecha Fin", None)
            
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
                    "fecha": str(fecha),
                    "fecha_fin": str(fecha_fin) if fecha_fin else None,
                    "prioridad": prioridad,
                    "tipo": tipo,
                    "estado": "Pendiente"
                }
                
                if gestionar_tareas('crear', nueva_tarea=nueva_tarea):
                    st.session_state["mensaje_global"] = {"tipo": "exito", "texto": "💾 Nueva tarea guardada correctamente en GitHub."}
                    st.rerun()
                else:
                    st.error("Error al guardar.") # Fallback si no recarga

    # --- TAB 3: Todas las Tareas (Gestión) ---
    with tab3:
        st.subheader("Gestión Global")
        
        # Convertir a DataFrame para mejor visualización si hay muchas
        if not tareas:
            st.info("No hay tareas registradas.")
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

                with st.expander(f"{t['titulo']} ({t['estado']}) {dias_restantes_str}"):
                    # Formulario de edición
                    with st.form(f"edit_{t['id']}"):
                        e_titulo = st.text_input("Título", t['titulo'])
                        e_estado = st.selectbox("Estado", ["Pendiente", "Completada"], index=0 if t['estado']=="Pendiente" else 1)
                        e_prioridad = st.selectbox("Prioridad", ["Normal", "Importante", "Urgente"], index=["Normal", "Importante", "Urgente"].index(t.get('prioridad', 'Normal')))
                        
                        col_save, col_del = st.columns([1, 4])
                        if col_save.form_submit_button("💾 Actualizar"):
                            t['titulo'] = e_titulo
                            t['estado'] = e_estado
                            t['prioridad'] = e_prioridad
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
