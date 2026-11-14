from django import forms
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from usuarios.forms import BootstrapMixin
from usuarios.models import Usuario

from .models import Especialidad, Horario, PoliticaCita, ProfesionalSalud


class HorarioForm(BootstrapMixin, forms.ModelForm):
    """PB-06: el profesional define un horario con fecha, hora de inicio y hora de fin."""

    class Meta:
        model = Horario
        fields = ["fecha", "hora_inicio", "hora_fin"]
        labels = {"fecha": "Fecha", "hora_inicio": "Hora de inicio", "hora_fin": "Hora de fin"}
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_inicio": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_fin": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, profesional=None, **kwargs):
        self.profesional = profesional
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        fecha, ini, fin = datos.get("fecha"), datos.get("hora_inicio"), datos.get("hora_fin")
        if fecha and ini and fin:
            if fin <= ini:
                raise forms.ValidationError("La hora de fin debe ser posterior a la hora de inicio.")
            if fecha < timezone.localdate():
                raise forms.ValidationError("No se pueden definir horarios en fechas pasadas.")
            cruce = Horario.objects.filter(profesional=self.profesional, fecha=fecha,
                                           hora_inicio__lt=fin, hora_fin__gt=ini).exists()
            if cruce:
                raise forms.ValidationError("Este horario se cruza con otro ya definido.")
        return datos

    def save(self, commit=True):
        horario = super().save(commit=False)
        horario.profesional = self.profesional
        if commit:
            horario.save()
        return horario


class PoliticaForm(BootstrapMixin, forms.ModelForm):
    """PB-07: anticipación mínima y máximo de reprogramaciones."""

    class Meta:
        model = PoliticaCita
        fields = ["nombre", "horas_min_anticipacion", "max_reprogramaciones", "activa"]
        labels = {"nombre": "Nombre", "activa": "Política vigente"}

    def save(self, commit=True):
        politica = super().save(commit=commit)
        if commit and politica.activa:
            PoliticaCita.objects.exclude(pk=politica.pk).update(activa=False)
        return politica


class EspecialidadForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Especialidad
        fields = ["nombre", "descripcion"]
        labels = {"nombre": "Nombre", "descripcion": "Descripción"}


class ProfesionalCrearForm(BootstrapMixin, forms.Form):
    """PB-09: registra un profesional (usuario con rol PROFESIONAL) y sus especialidades."""

    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    documento = forms.CharField(label="Documento de identidad", max_length=20)
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña inicial", widget=forms.PasswordInput)
    registro_profesional = forms.CharField(label="Registro profesional", max_length=30, required=False)
    especialidades = forms.ModelMultipleChoiceField(
        label="Especialidades", queryset=Especialidad.objects.all(), widget=forms.CheckboxSelectMultiple)

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

    @transaction.atomic
    def save(self):
        d = self.cleaned_data
        usuario = Usuario.objects.create_user(
            email=d["email"], password=d["password"], first_name=d["first_name"], last_name=d["last_name"],
            documento=d["documento"], rol=Usuario.Rol.PROFESIONAL)
        perfil = ProfesionalSalud.objects.create(usuario=usuario, registro_profesional=d["registro_profesional"])
        perfil.especialidades.set(d["especialidades"])
        return perfil


class ProfesionalEditarForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProfesionalSalud
        fields = ["registro_profesional", "especialidades"]
        labels = {"registro_profesional": "Registro profesional", "especialidades": "Especialidades"}
        widgets = {"especialidades": forms.CheckboxSelectMultiple}
