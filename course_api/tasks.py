# course_api/tasks.py
from celery import shared_task
from .models import Report, ActivityLog, ReportStatusEnum
import pandas as pd
from django.core.files.base import ContentFile
import io

@shared_task
def generate_activity_report(report_id):
    """
    A Celery task to generate a report file based on activity logs.
    """
    try:
        report = Report.objects.get(id=report_id)
        report.status = ReportStatusEnum.PROCESSING.name # A new status for clarity
        report.save()

        # Fetch the relevant activity logs
        logs = ActivityLog.objects.filter(
            log_date__date__range=[report.start_date, report.end_date]
        ).values('instructor__username', 'course__course_code', 'activity_type', 'log_date', 'details')

        if not logs.exists():
            raise ValueError("No activity data found for the selected period.")

        # Use pandas to create an Excel file in memory
        df = pd.DataFrame(list(logs))
        
        # Create an in-memory byte stream
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0) # Rewind the buffer to the beginning

        # Create a Django ContentFile
        file_name = f'report_{report_id}_{report.report_type}.xlsx'
        report.generated_file.save(file_name, ContentFile(excel_buffer.read()))
        
        # Mark the report as completed
        report.status = ReportStatusEnum.COMPLETED.name
        report.save()

    except Exception as e:
        # If anything goes wrong, mark the report as failed
        if 'report' in locals():
            report.status = ReportStatusEnum.FAILED.name
            report.save()
    
    return f"Report {report_id} processing finished."