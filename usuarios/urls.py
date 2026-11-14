from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.LoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", views.registro, name="registro"),
    path("registro/exito/", views.registro_exito, name="registro_exito"),
    path("panel/", views.panel, name="panel"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/contrasena/", views.cambiar_contrasena, name="cambiar_contrasena"),
]
