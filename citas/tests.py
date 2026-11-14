from datetime import time, timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Usuario

from .models import (Cita, Especialidad, Horario, HorarioNoDisponible, OperacionInvalida,
                     PoliticaCita, PoliticaIncumplida, ProfesionalSalud)

CLAVE = "ClaveSegura123"
R = Usuario.Rol


def crear_usuario(n, rol=R.PACIENTE):
    return Usuario.objects.create_user(email=f"u{n}@test.com", password=CLAVE, first_name=f"Nombre{n}",
                                       last_name="Test", documento=str(1000 + n), rol=rol)


class CitasBase(TestCase):
    def setUp(self):
        cache.clear()
        self.medico = crear_usuario(90, R.PROFESIONAL)
        self.prof = ProfesionalSalud.objects.create(usuario=self.medico)
        self.esp = Especialidad.objects.create(nombre="Medicina general")
        self.prof.especialidades.add(self.esp)
        self.horario = self.nuevo_horario(1, 8)
        self.p1, self.p2 = crear_usuario(1), crear_usuario(2)

    def nuevo_horario(self, dias, hora, estado=Horario.Estado.DISPONIBLE):
        return Horario.objects.create(
            profesional=self.prof, fecha=timezone.localdate() + timedelta(days=dias),
            hora_inicio=time(hora, 0), hora_fin=time(hora, 30), estado=estado)


# ------------------------------------------------------------------ PB-03 y PB-04
class RegistrarCitaTests(CitasBase):
    def test_registrar_reserva_el_horario(self):
        cita = Cita.registrar(self.p1, self.horario.pk, self.esp, "Control")
        self.horario.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.PROGRAMADA)
        self.assertEqual(self.horario.estado, Horario.Estado.RESERVADO)

    def test_doble_reserva_se_rechaza(self):
        Cita.registrar(self.p1, self.horario.pk, self.esp)
        with self.assertRaises(HorarioNoDisponible):
            Cita.registrar(self.p2, self.horario.pk, self.esp)
        self.assertEqual(Cita.objects.filter(horario=self.horario).count(), 1)

    def test_restriccion_de_base_de_datos_impide_dos_citas_activas(self):
        Cita.objects.create(paciente=self.p1, horario=self.horario, especialidad=self.esp)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cita.objects.create(paciente=self.p2, horario=self.horario, especialidad=self.esp)

    def test_horario_pasado_no_esta_disponible(self):
        self.horario.fecha = timezone.localdate() - timedelta(days=1)
        self.horario.save()
        with self.assertRaises(HorarioNoDisponible):
            Cita.registrar(self.p1, self.horario.pk, self.esp)


