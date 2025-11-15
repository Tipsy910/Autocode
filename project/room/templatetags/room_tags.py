import os
from django import template

register = template.Library()

@register.filter
def split_filename(value):
    """
    รับค่า Path ของไฟล์ (เช่น 'submission_files/test.py')
    และคืนค่าเฉพาะชื่อไฟล์ (เช่น 'test.py')
    """
    if not value:
        return ""
    # ใช้ os.path.basename จะปลอดภัยที่สุด
    return os.path.basename(str(value))