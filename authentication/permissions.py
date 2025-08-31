from rest_framework.permissions import BasePermission
from authentication.models import RoleEnum

class IsAdminUser(BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.profile.role == RoleEnum.ADMIN.value)

class IsInstructorUser(BasePermission):
    """
    Allows access only to instructor users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.profile.role == RoleEnum.INSTRUCTOR.value)