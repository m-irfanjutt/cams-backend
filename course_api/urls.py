from django.urls import path
from .views import CourseListView, ActivityLogView, ReportListView, InstructorDashboardStatsView, SystemEventLogView, CourseDetailManageView, ReportDownloadView, AdminAnalyticsView, ActivityLogDetailView, InstructorPerformanceView, InstructorCourseListView

urlpatterns = [
    # Dashboard URLs
    path('dashboard/instructor/', InstructorDashboardStatsView.as_view(), name='instructor-dashboard'),
    path('dashboard/admin/activity-feed/', SystemEventLogView.as_view(), name='admin-activity-feed'),

    # Course URLs
    path('courses/', CourseListView.as_view(), name='course-list'),
    path('courses/<int:pk>/', CourseDetailManageView.as_view(), name='course-detail'),
    
    path('instructor/courses/', InstructorCourseListView.as_view(), name='instructor-course-list'),
    
    # Activity Log URLs
    path('activities/', ActivityLogView.as_view(), name='activity-log'),
    path('activities/<int:pk>/', ActivityLogDetailView.as_view(), name='activity-log-detail'),
    
    # Report URLs
    path('reports/', ReportListView.as_view(), name='report-list'),
    path('reports/<int:pk>/download/', ReportDownloadView.as_view(), name='report-download'),
    
    path('analytics/admin/', AdminAnalyticsView.as_view(), name='admin-analytics-data'),
    path('performance/instructor/', InstructorPerformanceView.as_view(), name='instructor-performance'),
]