from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El correo es obligatorio.")
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **extra)
        usuario.set_password(password)  # RNF-03: se guarda el hash, no el texto plano
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("rol", "ADMIN")
        return self._crear(email, password, **extra)


class Usuario(AbstractUser):
    """Clase Usuario del diagrama de clases; el rol distingue a los cuatro actores."""

    class Rol(models.TextChoices):
        PACIENTE = "PACIENTE", "Paciente"
        PROFESIONAL = "PROFESIONAL", "Profesional de la salud"
        PERSONAL = "PERSONAL", "Personal administrativo"
        ADMIN = "ADMIN", "Administrador del sistema"

    username = None
    email = models.EmailField("correo electrónico", unique=True)
    documento = models.CharField("documento de identidad", max_length=20, unique=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    fecha_nacimiento = models.DateField("fecha de nacimiento", null=True, blank=True)
    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.PACIENTE)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "documento"]

    objects = UsuarioManager()

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def es_paciente(self):
        return self.rol == self.Rol.PACIENTE
