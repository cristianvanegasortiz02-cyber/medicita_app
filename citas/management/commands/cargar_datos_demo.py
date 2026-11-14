from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from citas.models import Especialidad, Horario, PoliticaCita, ProfesionalSalud
from usuarios.models import Usuario

CLAVE_DEMO = "Demo12345!"


class Command(BaseCommand):
    help = "Carga especialidades, profesionales, horarios, política y usuarios de prueba para cada rol."

    def _usuario(self, email, nombre, apellido, documento, rol, **extra):
        usuario, creado = Usuario.objects.get_or_create(
            email=email, defaults={"first_name": nombre, "last_name": apellido, "documento": documento,
                                   "rol": rol, **extra})
        if creado:
            usuario.set_password(CLAVE_DEMO)
            usuario.save()
        return usuario

    def handle(self, *args, **options):
        esp = {n: Especialidad.objects.get_or_create(nombre=n)[0]
               for n in ["Medicina general", "Pediatría", "Odontología"]}

        if not PoliticaCita.objects.exists():
            PoliticaCita.objects.create(nombre="Política estándar", horas_min_anticipacion=24,
                                        max_reprogramaciones=2, activa=True)

        medicos = [
            ("gomez@medicita.test", "Ana", "Gómez", "1001", "RM-001", ["Medicina general"]),
            ("perez@medicita.test", "Luis", "Pérez", "1002", "RM-002", ["Medicina general", "Pediatría"]),
            ("ruiz@medicita.test", "Mario", "Ruiz", "1003", "RM-003", ["Odontología"]),
        ]
        hoy = timezone.localdate()
        for email, nombre, apellido, doc, reg, especs in medicos:
            usuario = self._usuario(email, nombre, apellido, doc, Usuario.Rol.PROFESIONAL)
            prof, _ = ProfesionalSalud.objects.get_or_create(usuario=usuario, defaults={"registro_profesional": reg})
            prof.especialidades.set([esp[e] for e in especs])
            for dia in range(2, 12):
                fecha = hoy + timedelta(days=dia)
                if fecha.weekday() >= 5:
                    continue
                for hora in range(8, 11):
                    for minuto in (0, 30):
                        inicio = time(hora, minuto)
                        fin = time(hora, 30) if minuto == 0 else time(hora + 1, 0)
                        Horario.objects.get_or_create(
                            profesional=prof, fecha=fecha, hora_inicio=inicio, defaults={"hora_fin": fin})

        self._usuario("paciente@medicita.test", "Paula", "Paciente", "2001", Usuario.Rol.PACIENTE)
        self._usuario("personal@medicita.test", "Pedro", "Recepción", "3001", Usuario.Rol.PERSONAL)
        admin = self._usuario("admin@medicita.test", "Alicia", "Admin", "4001", Usuario.Rol.ADMIN,
                              is_staff=True, is_superuser=True)

        self.stdout.write(self.style.SUCCESS("Datos de prueba listos. Contraseña de todos: " + CLAVE_DEMO))
        self.stdout.write("  Paciente: paciente@medicita.test")
        self.stdout.write("  Personal administrativo: personal@medicita.test")
        self.stdout.write("  Profesional de la salud: gomez@medicita.test")
        self.stdout.write("  Administrador: " + admin.email)
