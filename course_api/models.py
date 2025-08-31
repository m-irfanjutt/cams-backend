import enum
from django.db import models
from django.contrib.auth.models import User

# --- Enums for Choices ---

class ActivityTypeEnum(enum.Enum):
    MDB_REPLY = 'MDB Replies'
    TICKET_RESPONSE = 'Ticket Responses'
    ASSIGNMENT_UPLOAD = 'Assignment Upload'
    ASSIGNMENT_MARKING = 'Assignment Marking'
    GDB_MARKING = 'GDB Marking'
    SESSION_TRACKING = 'Session Tracking'
    EMAIL_RESPONSE = 'Email Responses'
    
    @classmethod
    def choices(cls):
        return [(key.name, key.value) for key in cls]

class ReportTypeEnum(enum.Enum):
    ACTIVITY_SUMMARY = 'Activity Summary'
    PERFORMANCE_ANALYSIS = 'Instructor Performance Analysis'
    SYSTEM_USAGE = 'System Usage Report'
    
    @classmethod
    def choices(cls):
        return [(key.name, key.value) for key in cls]

class ReportStatusEnum(enum.Enum):
    PENDING = 'Pending'
    COMPLETED = 'Completed'
    FAILED = 'Failed'

    @classmethod
    def choices(cls):
        return [(key.name, key.value) for key in cls]

# --- Models ---

class Course(models.Model):
    course_code = models.CharField(max_length=20, unique=True)
    course_title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    instructor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='courses_taught')

    def __str__(self):
        return f"{self.course_code}: {self.course_title}"

class ActivityLog(models.Model):
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=30, choices=ActivityTypeEnum.choices())
    log_date = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, help_text="e.g., {'topic': 'Week 1 Intro', 'count': 15}")
    
    class Meta:
        ordering = ['-log_date']

    def __str__(self):
        return f"{self.activity_type} by {self.instructor.username} on {self.log_date.strftime('%Y-%m-%d')}"

class Report(models.Model):
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    report_type = models.CharField(max_length=30, choices=ReportTypeEnum.choices())
    status = models.CharField(max_length=10, choices=ReportStatusEnum.choices(), default=ReportStatusEnum.PENDING.name)
    start_date = models.DateField()
    end_date = models.DateField()
    generated_file = models.FileField(upload_to='reports/', null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.report_type} from {self.start_date} to {self.end_date}"

class SystemEventTypeEnum(enum.Enum):
    USER_CREATED = "User Account Created"
    USER_UPDATED = "User Account Updated"
    USER_DELETED = "User Account Deleted"
    REPORT_GENERATED = "Report Generated"
    COURSE_CREATED = "Course Created"
    
    @classmethod
    def choices(cls):
        return [(key.name, key.value) for key in cls]

class SystemEventLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, help_text="The user who performed the action.")
    event_type = models.CharField(max_length=30, choices=SystemEventTypeEnum.choices())
    details = models.JSONField(default=dict, help_text="Details of the event, e.g., {'username': 'johndoe'}")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.event_type} by {self.actor.username if self.actor else 'System'} at {self.timestamp}"