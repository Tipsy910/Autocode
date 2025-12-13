from django.contrib import admin
from .models import Room, Assignment, SubmissionType
from django.db import models  # ต้อง import models เพื่อใช้อ้างอิงชนิด Field
from django.forms import CheckboxSelectMultiple# Register your models here.

admin.site.register(Room)
class AssignmentAdmin(admin.ModelAdmin):
    # ส่วนนี้จะเปลี่ยนหน้าตาของ ManyToMany Field ทุกตัวในหน้านี้ให้เป็น Checkbox
    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }
    
    # กำหนดให้โชว์คอลัมน์อะไรบ้างในหน้ารวม (หน้า List)
    list_display = ('title', 'room', 'score', 'due_date')
    
    # (สำคัญ) ถ้าก่อนหน้านี้เคยมีการกำหนด fieldsets แล้วค้างอยู่ 
    # บรรทัดนี้จะสั่งให้ Django เรียง Field ตามลำดับใน Models.py อัตโนมัติ 
    # และต้องโชว์ allowed_submission_types แน่นอน
    exclude = [] 

# ลงทะเบียน Assignment พร้อมกับ class ที่เราปรับแต่ง
admin.site.register(Assignment, AssignmentAdmin)
admin.site.register(SubmissionType)