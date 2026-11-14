from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from usuarios.models import Usuario
from usuarios.permisos import rol_requerido

from .forms import HorarioForm
from .models import Cita

PROFESIONAL = Usuario.Rol.PROFESIONAL


def _perfil(request):
    return getattr(request.user, "perfil_profesional", None)


@rol_requerido(PROFESIONAL)
def agenda(request):
    """PB-06 / CU-05: el profesional define y consulta su agenda."""
    perfil = _perfil(request)
    if perfil is None:
        messages.error(request, "Tu usuario no tiene perfil profesional. Contacta al administrador.")
        return redirect("panel")
    form = HorarioForm(request.POST or None, profesional=perfil)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Horario agregado a tu agenda.")
        return redirect("agenda")
    fecha_txt = request.GET.get("fecha", "")
    fecha = parse_date(fecha_txt) if fecha_txt else None
    horarios = perfil.horarios.prefetch_related("citas__paciente")
    horarios = horarios.filter(fecha=fecha) if fecha else horarios.filter(fecha__gte=timezone.localdate())
    filas = []
    for h in horarios:
        activa = next((c for c in h.citas.all() if c.estado in Cita.ESTADOS_ACTIVOS), None)
        filas.append({"horario": h, "cita": activa, "eliminable": h.puede_eliminarse()})
    return render(request, "citas/agenda.html", {"form": form, "filas": filas, "fecha": fecha_txt})


@require_POST
@rol_requerido(PROFESIONAL)
def agenda_eliminar(request, pk):
    perfil = _perfil(request)
    if perfil is None:
        return redirect("panel")
    horario = get_object_or_404(perfil.horarios, pk=pk)
    if horario.puede_eliminarse():
        horario.delete()
        messages.success(request, "Horario eliminado.")
    else:
        messages.error(request, "Este horario está reservado o tiene citas asociadas y no se puede eliminar.")
    return redirect("agenda")
