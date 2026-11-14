from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from usuarios.models import Usuario
from usuarios.permisos import rol_requerido

from .models import (Cita, Especialidad, Horario, HorarioNoDisponible, OperacionInvalida,
                     PoliticaCita, PoliticaIncumplida)

PACIENTE = Usuario.Rol.PACIENTE
PERSONAL = Usuario.Rol.PERSONAL
MENSAJE_OCUPADO = "Este horario ya fue reservado. Elige otro horario."
RELACIONES = ("horario__profesional__usuario", "especialidad")


def _pk(valor):
    return int(valor) if str(valor).isdigit() else 0


def paciente_objetivo(request):
    """Paciente sobre el que se trabaja: el propio usuario, o el elegido por el personal (HU-04)."""
    usuario = request.user
    if usuario.rol == PACIENTE:
        return usuario
    if usuario.rol == PERSONAL:
        pk = request.session.get("paciente_gestionado")
        if pk:
            return Usuario.objects.filter(pk=pk, rol=PACIENTE, is_active=True).first()
    return None


def _paciente_o_redirigir(request):
    paciente = paciente_objetivo(request)
    if paciente:
        return paciente, None
    if request.user.rol == PERSONAL:
        messages.info(request, "Primero busca al paciente por su documento.")
        return None, redirect("paciente_buscar")
    return None, redirect("panel")


# ---------------------------------------------------------------- personal administrativo
@rol_requerido(PERSONAL)
def paciente_buscar(request):
    error = ""
    if request.method == "POST":
        documento = request.POST.get("documento", "").strip()
        paciente = Usuario.objects.filter(documento=documento, rol=PACIENTE, is_active=True).first()
        if paciente:
            request.session["paciente_gestionado"] = paciente.pk
            return redirect("mis_citas")
        error = "No existe un paciente con ese documento."
    return render(request, "citas/paciente_buscar.html", {"error": error})


@require_POST
@rol_requerido(PERSONAL)
def paciente_cambiar(request):
    request.session.pop("paciente_gestionado", None)
    return redirect("paciente_buscar")


# ---------------------------------------------------------------- consulta y registro
@rol_requerido(PACIENTE, PERSONAL)
def horarios(request):
    """P-05 / PB-02: horarios disponibles filtrados por especialidad y fecha."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    esp_id = request.GET.get("especialidad", "")
    fecha_txt = request.GET.get("fecha", "")
    lista = []
    if esp_id.isdigit():
        lista = (Horario.objects.futuros()
                 .filter(estado=Horario.Estado.DISPONIBLE, profesional__especialidades__id=esp_id)
                 .select_related("profesional__usuario"))
        fecha = parse_date(fecha_txt) if fecha_txt else None
        if fecha:
            lista = lista.filter(fecha=fecha)
        lista = lista[:50]
    return render(request, "citas/horarios.html", {
        "especialidades": Especialidad.objects.all(), "esp_id": esp_id, "fecha": fecha_txt,
        "horarios": lista, "buscado": bool(esp_id),
    })


@rol_requerido(PACIENTE, PERSONAL)
def cita_nueva(request):
    """P-06 / PB-03 y PB-04: confirmar la cita validando que el horario siga disponible."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    datos = request.POST if request.method == "POST" else request.GET
    horario = get_object_or_404(Horario.objects.select_related("profesional__usuario"), pk=_pk(datos.get("horario")))
    especialidad = get_object_or_404(Especialidad, pk=_pk(datos.get("especialidad")))
    error = None
    if request.method == "POST":
        gestor = request.user if request.user.rol == PERSONAL else None
        try:
            cita = Cita.registrar(paciente, horario.pk, especialidad,
                                  motivo=request.POST.get("motivo", "").strip(), gestionada_por=gestor)
            return redirect("cita_confirmacion", pk=cita.pk)
        except HorarioNoDisponible:
            error = MENSAJE_OCUPADO
    elif not horario.esta_disponible():
        error = MENSAJE_OCUPADO
    return render(request, "citas/cita_nueva.html", {
        "horario": horario, "especialidad": especialidad, "error": error,
        "motivo": datos.get("motivo", ""), "paciente": paciente,
    })