# ------------------------------------------------------------------ PB-05
class CancelarReprogramarTests(CitasBase):
    def setUp(self):
        super().setUp()
        PoliticaCita.objects.create(nombre="Estándar", horas_min_anticipacion=24, max_reprogramaciones=1)
        self.h5, self.h6, self.h7 = self.nuevo_horario(5, 9), self.nuevo_horario(6, 9), self.nuevo_horario(7, 9)
        self.cita = Cita.registrar(self.p1, self.h5.pk, self.esp)

    def test_cancelar_libera_el_horario(self):
        self.cita.cancelar("No puedo asistir")
        self.h5.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.Estado.CANCELADA)
        self.assertEqual(self.cita.motivo_cancelacion, "No puedo asistir")
        self.assertEqual(self.h5.estado, Horario.Estado.DISPONIBLE)

    def test_cancelar_rechazada_por_politica(self):
        PoliticaCita.objects.update(horas_min_anticipacion=24 * 30)
        with self.assertRaises(PoliticaIncumplida):
            self.cita.cancelar()
        self.cita.refresh_from_db()
        self.h5.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.Estado.PROGRAMADA)
        self.assertEqual(self.h5.estado, Horario.Estado.RESERVADO)

    def test_no_se_cancela_dos_veces(self):
        self.cita.cancelar()
        with self.assertRaises(OperacionInvalida):
            self.cita.cancelar()

    def test_horario_cancelado_puede_reservarse_de_nuevo(self):
        self.cita.cancelar()
        nueva = Cita.registrar(self.p2, self.h5.pk, self.esp)
        self.assertEqual(nueva.horario, self.h5)

    def test_reprogramar_cambia_de_horario(self):
        self.cita.reprogramar(self.h6.pk)
        self.h5.refresh_from_db()
        self.h6.refresh_from_db()
        self.assertEqual(self.cita.horario, self.h6)
        self.assertEqual(self.cita.estado, Cita.Estado.REPROGRAMADA)
        self.assertEqual(self.cita.reprogramaciones, 1)
        self.assertEqual(self.h5.estado, Horario.Estado.DISPONIBLE)
        self.assertEqual(self.h6.estado, Horario.Estado.RESERVADO)

    def test_reprogramar_respeta_el_maximo_de_la_politica(self):
        self.cita.reprogramar(self.h6.pk)
        with self.assertRaises(PoliticaIncumplida):
            self.cita.reprogramar(self.h7.pk)
        self.assertEqual(self.cita.horario, self.h6)

    def test_reprogramar_a_horario_ocupado_se_rechaza(self):
        Cita.registrar(crear_usuario(3), self.h6.pk, self.esp)
        with self.assertRaises(HorarioNoDisponible):
            self.cita.reprogramar(self.h6.pk)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.horario, self.h5)

    def test_confirmar_cita(self):
        self.cita.confirmar()
        self.assertEqual(self.cita.estado, Cita.Estado.CONFIRMADA)


# ------------------------------------------------------------------ vistas del paciente
class VistasPacienteTests(CitasBase):
    def test_horarios_solo_muestra_disponibles_filtrados(self):
        self.nuevo_horario(1, 9, Horario.Estado.RESERVADO)
        self.client.force_login(self.p1)
        r = self.client.get(reverse("horarios"), {"especialidad": self.esp.pk})
        self.assertEqual(list(r.context["horarios"]), [self.horario])

    def test_flujo_completo_registra_cita(self):
        self.client.force_login(self.p1)
        r = self.client.post(reverse("cita_nueva"), {"horario": self.horario.pk, "especialidad": self.esp.pk,
                                                    "motivo": "Control general"})
        cita = Cita.objects.get()
        self.assertRedirects(r, reverse("cita_confirmacion", args=[cita.pk]))

    def test_segunda_persona_ve_mensaje_de_horario_ocupado(self):
        Cita.registrar(self.p1, self.horario.pk, self.esp)
        self.client.force_login(self.p2)
        r = self.client.post(reverse("cita_nueva"), {"horario": self.horario.pk, "especialidad": self.esp.pk})
        self.assertContains(r, "Este horario ya fue reservado")
        self.assertEqual(Cita.objects.count(), 1)

    def test_confirmacion_solo_visible_para_su_paciente(self):
        cita = Cita.registrar(self.p1, self.horario.pk, self.esp)
        self.client.force_login(self.p2)
        r = self.client.get(reverse("cita_confirmacion", args=[cita.pk]))
        self.assertEqual(r.status_code, 404)

    def test_historial_muestra_las_citas_con_su_estado(self):
        Cita.registrar(self.p1, self.horario.pk, self.esp)
        self.client.force_login(self.p1)
        r = self.client.get(reverse("mis_citas"))
        self.assertContains(r, "Programada")

    def test_cancelar_desde_la_vista(self):
        h = self.nuevo_horario(5, 9)
        cita = Cita.registrar(self.p1, h.pk, self.esp)
        self.client.force_login(self.p1)
        r = self.client.post(reverse("cita_cancelar", args=[cita.pk]), {"causa": "Viaje"})
        self.assertRedirects(r, reverse("mis_citas"))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CANCELADA)

    def test_cancelar_fuera_de_politica_informa_la_causa(self):
        PoliticaCita.objects.create(nombre="Estricta", horas_min_anticipacion=24 * 30, max_reprogramaciones=1)
        h = self.nuevo_horario(5, 9)
        cita = Cita.registrar(self.p1, h.pk, self.esp)
        self.client.force_login(self.p1)
        r = self.client.post(reverse("cita_cancelar", args=[cita.pk]), {})
        self.assertContains(r, "La política exige al menos")
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.PROGRAMADA)

    def test_reprogramar_desde_la_vista(self):
        h5, h6 = self.nuevo_horario(5, 9), self.nuevo_horario(6, 9)
        cita = Cita.registrar(self.p1, h5.pk, self.esp)
        self.client.force_login(self.p1)
        r = self.client.post(reverse("cita_reprogramar", args=[cita.pk]), {"horario": h6.pk})
        self.assertRedirects(r, reverse("cita_confirmacion", args=[cita.pk]))
        cita.refresh_from_db()
        self.assertEqual(cita.horario, h6)

    def test_paciente_no_puede_gestionar_citas_de_otro(self):
        h = self.nuevo_horario(5, 9)
        cita = Cita.registrar(self.p1, h.pk, self.esp)
        self.client.force_login(self.p2)
        r = self.client.post(reverse("cita_cancelar", args=[cita.pk]), {})
        self.assertEqual(r.status_code, 404)


