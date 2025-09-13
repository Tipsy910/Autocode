from django.contrib import admin
from .models import Room, Assignment, SubmissionType
# Register your models here.
admin.site.register(Room)
admin.site.register(Assignment)
admin.site.register(SubmissionType)