# authentication/views.py
from django.contrib.auth import authenticate
from django.db import transaction
from django.contrib.auth.models import User

from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from rest_framework import status as request_status
# Import our new utility function
from course_activity.utils import generate_request_response
from .models import Profile, Department, RoleEnum
from .serializers import UserSerializer, DepartmentSerializer
from .permissions import IsAdminUser
from course_api.models import ReportTypeEnum, ReportStatusEnum, Report, SystemEventLog, SystemEventTypeEnum

class RegisterView(APIView):
    """
    Handles new user registration using a standardized response format.
    """
    @transaction.atomic
    def post(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        role = data.get('role', RoleEnum.INSTRUCTOR.value) # Default to instructor
        department_id = data.get('department')

        # --- Validation ---
        if not all([username, password, confirm_password, first_name, last_name, role, department_id]):
            return generate_request_response(
                status=False, status_code=request_status.HTTP_400_BAD_REQUEST, message="All fields are required."
            )
        
        if password != confirm_password:
            return generate_request_response(
                status=False, status_code=request_status.HTTP_400_BAD_REQUEST, message="Passwords do not match."
            )
            
        if User.objects.filter(username=username).exists():
            return generate_request_response(
                status=False, status_code=request_status.HTTP_400_BAD_REQUEST, message="Username already exists."
            )
        
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return generate_request_response(
                status=False, status_code=request_status.HTTP_404_NOT_FOUND, message="Selected department not found."
            )

        # --- User and Profile Creation ---
        try:
            user = User.objects.create(
                username=username, email=username, first_name=first_name, last_name=last_name
            )
            user.set_password(password)
            user.save()

            Profile.objects.create(
                user=user, role=role.upper(), name=f"{first_name} {last_name}", department=department
            )
            actor = request.user if request.user.is_authenticated else user
            SystemEventLog.objects.create(
                actor=actor,
                event_type=SystemEventTypeEnum.USER_CREATED.name,
                details={'user_id': user.id, 'username': user.username}
            )

            return generate_request_response(
                status_code=request_status.HTTP_201_CREATED, message="User created successfully."
            )

        except Exception as e:
            return generate_request_response(
                status=False, status_code=request_status.HTTP_500_INTERNAL_SERVER_ERROR, message=str(e)
            )

class LoginView(APIView):
    """
    API endpoint for user login. Returns an auth token on success.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Username and password are required.")

        user = authenticate(username=username, password=password)

        if user is not None:
            token, _ = Token.objects.get_or_create(user=user)
            user_data = UserSerializer(user).data
            response_data = {
                'token': token.key,
                'user': user_data
            }
            return generate_request_response(message="Login successful.", data=response_data)
        else:
            return generate_request_response(False, request_status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")

class UserDetailView(APIView):
    """
    API endpoint to fetch details of the currently authenticated user.
    """
    permission_classes = [IsAuthenticated] # Only authenticated users can access this
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return generate_request_response(message="User details fetched successfully.", data=serializer.data)

class LogoutView(APIView):
    """
    API endpoint to log out a user by deleting their auth token.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]


    def post(self, request):
        try:
            # request.user.auth_token is a shortcut provided by DRF
            request.user.auth_token.delete()
            return generate_request_response(message="Successfully logged out.")
        except Exception as e:
            return generate_request_response(False, request_status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

class DepartmentListView(APIView):
    """
    API endpoint to list all available departments for dropdowns.
    """
    permission_classes = [AllowAny] # Anyone can see the list of departments

    def get(self, request):
        departments = Department.objects.all()
        serializer = DepartmentSerializer(departments, many=True)
        return generate_request_response(message="Departments fetched successfully.", data=serializer.data)


class UserListView(APIView):
    """
    Endpoint for Admins to list all user accounts.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # Using prefetch_related to optimize the query and avoid N+1 problem
        users = User.objects.prefetch_related('profile__department').all()
        serializer = UserSerializer(users, many=True)
        return generate_request_response(message="Users fetched successfully.", data=serializer.data)

class UserDetailManageView(APIView):
    """
    Endpoint for Admins to retrieve or update a specific user's details.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get_user_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self.get_user_object(pk)
        if user is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "User not found.")
        
        serializer = UserSerializer(user)
        return generate_request_response(message="User details fetched successfully.", data=serializer.data)

    @transaction.atomic
    def put(self, request, pk):
        user = self.get_user_object(pk)
        if user is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "User not found.")

        data = request.data
        profile = user.profile

        # Update User model fields
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.is_active = data.get('is_active', user.is_active)

        # Update Profile model fields
        profile.role = data.get('role', profile.role).upper()
        department_id = data.get('department_id')
        if department_id:
            try:
                profile.department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Department not found.")
        
        # Save both objects
        user.save()
        profile.save()
        SystemEventLog.objects.create(
            actor=request.user,
            event_type=SystemEventTypeEnum.USER_UPDATED.name,
            details={'user_id': user.id, 'username': user.username}
        )

        serializer = UserSerializer(user)
        return generate_request_response(message="User updated successfully.", data=serializer.data)

    def delete(self, request, pk):
        user = self.get_user_object(pk)
        if user is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "User not found.")
        
        username = user.username
        user.delete()

        # Log this event
        SystemEventLog.objects.create(
            actor=request.user,
            event_type=SystemEventTypeEnum.USER_DELETED.name,
            details={'username': username}
        )
        return generate_request_response(status_code=request_status.HTTP_204_NO_CONTENT, message="User deleted successfully.")

class AdminDashboardStatsView(APIView):
    """
    Endpoint for Admins to fetch aggregated statistics for the dashboard.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # 1. Total Users
        total_users = User.objects.count()

        # 2. Active Instructors
        active_instructors = User.objects.filter(
            is_active=True, 
            profile__role=RoleEnum.INSTRUCTOR.value
        ).count()

        # 3. Reports Generated (we'll count completed reports)
        reports_generated = Report.objects.filter(status=ReportStatusEnum.COMPLETED.name).count()

        # 4. System Performance / Uptime
        # This metric is typically provided by external monitoring tools or hosting platforms (e.g., AWS CloudWatch).
        # It's not something the Django application can calculate itself.
        # We will return a mock value and assume the frontend knows how to display it.
        system_uptime = 99.9  # Mock value

        # Assemble the data into a dictionary
        stats_data = {
            'total_users': total_users,
            'active_instructors': active_instructors,
            'reports_generated': reports_generated,
            'system_performance': {
                'uptime_percentage': system_uptime
            }
        }

        return generate_request_response(
            message="Dashboard statistics fetched successfully.",
            data=stats_data
        )

