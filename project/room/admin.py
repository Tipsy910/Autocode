from django.contrib import admin
from .models import Room, Assignment, SubmissionType, Announcement, AnnouncementFile
from django.utils.html import format_html 
from django.urls import reverse
from django.utils import timezone

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    # ✅ 1. เพิ่ม 'count_teachers' เข้าไปในรายการโชว์
    list_display = ('name', 'owner_name', 'invite_code', 'link_to_students', 'link_to_teachers', 'link_to_assignments', 'created_at', 'id','link_to_manage')
    
    search_fields = ('name', 'invite_code', 'owner__first_name', 'owner__email','id')
    list_filter = ('created_at','owner')
    
    fieldsets = (
        ("ข้อมูลห้องเรียน", {
            "fields": ("name", "invite_code", "owner", "cover_image")
        }),
        ("จัดการสมาชิก", {
            "classes": ("collapse",),
            "fields": ("students", "teachers"),
        }),
    )
    filter_horizontal = ('students', 'teachers')

    def owner_name(self, obj):
        if obj.owner:
            return f"{obj.owner.first_name} {obj.owner.last_name}" if obj.owner.first_name else obj.owner.email
        return "-"
    owner_name.short_description = "เจ้าของห้อง (Owner)"

    def link_to_students(self, obj):
        count = obj.students.count()
        # สร้าง URL ไปยังหน้า users_students_changelist (ต้องลงทะเบียน Students ใน admin ก่อนนะ)
        url = (
            reverse("admin:users_students_changelist") 
            + f"?joined_rooms__id__exact={obj.id}"
        )
        return format_html('<a href="{}" class="button" style="background-color:#369f36; color:white; padding:3px 8px; border-radius:5px;">📋 {} คน (คลิกดู)</a>', url, count)
    link_to_students.short_description = "นักเรียน"
    link_to_students.allow_tags = True

    # ✅ ฟังก์ชันใหม่: สร้างปุ่มกดไปดูรายชื่ออาจารย์
    def link_to_teachers(self, obj):
        count = obj.teachers.count()
        url = (
            reverse("admin:users_teachers_changelist") 
            + f"?taught_rooms__id__exact={obj.id}"
        )
        return format_html('<a href="{}" style="color:#bf80ff; font-weight:bold;">👨‍🏫 {} คน</a>', url, count)
    link_to_teachers.short_description = "ผู้ช่วยสอน"

    def link_to_assignments(self, obj):
        # นับจำนวน Assignment ที่ field 'room' ตรงกับห้องนี้
        count = Assignment.objects.filter(room=obj).count()
        
        # สร้าง URL ไปหน้า Assignment List แล้วกรองเฉพาะห้องนี้
        # admin:appname_modelname_changelist
        url = (
            reverse("admin:room_assignment_changelist") 
            + f"?room__id__exact={obj.id}"
        )
        
        # แต่งสีส้ม (Orange) ให้ดูแตกต่างจาก นร. และ ครู
        return format_html(
            '<a href="{}" style="color:#e67e22; font-weight:bold;">📚 {} งาน</a>',
            url, 
            count
        )
    link_to_assignments.short_description = "การบ้าน/งาน"

    def link_to_manage(self, obj):
        # สร้าง URL ไปยังหน้าแก้ไข (Change View) ของห้องนี้
        # รูปแบบ: admin:app_model_change
        url = reverse("admin:room_room_change", args=[obj.id])
        
        # แต่งปุ่มสีฟ้าเข้ม ให้ดูเหมือนปุ่ม Setting
        return format_html(
            '<a href="{}" class="button" style="background-color:#417690; color:white; padding:5px 10px; border-radius:5px; text-decoration:none; font-weight:bold;">⚙️ จัดการ (Manage)</a>',
            url
        )
    
    link_to_manage.short_description = "การจัดการ"

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    # ✅ 1. ใช้ชื่อ field ให้ตรงกับ Model (score) และใช้ฟังก์ชัน get_submission_types
    list_display = ('title', 'room', 'get_submission_types', 'score', 'due_date', 'status_label') 
    
    list_filter = ('room',) 
    search_fields = ('title', 'description')
    
    # ✅ 2. จัดกลุ่มข้อมูลในหน้าแก้ไข (Edit Page) ให้ดูง่าย
    fieldsets = (
        ("ข้อมูลงาน (General)", {
            "fields": ("title", "description", "room", "author", "created_at")
        }),
        ("การตั้งค่าการส่งงาน & คะแนน", {
            "fields": ("score", "due_date", "allowed_submission_types", "allow_late_submission"),
        }),
        ("ตั้งค่า AI Quiz (AI Configuration)", {
            "classes": ("collapse",), # ซ่อนไว้ก่อน ถ้าจะแก้ค่อยกดเปิด
            "fields": ("enable_ai_quiz", "problem_file", "test_case_file", "quiz_question_count", "quiz_choice_count", "quiz_time_limit"),
        }),
    )
    
    # เนื่องจาก created_at เป็น auto_now_add ปกติจะแก้ไม่ได้ ต้องสั่งให้อ่านได้อย่างเดียว
    readonly_fields = ('created_at',)
    filter_horizontal = ('allowed_submission_types',) # ทำให้เลือกประเภทไฟล์ง่ายขึ้น (แบบซ้ายขวา)
    list_filter = ('room',)
    search_fields = ('title', 'description')

    # ✅ 3. ฟังก์ชันดึงประเภทไฟล์ (แก้ปัญหา ManyToMany ใน list_display)
    def get_submission_types(self, obj):
        # ดึงชื่อประเภททั้งหมดมาต่อกันด้วย comma
        return ", ".join([t.name for t in obj.allowed_submission_types.all()])
    get_submission_types.short_description = "รูปแบบไฟล์ที่รับ"

    # ✅ 4. ฟังก์ชันเช็คสถานะ (เหมือนเดิม)
    def status_label(self, obj):
        if not obj.due_date:
            return format_html('<span style="color:gray;">- ไม่กำหนด -</span>')
            
        if obj.due_date < timezone.now():
            return format_html('<span style="color:red; font-weight:bold;">❌ ปิดรับ (Closed)</span>')
        else:
            return format_html('<span style="color:green; font-weight:bold;">🟢 เปิดรับ (Active)</span>')
    status_label.short_description = "สถานะ"

# อย่าลืมลงทะเบียน SubmissionType ด้วย จะได้เข้าไปสร้างประเภทไฟล์ได้ (เช่น PDF, Zip, Code)
class AnnouncementFileInline(admin.TabularInline):
    model = AnnouncementFile
    extra = 1

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['id', 'room', 'author', 'created_at']
    list_filter = ['room', 'created_at']
    inlines = [AnnouncementFileInline] # ใส่ไฟล์แนบให้จัดการง่ายๆ

@admin.register(SubmissionType)
class SubmissionTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
