# authentication/models.py

import enum
from django.db import models
from django.contrib.auth.models import User

# --- Enums for Choices ---

class RoleEnum(enum.Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"

    @classmethod
    def choices(cls):
        # This creates the tuple list that Django's 'choices' attribute expects
        return [(key.value, key.name.title()) for key in cls]

# --- Models ---

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=200,
        null=True
    )
    # Use the choices() method from our Enum
    role = models.CharField(
        max_length=10,
        choices=RoleEnum.choices(),
        default=RoleEnum.INSTRUCTOR.value
    )
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"