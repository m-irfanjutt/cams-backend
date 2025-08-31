from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework import status as request_status
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404

# Re-use the utility function from the authentication app
from course_activity.utils import generate_request_response
from .models import Course, ActivityLog, ActivityTypeEnum, Report, ReportTypeEnum, SystemEventLog, ReportStatusEnum, SystemEventTypeEnum
from .serializers import CourseSerializer, ActivityLogSerializer, ReportSerializer, SystemEventLogSerializer
from authentication.permissions import IsAdminUser, IsInstructorUser
from course_api.tasks import generate_activity_report

class CourseListView(APIView):
    """
    Endpoint for Admins to list all courses or create a new one.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        courses = Course.objects.all()
        serializer = CourseSerializer(courses, many=True)
        return generate_request_response(message="Courses fetched successfully.", data=serializer.data)

    def post(self, request):
        data = request.data
        course_code = data.get('course_code')
        course_title = data.get('course_title')
        instructor_id = data.get('instructor_id')

        if not all([course_code, course_title, instructor_id]):
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "All fields are required.")

        try:
            instructor = User.objects.get(id=instructor_id, profile__role='INSTRUCTOR')
            course = Course.objects.create(
                course_code=course_code,
                course_title=course_title,
                description=data.get('description', ''),
                instructor=instructor
            )
            SystemEventLog.objects.create(
                actor=request.user,
                event_type=SystemEventTypeEnum.COURSE_CREATED.name,
                details={'course_code': course.course_code, 'course_title': course.course_title}
            )
            serializer = CourseSerializer(course)
            return generate_request_response(
                status_code=request_status.HTTP_201_CREATED,
                message="Course created successfully.",
                data=serializer.data
            )
        except User.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Instructor not found.")
        except Exception as e:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, str(e))


class ActivityLogView(APIView):
    """
    Endpoint for Instructors to log a new activity or view their past activities.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # Instructors can only see their own logs
        logs = ActivityLog.objects.filter(instructor=request.user)
        serializer = ActivityLogSerializer(logs, many=True)
        return generate_request_response(message="Activity logs fetched successfully.", data=serializer.data)

    def post(self, request):
        data = request.data
        activity_type = data.get('activity_type')
        course_id = data.get('course_id')
        details = data.get('details') # Expect a JSON object from the frontend

        # Validate activity_type against our Enum
        valid_types = [item.name for item in ActivityTypeEnum]
        if activity_type not in valid_types:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid activity type specified.")
        
        if not all([course_id, details]):
             return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Course and details are required.")

        try:
            # An instructor can only log activity for a course they teach
            course = Course.objects.get(id=course_id, instructor=request.user)
            log = ActivityLog.objects.create(
                instructor=request.user,
                course=course,
                activity_type=activity_type,
                details=details
            )
            serializer = ActivityLogSerializer(log)
            return generate_request_response(
                status_code=request_status.HTTP_201_CREATED,
                message="Activity logged successfully.",
                data=serializer.data
            )
        except Course.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Course not found or you are not assigned to it.")
        except Exception as e:
            return generate_request_response(False, request_status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


class ReportListView(APIView):
    """
    Endpoint for users to request a new report or list their existing ones.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # Users can only see reports they generated themselves
        reports = Report.objects.filter(generated_by=request.user)
        serializer = ReportSerializer(reports, many=True)
        return generate_request_response(message="Reports fetched successfully.", data=serializer.data)

    def post(self, request):
        data = request.data
        report_type = data.get('report_type')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        if not all([report_type, start_date_str, end_date_str]):
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Report type and date range are required.")

        # Validate report type
        valid_types = [item.name for item in ReportTypeEnum]
        if report_type not in valid_types:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid report type.")

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid date format. Use YYYY-MM-DD.")

        # --- Report Generation Logic ---
        # In a production environment, this is where you would trigger a background task.
        # For example: generate_report_task.delay(user_id, report_type, start_date, end_date)
        # Here, we will just create the report record with a 'PENDING' status.

        report = Report.objects.create(
            generated_by=request.user,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            # Status defaults to PENDING from the model definition
        )
        generate_activity_report.delay(report.id)
        serializer = ReportSerializer(report)
        return generate_request_response(
            status_code=request_status.HTTP_202_ACCEPTED,
            message="Report generation has been queued.",
            data=serializer.data
        )

class InstructorDashboardStatsView(APIView):
    """
    Endpoint for Instructors to fetch statistics for their dashboard.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        instructor = request.user

        # 1. Total activities logged by this instructor
        total_activities = ActivityLog.objects.filter(instructor=instructor).count()

        # 2. Breakdown of activities by type
        activity_breakdown = ActivityLog.objects.filter(instructor=instructor) \
            .values('activity_type') \
            .annotate(count=Count('id')) \
            .order_by('-count')

        # 3. Recent activities (last 5)
        recent_activities = ActivityLog.objects.filter(instructor=instructor)[:5]
        recent_activities_serializer = ActivityLogSerializer(recent_activities, many=True)

        stats_data = {
            'total_activities': total_activities,
            'activity_breakdown': list(activity_breakdown),
            'recent_activities': recent_activities_serializer.data
        }

        return generate_request_response(message="Instructor dashboard stats fetched.", data=stats_data)

class SystemEventLogView(APIView):
    """
    Endpoint for Admins to view a feed of recent system-wide events.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # Fetch the 20 most recent events
        events = SystemEventLog.objects.all()[:20]
        serializer = SystemEventLogSerializer(events, many=True)
        return generate_request_response(message="Recent system activity fetched.", data=serializer.data)

class ReportDownloadView(APIView):
    """
    Endpoint to download a generated report file.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get(self, request, pk):
        try:
            report = Report.objects.get(pk=pk)
            
            # Security check: Only the user who generated it or an admin can download
            if report.generated_by != request.user and not request.user.profile.role == 'ADMIN':
                return generate_request_response(False, request_status.HTTP_403_FORBIDDEN, "You do not have permission.")

            if report.status == ReportStatusEnum.COMPLETED.name and report.generated_file:
                # Use FileResponse to stream the file efficiently
                return FileResponse(report.generated_file.open('rb'), as_attachment=True)
            elif report.status == ReportStatusEnum.FAILED.name:
                return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Report generation failed.")
            else:
                return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Report is still being processed.")

        except Report.DoesNotExist:
            raise Http404

class CourseDetailManageView(APIView):
    """
    Endpoint for Admins to retrieve, update, or delete a specific course.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get_object(self, pk):
        try:
            return Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            return None

    def get(self, request, pk):
        course = self.get_object(pk)
        if course is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Course not found.")
        serializer = CourseSerializer(course)
        return generate_request_response(data=serializer.data)

    def put(self, request, pk):
        course = self.get_object(pk)
        if course is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Course not found.")
        
        # This is a simplified update. You can add more complex logic as needed.
        serializer = CourseSerializer(course, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return generate_request_response(data=serializer.data)
        return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, serializer.errors)

    def delete(self, request, pk):
        course = self.get_object(pk)
        if course is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Course not found.")
        course.delete()
        return generate_request_response(status_code=request_status.HTTP_204_NO_CONTENT, message="Course deleted.")

class AdminAnalyticsView(APIView):
    """
    Endpoint for Admins to fetch aggregated data for analytics charts.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # --- 1. Activity Over Time (Last 30 Days) ---
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        
        activity_over_time = ActivityLog.objects.filter(log_date__date__gte=thirty_days_ago) \
            .annotate(date=TruncDate('log_date')) \
            .values('date') \
            .annotate(count=Count('id')) \
            .order_by('date')

        # --- 2. Activity Breakdown by Type ---
        activity_by_type = ActivityLog.objects.values('activity_type') \
            .annotate(count=Count('id')) \
            .order_by('-count')
            
        # --- 3. Top Performing Instructors (by activity count) ---
        top_instructors = User.objects.filter(profile__role='INSTRUCTOR', is_active=True) \
            .annotate(activity_count=Count('activity_logs')) \
            .order_by('-activity_count') \
            .values('username', 'first_name', 'last_name', 'activity_count')[:5] # Top 5

        analytics_data = {
            'activity_over_time': list(activity_over_time),
            'activity_by_type': list(activity_by_type),
            'top_instructors': list(top_instructors)
        }

        return generate_request_response(message="Analytics data fetched successfully.", data=analytics_data)


class ActivityLogDetailView(APIView):
    """
    Endpoint for an instructor to retrieve, update, or delete a specific activity log.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get_object(self, pk, user):
        try:
            # Ensure the log belongs to the requesting user to prevent unauthorized access
            return ActivityLog.objects.get(pk=pk, instructor=user)
        except ActivityLog.DoesNotExist:
            return None

    def put(self, request, pk):
        log = self.get_object(pk, request.user)
        if log is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Activity log not found.")
        
        # For simplicity, we'll use a serializer for PUT. This can be done manually too.
        serializer = ActivityLogSerializer(log, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return generate_request_response(message="Activity log updated.", data=serializer.data)
        return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, serializer.errors)

    def delete(self, request, pk):
        log = self.get_object(pk, request.user)
        if log is None:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Activity log not found.")
        
        log.delete()
        return generate_request_response(status_code=request_status.HTTP_204_NO_CONTENT, message="Activity log deleted.")

class InstructorPerformanceView(APIView):
    """
    Endpoint for an instructor to fetch their own aggregated performance data.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        instructor = request.user
        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        # 1. Activity Over Time (for this instructor)
        activity_over_time = ActivityLog.objects.filter(
            instructor=instructor,
            log_date__date__gte=thirty_days_ago
        ).annotate(date=TruncDate('log_date')) \
         .values('date') \
         .annotate(count=Count('id')) \
         .order_by('date')

        # 2. Activity Breakdown by Type (for this instructor)
        activity_by_type = ActivityLog.objects.filter(instructor=instructor) \
            .values('activity_type') \
            .annotate(count=Count('id')) \
            .order_by('-count')

        # 3. Activity by Course (for this instructor)
        activity_by_course = ActivityLog.objects.filter(instructor=instructor) \
            .values('course__course_code', 'course__course_title') \
            .annotate(count=Count('id')) \
            .order_by('-count')

        performance_data = {
            'activity_over_time': list(activity_over_time),
            'activity_by_type': list(activity_by_type),
            'activity_by_course': list(activity_by_course)
        }

        return generate_request_response(message="Performance data fetched.", data=performance_data)