# ------------------------------------------------------------------ HU-04
class PersonalAdministrativoTests(CitasBase):
    def setUp(self):
        super().setUp()
        self.staff = crear_usuario(50, R.PERSONAL)
        self.client.force_login(self.staff)

    def test_debe_buscar_primero_al_paciente(self):
        r = self.client.get(reverse("horarios"))
        self.assertRedirects(r, reverse("paciente_buscar"))

    def test_registra_cita_en_nombre_del_paciente(self):
        self.client.post(reverse("paciente_buscar"), {"documento": self.p1.documento})
        r = self.client.post(reverse("cita_nueva"), {"horario": self.horario.pk, "especialidad": self.esp.pk})
        cita = Cita.objects.get()
        self.assertEqual(cita.paciente, self.p1)
        self.assertEqual(cita.gestionada_por, self.staff)
        self.assertRedirects(r, reverse("cita_confirmacion", args=[cita.pk]))

    def test_documento_inexistente(self):
        r = self.client.post(reverse("paciente_buscar"), {"documento": "no-existe"})
        self.assertContains(r, "No existe un paciente")

    def test_confirmar_cita_como_personal(self):
        cita = Cita.registrar(self.p1, self.horario.pk, self.esp)
        self.client.post(reverse("paciente_buscar"), {"documento": self.p1.documento})
        self.client.post(reverse("cita_confirmar", args=[cita.pk]))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

    def test_un_paciente_no_entra_a_buscar_pacientes(self):
        self.client.force_login(self.p1)
        r = self.client.get(reverse("paciente_buscar"))
        self.assertRedirects(r, reverse("panel"))


