from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    UserDetailView,
    LogoutView,
    DepartmentListView,
    UserListView,
    UserDetailManageView,
    AdminDashboardStatsView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', UserDetailView.as_view(), name='user-detail'),
    path('departments/', DepartmentListView.as_view(), name='department-list'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailManageView.as_view(), name='user-detail-manage'),
    path('dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
]