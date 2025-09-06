import io
import pandas as pd
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from rest_framework import status as request_status
from django.contrib.auth.models import User
from datetime import datetime, timedelta, date
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

class InstructorCourseListView(APIView):
    """
    An endpoint for an authenticated instructor to view a list of
    only the courses they are assigned to.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        instructor = request.user
        
        # Filter the Course model to get only courses where the instructor is the request.user
        courses = Course.objects.filter(instructor=instructor)
        
        # We can reuse the existing CourseSerializer
        serializer = CourseSerializer(courses, many=True)
        
        return generate_request_response(
            message="Assigned courses fetched successfully.",
            data=serializer.data
        )
class ActivityLogView(APIView):
    """
    Endpoint for Instructors to log a new activity or view their past activities.
    """
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        # Instructors can only see their own logs
        logs = ActivityLog.objects.filter(instructor=request.user)
        
        # Add optional filtering support
        activity_type = request.GET.get('activity_type')
        course_id = request.GET.get('course_id')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        if activity_type:
            logs = logs.filter(activity_type=activity_type)
        if course_id:
            logs = logs.filter(course_id=course_id)
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                logs = logs.filter(log_date__date__gte=from_date)
            except ValueError:
                pass  # Invalid date format, ignore filter
        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                logs = logs.filter(log_date__date__lte=to_date)
            except ValueError:
                pass  # Invalid date format, ignore filter
        
        serializer = ActivityLogSerializer(logs, many=True)
        return generate_request_response(message="Activity logs fetched successfully.", data=serializer.data)

    def post(self, request):
        data = request.data
        activity_type = data.get('activity_type')
        course_id = data.get('course_id')
        details = data.get('details', {})  # Default to empty dict
        log_date = data.get('log_date')  # Accept custom log_date

        # Validate activity_type against our Enum
        valid_types = [item.name for item in ActivityTypeEnum]
        if activity_type not in valid_types:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid activity type specified.")
        
        if not course_id:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Course is required.")

        try:
            # An instructor can only log activity for a course they teach
            course = Course.objects.get(id=course_id, instructor=request.user)
            
            # Create log with optional custom date
            log_data = {
                'instructor': request.user,
                'course': course,
                'activity_type': activity_type,
                'details': details
            }
            
            # If log_date is provided, use it (but still auto-set log_date field)
            # The log_date field is auto_now_add, so we'll store custom date in details if needed
            if log_date:
                log_data['details']['custom_log_date'] = log_date
            
            log = ActivityLog.objects.create(**log_data)
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

    # Add PUT and DELETE methods to the same view
    def put(self, request, log_id=None):
        """Update an existing activity log"""
        if not log_id:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Log ID is required.")
        
        try:
            log = ActivityLog.objects.get(id=log_id, instructor=request.user)
            
            data = request.data
            activity_type = data.get('activity_type', log.activity_type)
            course_id = data.get('course_id', log.course.id if log.course else None)
            details = data.get('details', log.details)

            # Validate activity_type
            valid_types = [item.name for item in ActivityTypeEnum]
            if activity_type not in valid_types:
                return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid activity type specified.")
            
            # Validate course
            if course_id:
                course = Course.objects.get(id=course_id, instructor=request.user)
                log.course = course
            
            log.activity_type = activity_type
            log.details = details
            log.save()
            
            serializer = ActivityLogSerializer(log)
            return generate_request_response(message="Activity log updated successfully.", data=serializer.data)
            
        except ActivityLog.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Activity log not found.")
        except Course.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Course not found or you are not assigned to it.")
        except Exception as e:
            return generate_request_response(False, request_status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

    def delete(self, request, log_id=None):
        """Delete an activity log"""
        if not log_id:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Log ID is required.")
        
        try:
            log = ActivityLog.objects.get(id=log_id, instructor=request.user)
            log.delete()
            return generate_request_response(message="Activity log deleted successfully.")
            
        except ActivityLog.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Activity log not found.")
        except Exception as e:
            return generate_request_response(False, request_status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

class ReportListView(APIView):
    """
    Endpoint for users to request a new report or list their existing ones.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
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
        instructor_id = data.get('instructor_id') # New: Get instructor ID

        if not all([report_type, start_date_str, end_date_str]):
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "All fields are required.")

        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except ValueError:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Invalid date format.")

        # --- SYNCHRONOUS REPORT GENERATION ---
        report = Report.objects.create(
            generated_by=request.user, report_type=report_type,
            start_date=start_date, end_date=end_date,
            status=ReportStatusEnum.PROCESSING.name
        )
        SystemEventLog.objects.create(
            actor=request.user,
            event_type=SystemEventTypeEnum.REPORT_GENERATED.name,
            details={'start_date': str(report.start_date), 'report_type': report.report_type, "end_date": str(report.end_date)}
        )

        try:
            # Base query for logs
            logs_query = ActivityLog.objects.filter(log_date__date__range=[start_date, end_date])
            
            # Filter by instructor if an ID is provided and is not 'ALL'
            if instructor_id and instructor_id != 'ALL':
                logs_query = logs_query.filter(instructor_id=instructor_id)
            
            logs = logs_query.values(
                'instructor__username', 'course__course_code', 
                'activity_type', 'log_date', 'details'
            )

            if not logs.exists():
                raise ValueError("No activity data found for the selected criteria.")

            df = pd.DataFrame(list(logs))
            df['log_date'] = pd.to_datetime(df['log_date']).dt.tz_localize(None)
            
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_buffer.seek(0)

            file_name = f'report_{report.id}_{report_type}.xlsx'
            report.generated_file.save(file_name, ContentFile(excel_buffer.read()))
            
            report.status = ReportStatusEnum.COMPLETED.name
            report.save()

            serializer = ReportSerializer(report)
            return generate_request_response(
                status_code=request_status.HTTP_201_CREATED,
                message="Report generated successfully.",
                data=serializer.data
            )
        except Exception as e:
            report.status = ReportStatusEnum.FAILED.name
            report.save()
            return generate_request_response(False, request_status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

    def delete(self, request):
        report_id = request.data.get('id')
        if not report_id:
            return generate_request_response(False, request_status.HTTP_400_BAD_REQUEST, "Report ID is required.")
        
        try:
            report_to_delete = Report.objects.get(pk=report_id)
            # Optional: Add permission check (only admin or creator can delete)
            if request.user.profile.role != 'ADMIN' and report_to_delete.generated_by != request.user:
                 return generate_request_response(False, request_status.HTTP_403_FORBIDDEN, "Permission denied.")
            
            # Delete the associated file from storage if it exists
            if report_to_delete.generated_file:
                report_to_delete.generated_file.delete(save=False)

            report_to_delete.delete()
            return generate_request_response(message="Report deleted successfully.")
        except Report.DoesNotExist:
            return generate_request_response(False, request_status.HTTP_404_NOT_FOUND, "Report not found.")

class InstructorDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsInstructorUser]
    authentication_classes = [TokenAuthentication]
    def get(self, request):
        instructor = request.user
        
        # Calculate stats
        total_activities = ActivityLog.objects.filter(instructor=instructor).count()
        activity_breakdown = ActivityLog.objects.filter(instructor=instructor).values('activity_type').annotate(count=Count('id')).order_by('-count')
        recent_activities = ActivityLog.objects.filter(instructor=instructor)[:5]
        courses_assigned_count = Course.objects.filter(instructor=instructor).count() # DYNAMIC COUNT
        
        # Serialize recent activities (you might need a simple serializer for this)
        recent_activities_data = ActivityLogSerializer(recent_activities, many=True).data

        stats_data = {
            'total_activities': total_activities,
            'activity_breakdown': list(activity_breakdown),
            'recent_activities': recent_activities_data,
            'courses_assigned_count': courses_assigned_count # ADD THIS
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
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            report = Report.objects.get(pk=pk)
            
            # Security check: Only the user who generated it or an admin can download
            # if report.generated_by != request.user and not request.user.profile.role == 'ADMIN':
            #     return generate_request_response(False, request_status.HTTP_403_FORBIDDEN, "You do not have permission.")

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
