import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'course_activity.settings')
app = Celery('course_activity')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()