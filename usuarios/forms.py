from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache

from .models import Usuario

MAX_INTENTOS = 5          # CU-01, flujo A2: intentos fallidos permitidos
BLOQUEO_SEGUNDOS = 300    # y duración del bloqueo temporal (5 minutos)


class BootstrapMixin:
    """Agrega las clases de Bootstrap a los campos de cualquier formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, forms.CheckboxSelectMultiple):
                continue
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs["class"] = "form-select"
            else:
                w.attrs["class"] = "form-control"


class LoginForm(AuthenticationForm):
    """P-01. Error único para credenciales incorrectas (CU-01, A1) y bloqueo temporal (A2)."""

    error_messages = {
        "invalid_login": "Correo o contraseña incorrectos",
        "inactive": "Esta cuenta está inactiva.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Correo electrónico"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "placeholder": "usuario@correo.com", "autofocus": True})
        self.fields["password"].widget.attrs.update({"class": "form-control", "placeholder": "********"})

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def clean(self):
        clave = "login_fallos:" + self.data.get("username", "").strip().lower()
        if cache.get(clave, 0) >= MAX_INTENTOS:
            raise forms.ValidationError(
                "Demasiados intentos fallidos. Intenta de nuevo en 5 minutos.", code="bloqueado")
        try:
            datos = super().clean()
        except forms.ValidationError:
            cache.add(clave, 0, BLOQUEO_SEGUNDOS)
            try:
                cache.incr(clave)
            except ValueError:
                cache.set(clave, 1, BLOQUEO_SEGUNDOS)
            raise
        cache.delete(clave)
        return datos


class RegistroForm(BootstrapMixin, forms.ModelForm):
    """P-02. Registro de pacientes (HU-01)."""

    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "documento", "email"]
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "documento": "Documento de identidad",
            "email": "Correo electrónico",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo ya está registrado")
        return email

    def clean_documento(self):
        documento = self.cleaned_data["documento"].strip()
        if Usuario.objects.filter(documento=documento).exists():
            raise forms.ValidationError("Este documento ya está registrado")
        return documento

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.rol = Usuario.Rol.PACIENTE
        usuario.set_password(self.cleaned_data["password"])
        if commit:
            usuario.save()
        return usuario


class PerfilForm(BootstrapMixin, forms.ModelForm):
    """CU-02. Gestionar perfil de usuario."""

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "telefono", "fecha_nacimiento"]
        labels = {"first_name": "Nombres", "last_name": "Apellidos", "telefono": "Teléfono",
                  "fecha_nacimiento": "Fecha de nacimiento"}
        widgets = {"fecha_nacimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class CambiarContrasenaForm(BootstrapMixin, PasswordChangeForm):
    """CU-02. cambiarContrasena(actual, nueva) del diagrama de clases."""
