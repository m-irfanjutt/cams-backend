# authentication/management/commands/seed_departments.py

from django.core.management.base import BaseCommand
from authentication.models import Department

class Command(BaseCommand):
    help = 'Seeds the database with a list of prominent departments.'

    # Define the list of departments you want to create
    DEPARTMENTS_TO_CREATE = [
        "Computer Science",
        "Software Engineering",
        "Information Technology",
        "Data Science",
        "Cybersecurity",
        "Mathematics",
        "Biology",
        "Engineering",
        "Administration",
        "Physics",
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to seed departments...'))

        departments_created_count = 0
        for dept_name in self.DEPARTMENTS_TO_CREATE:
            # get_or_create checks if a department with this name already exists.
            # If it does, it retrieves it. If not, it creates it.
            # This prevents creating duplicate departments if you run the command multiple times.
            department, created = Department.objects.get_or_create(name=dept_name)
            
            if created:
                departments_created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Successfully created Department: "{dept_name}"'))
            else:
                self.stdout.write(self.style.WARNING(f'Department "{dept_name}" already exists. Skipping.'))
        
        if departments_created_count > 0:
             self.stdout.write(self.style.SUCCESS(f'\nFinished seeding. {departments_created_count} new departments were created.'))
        else:
             self.stdout.write(self.style.SUCCESS('\nFinished seeding. No new departments were created.'))