@rol_requerido(PACIENTE, PERSONAL)
def cita_confirmacion(request, pk):
    """P-07: la cita registrada (o reprogramada) con su estado."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    cita = get_object_or_404(Cita.objects.select_related(*RELACIONES), pk=pk, paciente=paciente)
    return render(request, "citas/cita_confirmacion.html", {"cita": cita})


# ---------------------------------------------------------------- historial y gestión
@rol_requerido(PACIENTE, PERSONAL)
def mis_citas(request):
    """PB-08 / CU-04: historial de citas con su estado actual."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    estado = request.GET.get("estado", "")
    citas = paciente.citas.select_related(*RELACIONES).order_by("-horario__fecha", "-horario__hora_inicio")
    if estado in Cita.Estado.values:
        citas = citas.filter(estado=estado)
    return render(request, "citas/mis_citas.html", {
        "citas": citas, "estados": Cita.Estado.choices, "estado_sel": estado, "paciente": paciente,
    })


@rol_requerido(PACIENTE, PERSONAL)
def cita_cancelar(request, pk):
    """PB-05: cancelar una cita validando la política vigente."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    cita = get_object_or_404(Cita.objects.select_related(*RELACIONES), pk=pk, paciente=paciente)
    politica = PoliticaCita.vigente()
    error = "Esta cita ya no está activa." if not cita.es_activa else politica.causa_incumplimiento(cita, "cancelar")
    if request.method == "POST" and not error:
        try:
            cita.cancelar(causa=request.POST.get("causa", "").strip())
            messages.success(request, "La cita fue cancelada.")
            return redirect("mis_citas")
        except (PoliticaIncumplida, OperacionInvalida) as e:
            error = str(e)
    return render(request, "citas/cita_cancelar.html", {"cita": cita, "politica": politica, "error": error})


@rol_requerido(PACIENTE, PERSONAL)
def cita_reprogramar(request, pk):
    """PB-05: reprogramar una cita a otro horario validando la política vigente."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    cita = get_object_or_404(Cita.objects.select_related(*RELACIONES), pk=pk, paciente=paciente)
    politica = PoliticaCita.vigente()
    bloqueo = "Esta cita ya no está activa." if not cita.es_activa else politica.causa_incumplimiento(cita, "reprogramar")
    error = ""
    if request.method == "POST" and not bloqueo:
        try:
            cita.reprogramar(_pk(request.POST.get("horario")))
            messages.success(request, "La cita fue reprogramada.")
            return redirect("cita_confirmacion", pk=cita.pk)
        except HorarioNoDisponible:
            error = MENSAJE_OCUPADO
        except (PoliticaIncumplida, OperacionInvalida) as e:
            error = str(e)
    disponibles = []
    fecha_txt = request.GET.get("fecha", "")
    if not bloqueo:
        disponibles = (Horario.objects.futuros()
                       .filter(estado=Horario.Estado.DISPONIBLE, profesional__especialidades=cita.especialidad)
                       .exclude(pk=cita.horario_id).select_related("profesional__usuario"))
        fecha = parse_date(fecha_txt) if fecha_txt else None
        if fecha:
            disponibles = disponibles.filter(fecha=fecha)
        disponibles = disponibles[:50]
    return render(request, "citas/cita_reprogramar.html", {
        "cita": cita, "politica": politica, "bloqueo": bloqueo, "error": error,
        "horarios": disponibles, "fecha": fecha_txt,
    })


@require_POST
@rol_requerido(PERSONAL)
def cita_confirmar(request, pk):
    """RF-03: el personal administrativo confirma una cita programada o reprogramada."""
    paciente, respuesta = _paciente_o_redirigir(request)
    if respuesta:
        return respuesta
    cita = get_object_or_404(Cita, pk=pk, paciente=paciente)
    try:
        cita.confirmar()
        messages.success(request, "La cita fue confirmada.")
    except OperacionInvalida as e:
        messages.error(request, str(e))
    return redirect("mis_citas")
