from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from usuarios.models import Usuario
from usuarios.permisos import rol_requerido

from .forms import EspecialidadForm, PoliticaForm, ProfesionalCrearForm, ProfesionalEditarForm
from .models import Especialidad, PoliticaCita, ProfesionalSalud

ADMIN = Usuario.Rol.ADMIN


def _pagina_form(request, form, titulo, volver, boton="Guardar", info=None):
    return render(request, "form_generico.html", {
        "titulo": titulo, "form": form, "volver_url": volver, "boton": boton, "info": info or []})


# ---------------------------------------------------------------- políticas (PB-07)
@rol_requerido(ADMIN)
def politicas(request):
    return render(request, "gestion/politicas.html", {
        "politicas": PoliticaCita.objects.all(),
        "hay_vigente": PoliticaCita.objects.filter(activa=True).exists(),
    })


@rol_requerido(ADMIN)
def politica_form(request, pk=None):
    politica = get_object_or_404(PoliticaCita, pk=pk) if pk else None
    form = PoliticaForm(request.POST or None, instance=politica)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Política guardada.")
        return redirect("politicas")
    return _pagina_form(
        request, form, "Editar política" if politica else "Nueva política", reverse("politicas"),
        info=["Solo una política está vigente: al activar una, las demás se desactivan."])


# ---------------------------------------------------------------- especialidades (PB-09)
@rol_requerido(ADMIN)
def especialidades(request):
    form = EspecialidadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Especialidad registrada.")
        return redirect("especialidades")
    return render(request, "gestion/especialidades.html", {
        "especialidades": Especialidad.objects.prefetch_related("profesionales__usuario"), "form": form})


@rol_requerido(ADMIN)
def especialidad_editar(request, pk):
    especialidad = get_object_or_404(Especialidad, pk=pk)
    form = EspecialidadForm(request.POST or None, instance=especialidad)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Especialidad actualizada.")
        return redirect("especialidades")
    return _pagina_form(request, form, "Editar especialidad", reverse("especialidades"))


# ---------------------------------------------------------------- profesionales (PB-09)
@rol_requerido(ADMIN)
def profesionales(request):
    lista = ProfesionalSalud.objects.select_related("usuario").prefetch_related("especialidades")
    return render(request, "gestion/profesionales.html", {"profesionales": lista})


@rol_requerido(ADMIN)
def profesional_nuevo(request):
    form = ProfesionalCrearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profesional registrado y asociado a sus especialidades.")
        return redirect("profesionales")
    if not Especialidad.objects.exists():
        messages.info(request, "Primero registra al menos una especialidad.")
    return _pagina_form(request, form, "Registrar profesional", reverse("profesionales"), boton="Registrar")


@rol_requerido(ADMIN)
def profesional_editar(request, pk):
    perfil = get_object_or_404(ProfesionalSalud.objects.select_related("usuario"), pk=pk)
    form = ProfesionalEditarForm(request.POST or None, instance=perfil)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profesional actualizado.")
        return redirect("profesionales")
    return _pagina_form(request, form, f"Editar: {perfil}", reverse("profesionales"))


# ---------------------------------------------------------------- usuarios (PB-10)
@rol_requerido(ADMIN)
def usuarios_lista(request):
    q = request.GET.get("q", "").strip()
    rol = request.GET.get("rol", "")
    lista = Usuario.objects.order_by("first_name", "last_name")
    if q:
        lista = lista.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q)
                             | Q(email__icontains=q) | Q(documento__icontains=q))
    if rol in Usuario.Rol.values:
        lista = lista.filter(rol=rol)
    return render(request, "gestion/usuarios.html", {
        "usuarios": lista, "roles": Usuario.Rol.choices, "q": q, "rol_sel": rol})


@require_POST
@rol_requerido(ADMIN)
def usuario_estado(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes inactivar tu propia cuenta.")
    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        messages.success(request, f"{usuario} ahora está {'activo' if usuario.is_active else 'inactivo'}.")
    return redirect("gestion_usuarios")


@require_POST
@rol_requerido(ADMIN)
def usuario_rol(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    nuevo = request.POST.get("rol", "")
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes cambiar tu propio rol.")
    elif nuevo not in Usuario.Rol.values:
        messages.error(request, "Rol no válido.")
    else:
        usuario.rol = nuevo
        usuario.save(update_fields=["rol"])
        if nuevo == Usuario.Rol.PROFESIONAL:
            ProfesionalSalud.objects.get_or_create(usuario=usuario)
        messages.success(request, f"El rol de {usuario} ahora es {usuario.get_rol_display()}.")
    return redirect("gestion_usuarios")
