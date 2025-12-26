from django import template
from users.models import Students, Teachers  # Import โมเดลนักเรียน/อาจารย์
from room.models import Room, Assignment     # Import โมเดลห้อง/งาน

register = template.Library()

@register.simple_tag
def get_summary_stats():
    # นับจำนวนข้อมูลจาก Database
    return {
        "students": Students.objects.count(),
        "teachers": Teachers.objects.count(),
        "rooms": Room.objects.count(),
        "assignments": Assignment.objects.count(),
    }