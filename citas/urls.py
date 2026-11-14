from django.urls import path

from . import views, views_agenda, views_gestion as g

urlpatterns = [
    # paciente y personal administrativo
    path("pacientes/buscar/", views.paciente_buscar, name="paciente_buscar"),
    path("pacientes/cambiar/", views.paciente_cambiar, name="paciente_cambiar"),
    path("horarios/", views.horarios, name="horarios"),
    path("citas/", views.mis_citas, name="mis_citas"),
    path("citas/nueva/", views.cita_nueva, name="cita_nueva"),
    path("citas/<int:pk>/confirmacion/", views.cita_confirmacion, name="cita_confirmacion"),
    path("citas/<int:pk>/cancelar/", views.cita_cancelar, name="cita_cancelar"),
    path("citas/<int:pk>/reprogramar/", views.cita_reprogramar, name="cita_reprogramar"),
    path("citas/<int:pk>/confirmar/", views.cita_confirmar, name="cita_confirmar"),
    # profesional de la salud
    path("agenda/", views_agenda.agenda, name="agenda"),
    path("agenda/<int:pk>/eliminar/", views_agenda.agenda_eliminar, name="agenda_eliminar"),
    # administrador del sistema
    path("gestion/politicas/", g.politicas, name="politicas"),
    path("gestion/politicas/nueva/", g.politica_form, name="politica_nueva"),
    path("gestion/politicas/<int:pk>/editar/", g.politica_form, name="politica_editar"),
    path("gestion/especialidades/", g.especialidades, name="especialidades"),
    path("gestion/especialidades/<int:pk>/editar/", g.especialidad_editar, name="especialidad_editar"),
    path("gestion/profesionales/", g.profesionales, name="profesionales"),
    path("gestion/profesionales/nuevo/", g.profesional_nuevo, name="profesional_nuevo"),
    path("gestion/profesionales/<int:pk>/editar/", g.profesional_editar, name="profesional_editar"),
    path("gestion/usuarios/", g.usuarios_lista, name="gestion_usuarios"),
    path("gestion/usuarios/<int:pk>/estado/", g.usuario_estado, name="usuario_estado"),
    path("gestion/usuarios/<int:pk>/rol/", g.usuario_rol, name="usuario_rol"),
]
