from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Usuario

CLAVE = "ClaveSegura123"


class AutenticacionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.paciente = Usuario.objects.create_user(
            email="paciente@test.com", password=CLAVE,
            first_name="Pablo", last_name="Prueba", documento="100",
        )

    def test_login_correcto_lleva_al_panel(self):
        r = self.client.post(reverse("login"), {"username": "paciente@test.com", "password": CLAVE})
        self.assertRedirects(r, reverse("panel"))

    def test_login_incorrecto_muestra_error_y_no_da_acceso(self):
        r = self.client.post(reverse("login"), {"username": "paciente@test.com", "password": "mala"})
        self.assertContains(r, "Correo o contraseña incorrectos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bloqueo_temporal_tras_intentos_fallidos(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "paciente@test.com", "password": "mala"})
        r = self.client.post(reverse("login"), {"username": "paciente@test.com", "password": CLAVE})
        self.assertContains(r, "Demasiados intentos fallidos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_panel_exige_sesion(self):
        r = self.client.get(reverse("panel"))
        self.assertEqual(r.status_code, 302)

    def test_contrasena_se_guarda_cifrada(self):
        self.assertNotEqual(self.paciente.password, CLAVE)
        self.assertTrue(self.paciente.check_password(CLAVE))


class RegistroTests(TestCase):
    datos = {"first_name": "Ana", "last_name": "Lopez", "documento": "200",
             "email": "ana@test.com", "password": CLAVE}

    def test_registro_crea_paciente(self):
        r = self.client.post(reverse("registro"), self.datos)
        self.assertRedirects(r, reverse("registro_exito"))
        u = Usuario.objects.get(email="ana@test.com")
        self.assertEqual(u.rol, Usuario.Rol.PACIENTE)

    def test_correo_duplicado_se_rechaza(self):
        Usuario.objects.create_user(email="ana@test.com", password=CLAVE, documento="999",
                                    first_name="X", last_name="Y")
        r = self.client.post(reverse("registro"), self.datos)
        self.assertContains(r, "Este correo ya está registrado")
        self.assertEqual(Usuario.objects.filter(email="ana@test.com").count(), 1)


class PerfilTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = Usuario.objects.create_user(email="p@test.com", password=CLAVE, first_name="Paco",
                                             last_name="Perez", documento="300")
        self.client.force_login(self.u)

    def test_actualiza_datos_del_perfil(self):
        r = self.client.post(reverse("perfil"), {"first_name": "Francisco", "last_name": "Perez",
                                                 "telefono": "3001234567", "fecha_nacimiento": ""})
        self.assertRedirects(r, reverse("perfil"))
        self.u.refresh_from_db()
        self.assertEqual(self.u.first_name, "Francisco")
        self.assertEqual(self.u.telefono, "3001234567")

    def test_cambia_la_contrasena(self):
        r = self.client.post(reverse("cambiar_contrasena"), {
            "old_password": CLAVE, "new_password1": "NuevaClave456!x", "new_password2": "NuevaClave456!x"})
        self.assertRedirects(r, reverse("perfil"))
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password("NuevaClave456!x"))