# ------------------------------------------------------------------ PB-06
class AgendaTests(CitasBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.medico)

    def datos(self, ini="10:00", fin="10:30", dias=3):
        return {"fecha": (timezone.localdate() + timedelta(days=dias)).isoformat(), "hora_inicio": ini, "hora_fin": fin}

    def test_profesional_agrega_horario(self):
        r = self.client.post(reverse("agenda"), self.datos())
        self.assertRedirects(r, reverse("agenda"))
        self.assertEqual(Horario.objects.filter(profesional=self.prof).count(), 2)

    def test_horario_que_se_cruza_se_rechaza(self):
        self.client.post(reverse("agenda"), self.datos())
        r = self.client.post(reverse("agenda"), self.datos("10:15", "10:45"))
        self.assertContains(r, "se cruza")
        self.assertEqual(Horario.objects.filter(profesional=self.prof).count(), 2)

    def test_hora_fin_debe_ser_posterior(self):
        r = self.client.post(reverse("agenda"), self.datos("11:00", "10:00"))
        self.assertContains(r, "posterior")

    def test_no_elimina_horario_reservado(self):
        Cita.registrar(self.p1, self.horario.pk, self.esp)
        self.client.post(reverse("agenda_eliminar", args=[self.horario.pk]))
        self.assertTrue(Horario.objects.filter(pk=self.horario.pk).exists())

    def test_elimina_horario_libre(self):
        self.client.post(reverse("agenda_eliminar", args=[self.horario.pk]))
        self.assertFalse(Horario.objects.filter(pk=self.horario.pk).exists())

    def test_paciente_no_accede_a_la_agenda(self):
        self.client.force_login(self.p1)
        self.assertRedirects(self.client.get(reverse("agenda")), reverse("panel"))


# ------------------------------------------------------------------ PB-07, PB-09, PB-10
class GestionTests(CitasBase):
    def setUp(self):
        super().setUp()
        self.admin = crear_usuario(60, R.ADMIN)
        self.client.force_login(self.admin)

    def test_solo_una_politica_vigente(self):
        for nombre in ("A", "B"):
            self.client.post(reverse("politica_nueva"), {
                "nombre": nombre, "horas_min_anticipacion": 12, "max_reprogramaciones": 3, "activa": "on"})
        self.assertEqual(PoliticaCita.objects.filter(activa=True).count(), 1)
        self.assertEqual(PoliticaCita.vigente().nombre, "B")

    def test_registra_especialidad(self):
        self.client.post(reverse("especialidades"), {"nombre": "Pediatría", "descripcion": "Niños"})
        self.assertTrue(Especialidad.objects.filter(nombre="Pediatría").exists())

    def test_registra_profesional_con_especialidades(self):
        r = self.client.post(reverse("profesional_nuevo"), {
            "first_name": "Rosa", "last_name": "Mejía", "documento": "777", "email": "rosa@test.com",
            "password": CLAVE, "registro_profesional": "RM-9", "especialidades": [self.esp.pk]})
        self.assertRedirects(r, reverse("profesionales"))
        usuario = Usuario.objects.get(email="rosa@test.com")
        self.assertEqual(usuario.rol, R.PROFESIONAL)
        self.assertEqual(list(usuario.perfil_profesional.especialidades.all()), [self.esp])

    def test_inactiva_y_activa_usuarios(self):
        self.client.post(reverse("usuario_estado", args=[self.p1.pk]))
        self.p1.refresh_from_db()
        self.assertFalse(self.p1.is_active)
        self.client.post(reverse("usuario_estado", args=[self.p1.pk]))
        self.p1.refresh_from_db()
        self.assertTrue(self.p1.is_active)

    def test_no_puede_inactivarse_a_si_mismo(self):
        self.client.post(reverse("usuario_estado", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_cambia_el_rol_y_crea_perfil_profesional(self):
        self.client.post(reverse("usuario_rol", args=[self.p1.pk]), {"rol": R.PROFESIONAL})
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.rol, R.PROFESIONAL)
        self.assertTrue(ProfesionalSalud.objects.filter(usuario=self.p1).exists())

    def test_usuario_inactivo_no_inicia_sesion(self):
        self.p1.is_active = False
        self.p1.save()
        self.client.logout()
        r = self.client.post(reverse("login"), {"username": self.p1.email, "password": CLAVE})
        self.assertContains(r, "Correo o contraseña incorrectos")

    def test_quien_no_es_admin_no_accede(self):
        self.client.force_login(self.p1)
        self.assertRedirects(self.client.get(reverse("politicas")), reverse("panel"))
        self.assertRedirects(self.client.get(reverse("gestion_usuarios")), reverse("panel"))
