from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import TimeStampedModel


class User(AbstractUser, TimeStampedModel):
    """Single user model for admins and bid managers (specs/02 §1, decision D1)."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "관리자"
        BID_MANAGER = "BID_MANAGER", "입찰담당자"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.BID_MANAGER)
    display_name = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    must_change_password = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser
