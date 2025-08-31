from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Course, ActivityLog, Report, SystemEventLog

# A simplified serializer for user details within other models
class BasicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class CourseSerializer(serializers.ModelSerializer):
    # Show basic instructor details instead of just the ID
    instructor = BasicUserSerializer(read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'course_code', 'course_title', 'description', 'instructor']

class ActivityLogSerializer(serializers.ModelSerializer):
    instructor = BasicUserSerializer(read_only=True)
    # Use a custom field to show the human-readable activity type
    activity_type = serializers.CharField(source='get_activity_type_display')
    # Nest course details within the activity log
    course = CourseSerializer(read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'instructor', 'course', 'activity_type', 'log_date', 'details']

class ReportSerializer(serializers.ModelSerializer):
    generated_by = BasicUserSerializer(read_only=True)
    report_type = serializers.CharField(source='get_report_type_display')
    status = serializers.CharField(source='get_status_display')

    class Meta:
        model = Report
        fields = ['id', 'generated_by', 'report_type', 'status', 'start_date', 'end_date', 'generated_file', 'generated_at']

class SystemEventLogSerializer(serializers.ModelSerializer):
    actor = BasicUserSerializer(read_only=True)
    event_type = serializers.CharField(source='get_event_type_display')

    class Meta:
        model = SystemEventLog
        fields = ['id', 'actor', 'event_type', 'details', 'timestamp']    

