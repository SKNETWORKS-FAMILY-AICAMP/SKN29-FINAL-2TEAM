from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "관리자"
    PM = "PM", "프로젝트 관리자"
    MEMBER = "MEMBER", "구성원"


class User(AbstractUser):
    """플랫폼 사용자. People DB의 Person과는 별도이며 선택적으로 연결한다."""

    display_name = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.MEMBER)

    def __str__(self) -> str:
        return self.display_name or self.username
