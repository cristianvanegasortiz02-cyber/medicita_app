from django.contrib import admin

from .models import Cita, Especialidad, Horario, PoliticaCita, ProfesionalSalud


@admin.register(Especialidad)
class EspecialidadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")


@admin.register(ProfesionalSalud)
class ProfesionalAdmin(admin.ModelAdmin):
    list_display = ("__str__", "registro_profesional")
    filter_horizontal = ("especialidades",)


@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ("profesional", "fecha", "hora_inicio", "hora_fin", "estado")
    list_filter = ("estado", "fecha", "profesional")


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ("id", "paciente", "horario", "especialidad", "estado", "fecha_registro")
    list_filter = ("estado", "especialidad")


@admin.register(PoliticaCita)
class PoliticaCitaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "horas_min_anticipacion", "max_reprogramaciones", "activa")
