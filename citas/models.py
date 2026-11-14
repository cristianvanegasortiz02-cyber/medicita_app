from datetime import datetime

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class HorarioNoDisponible(Exception):
    """El horario no existe, ya fue reservado o ya pasó (CU-03, flujos 4a y 4b)."""


class PoliticaIncumplida(Exception):
    """La operación no cumple la política vigente (CU-03, flujo 5a; RF-07)."""


class OperacionInvalida(Exception):
    """La cita no se encuentra en un estado que permita la operación."""


class Especialidad(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "especialidades"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ProfesionalSalud(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        limit_choices_to={"rol": "PROFESIONAL"}, related_name="perfil_profesional",
    )
    registro_profesional = models.CharField(max_length=30, blank=True)
    especialidades = models.ManyToManyField(Especialidad, related_name="profesionales", blank=True)

    class Meta:
        verbose_name = "profesional de la salud"
        verbose_name_plural = "profesionales de la salud"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.email


class HorarioQuerySet(models.QuerySet):
    def futuros(self):
        """Horarios cuya hora de inicio aún no ha pasado."""
        ahora = timezone.localtime()
        return self.filter(Q(fecha__gt=ahora.date()) | Q(fecha=ahora.date(), hora_inicio__gt=ahora.time()))


class Horario(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        RESERVADO = "RESERVADO", "Reservado"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"

    profesional = models.ForeignKey(ProfesionalSalud, on_delete=models.CASCADE, related_name="horarios")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.DISPONIBLE)

    objects = HorarioQuerySet.as_manager()

    class Meta:
        ordering = ["fecha", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(fields=["profesional", "fecha", "hora_inicio"], name="horario_unico_por_profesional"),
        ]

    def __str__(self):
        return f"{self.profesional} · {self.fecha:%d/%m/%Y} {self.hora_inicio:%H:%M}"

    @property
    def inicio(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora_inicio))

    def esta_disponible(self):
        """CU-09: el horario puede reservarse si está disponible y su hora de inicio no ha pasado."""
        return self.estado == self.Estado.DISPONIBLE and self.inicio > timezone.now()

    def reservar(self):
        self.estado = self.Estado.RESERVADO
        self.save(update_fields=["estado"])

    def liberar(self):
        self.estado = self.Estado.DISPONIBLE
        self.save(update_fields=["estado"])

    def puede_eliminarse(self):
        """HU-05: un horario reservado (o con citas asociadas) no se elimina directamente."""
        return self.estado != self.Estado.RESERVADO and not self.citas.exists()


class PoliticaCita(models.Model):
    """Política de cancelación y reprogramación (RF-06, RF-07)."""

    nombre = models.CharField(max_length=80)
    horas_min_anticipacion = models.PositiveIntegerField("anticipación mínima (horas)", default=24)
    max_reprogramaciones = models.PositiveIntegerField("máximo de reprogramaciones", default=2)
    activa = models.BooleanField("vigente", default=True)

    class Meta:
        verbose_name = "política de citas"
        verbose_name_plural = "políticas de citas"
        ordering = ["-activa", "-id"]

    def __str__(self):
        return self.nombre

    @classmethod
    def vigente(cls):
        """La política activa; si no existe ninguna se usa una predeterminada (24 h y 2 reprogramaciones)."""
        return cls.objects.filter(activa=True).order_by("-id").first() or cls(
            nombre="Predeterminada", horas_min_anticipacion=24, max_reprogramaciones=2)

    def causa_incumplimiento(self, cita, accion):
        """Devuelve la causa por la que la cita no cumple la política, o '' si la cumple."""
        horas = (cita.horario.inicio - timezone.now()).total_seconds() / 3600
        if horas <= 0:
            return "La cita ya comenzó o ya pasó."
        if horas < self.horas_min_anticipacion:
            return (f"La política exige al menos {self.horas_min_anticipacion} horas de anticipación "
                    f"y la cita es en {int(horas)} horas.")
        if accion == "reprogramar" and cita.reprogramaciones >= self.max_reprogramaciones:
            return f"La cita ya alcanzó el máximo de {self.max_reprogramaciones} reprogramaciones permitidas."
        return ""

    def validar(self, cita, accion):
        causa = self.causa_incumplimiento(cita, accion)
        if causa:
            raise PoliticaIncumplida(causa)


