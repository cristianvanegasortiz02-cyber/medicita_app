from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import CambiarContrasenaForm, LoginForm, PerfilForm, RegistroForm


class LoginView(auth_views.LoginView):
    template_name = "usuarios/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


def registro(request):
    if request.user.is_authenticated:
        return redirect("panel")
    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("registro_exito")
    return render(request, "usuarios/registro.html", {"form": form})


def registro_exito(request):
    return render(request, "usuarios/registro_exito.html")


@login_required
def panel(request):
    return render(request, "usuarios/panel.html")


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tu perfil fue actualizado.")
        return redirect("perfil")
    u = request.user
    return render(request, "form_generico.html", {
        "titulo": "Mi perfil", "form": form, "volver_url": reverse("panel"), "boton": "Guardar cambios",
        "info": [f"Correo: {u.email}", f"Documento: {u.documento}", f"Rol: {u.get_rol_display()}"],
        "enlace_extra_url": reverse("cambiar_contrasena"), "enlace_extra_texto": "Cambiar contraseña",
    })


@login_required
def cambiar_contrasena(request):
    form = CambiarContrasenaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)
        messages.success(request, "Tu contraseña fue actualizada.")
        return redirect("perfil")
    return render(request, "form_generico.html", {
        "titulo": "Cambiar contraseña", "form": form, "volver_url": reverse("perfil"), "boton": "Cambiar contraseña",
    })
