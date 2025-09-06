from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Department

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']

class ProfileSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    class Meta:
        model = Profile
        fields = ['role', 'department', 'name', 'created_at']

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'last_login', 'profile']