class Cita(models.Model):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        REPROGRAMADA = "REPROGRAMADA", "Reprogramada"
        CANCELADA = "CANCELADA", "Cancelada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    ESTADOS_ACTIVOS = ["PROGRAMADA", "CONFIRMADA", "REPROGRAMADA"]

    paciente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="citas")
    horario = models.ForeignKey(Horario, on_delete=models.PROTECT, related_name="citas")
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT, related_name="citas")
    motivo = models.CharField(max_length=200, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PROGRAMADA)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    reprogramaciones = models.PositiveIntegerField(default=0)
    motivo_cancelacion = models.CharField(max_length=200, blank=True)
    gestionada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="citas_gestionadas",
    )

    class Meta:
        ordering = ["-fecha_registro"]
        constraints = [
            # RNF-04: a nivel de base de datos, un horario solo admite una cita activa.
            models.UniqueConstraint(
                fields=["horario"], condition=Q(estado__in=["PROGRAMADA", "CONFIRMADA", "REPROGRAMADA"]),
                name="una_cita_activa_por_horario",
            ),
        ]

    def __str__(self):
        return f"Cita #{self.pk} · {self.paciente} · {self.horario}"

    @property
    def es_activa(self):
        return self.estado in self.ESTADOS_ACTIVOS

    def cumple_politica(self, politica, accion="cancelar"):
        return not politica.causa_incumplimiento(self, accion)

    # ------------------------------------------------------------------ registrar
    @classmethod
    def registrar(cls, paciente, horario_id, especialidad, motivo="", gestionada_por=None):
        """Registra una cita validando la disponibilidad (CU-03 + CU-09, PB-03 y PB-04).

        Se bloquea la fila del horario dentro de una transacción para que dos
        solicitudes simultáneas no puedan reservar el mismo horario (RNF-04).
        """
        with transaction.atomic():
            try:
                horario = Horario.objects.select_for_update().get(pk=horario_id)
            except Horario.DoesNotExist:
                raise HorarioNoDisponible("El horario no existe.")
            if not horario.esta_disponible():
                raise HorarioNoDisponible("El horario ya fue reservado.")
            if not horario.profesional.especialidades.filter(pk=especialidad.pk).exists():
                raise HorarioNoDisponible("El profesional no atiende esa especialidad.")
            horario.reservar()
            return cls.objects.create(
                paciente=paciente, horario=horario, especialidad=especialidad,
                motivo=motivo, estado=cls.Estado.PROGRAMADA, gestionada_por=gestionada_por,
            )

    # ------------------------------------------------------------------ confirmar
    def confirmar(self):
        with transaction.atomic():
            cita = Cita.objects.select_for_update().get(pk=self.pk)
            if cita.estado not in (self.Estado.PROGRAMADA, self.Estado.REPROGRAMADA):
                raise OperacionInvalida("Solo se pueden confirmar citas programadas o reprogramadas.")
            cita.estado = self.Estado.CONFIRMADA
            cita.save(update_fields=["estado"])
        self.refresh_from_db()

    # ------------------------------------------------------------------ cancelar
    def cancelar(self, causa="", politica=None):
        """PB-05: cancela la cita si cumple la política vigente y libera el horario."""
        with transaction.atomic():
            cita = Cita.objects.select_for_update().select_related("horario").get(pk=self.pk)
            if not cita.es_activa:
                raise OperacionInvalida("La cita ya no está activa.")
            (politica or PoliticaCita.vigente()).validar(cita, "cancelar")
            horario = Horario.objects.select_for_update().get(pk=cita.horario_id)
            horario.liberar()
            cita.estado = self.Estado.CANCELADA
            cita.motivo_cancelacion = causa
            cita.save(update_fields=["estado", "motivo_cancelacion"])
        self.refresh_from_db()

    # ------------------------------------------------------------------ reprogramar
    def reprogramar(self, nuevo_horario_id, politica=None):
        """PB-05: pasa la cita a otro horario si cumple la política y el nuevo horario está libre."""
        with transaction.atomic():
            cita = Cita.objects.select_for_update().select_related("horario").get(pk=self.pk)
            if not cita.es_activa:
                raise OperacionInvalida("La cita ya no está activa.")
            ids = sorted({cita.horario_id, nuevo_horario_id})
            bloqueados = {h.pk: h for h in Horario.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
            nuevo = bloqueados.get(nuevo_horario_id)
            if nuevo is None or nuevo.pk == cita.horario_id:
                raise HorarioNoDisponible("Elige un horario distinto al actual.")
            if not nuevo.esta_disponible():
                raise HorarioNoDisponible("El horario ya fue reservado.")
            if not nuevo.profesional.especialidades.filter(pk=cita.especialidad_id).exists():
                raise HorarioNoDisponible("El profesional no atiende esa especialidad.")
            (politica or PoliticaCita.vigente()).validar(cita, "reprogramar")
            bloqueados[cita.horario_id].liberar()
            nuevo.reservar()
            cita.horario = nuevo
            cita.estado = self.Estado.REPROGRAMADA
            cita.reprogramaciones += 1
            cita.save(update_fields=["horario", "estado", "reprogramaciones"])
        self.refresh_from_db()
