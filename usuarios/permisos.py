from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def rol_requerido(*roles):
    """Permite el acceso solo a los roles indicados (niveles de acceso de la sección 5.3)."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if request.user.rol not in roles:
                messages.error(request, "No tienes permiso para acceder a esa sección.")
                return redirect("panel")
            return vista(request, *args, **kwargs)

        return login_required(envoltura)

    return decorador
