from .models import Usuario


def paciente_gestionado(request):
    """Para el personal administrativo: paciente cuyas citas está gestionando (HU-04)."""
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated and usuario.rol == Usuario.Rol.PERSONAL:
        pk = request.session.get("paciente_gestionado")
        if pk:
            return {"paciente_gestionado": Usuario.objects.filter(pk=pk, rol=Usuario.Rol.PACIENTE).first()}
    return {}
