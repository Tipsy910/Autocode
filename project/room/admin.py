from django.contrib import admin,messages
from .models import Room, Assignment, SubmissionType, Announcement, AnnouncementFile,AIConfiguration, AIModelOption
from django.utils.html import format_html 
from django.urls import reverse
from django.utils import timezone
from .utils import test_ai_connection # อย่าลืม import ฟังก์ชันเทสที่เราเคยเขียน
from django.shortcuts import redirect
from .forms import AIConfigurationForm

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

@admin.register(AIModelOption)
class AIModelOptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_value', 'is_active')
    search_fields = ('name', 'api_value')


@admin.register(AIConfiguration)
class AIConfigurationAdmin(admin.ModelAdmin):
    # =========================================================
    # 1. Configuration (ส่วนตั้งค่าพื้นฐาน)
    # =========================================================
    form = AIConfigurationForm
    change_form_template = 'admin/room/aiconfiguration/change_form.html'
    change_list_template = 'admin/room/aiconfiguration/change_list.html'
    
    list_display = ('current_model', 'is_active', 'show_connection_status', 'last_checked_at')
    list_filter = ('is_active', 'last_status_ok')
    ordering = ('-is_active', '-updated_at')
    
    # =========================================================
    # 2. View Overrides (ส่วนแทรกแซงการแสดงผลหน้าเว็บ)
    # =========================================================
    
    # แทรกข้อมูล active_config ไปที่หน้า List (เพื่อแสดง Banner ด้านบน)
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        active_config = AIConfiguration.objects.filter(is_active=True).first()
        extra_context['active_config'] = active_config
        return super().changelist_view(request, extra_context=extra_context)

    # =========================================================
    # 3. Save Logic (ส่วนจัดการข้อมูลตอนบันทึก)
    # =========================================================

    # Logic: "เลือก 1 แล้วปิดที่เหลือ"
    def save_model(self, request, obj, form, change):
        if obj.is_active:
            # สั่งปิดตัวอื่นทั้งหมด ยกเว้นตัวที่กำลังเซฟ
            AIConfiguration.objects.exclude(pk=obj.pk).update(is_active=False)
            messages.info(request, f"ระบบได้ปรับ {obj.current_model} เป็นตัวหลัก และปิดตัวอื่นให้แล้ว")

        super().save_model(request, obj, form, change)

    # =========================================================
    # 4. Button Handlers (ส่วนจัดการปุ่ม Custom)
    # =========================================================

    # ดักจับปุ่มกดในหน้า "แก้ไข"
    def response_change(self, request, obj):
        if "_test_connection" in request.POST:
            return self.perform_test_and_save(request, obj)
        return super().response_change(request, obj)

    # ดักจับปุ่มกดในหน้า "เพิ่มใหม่"
    def response_add(self, request, obj, post_url_continue=None):
        if "_test_connection" in request.POST:
            return self.perform_test_and_save(request, obj)
        return super().response_add(request, obj, post_url_continue)

    # ฟังก์ชันช่วย Test Connection (Helper Function)
    def perform_test_and_save(self, request, obj):
        
        # 1. ตรวจสอบว่าเลือก Model หรือยัง
        if not obj.current_model:
            self.message_user(request, "กรุณาเลือกโมเดลก่อนทดสอบ", level=messages.WARNING)
            # กลับไปหน้าเดิม
            return redirect(request.path)

        # =====================================================
        # ✅ [UPDATED] ดักจับว่าต้องเป็น Gemini เท่านั้น
        # =====================================================
        try:
            # ดึงค่า api_value มาเช็ค (เช่น 'gemini-1.5-flash', 'gpt-4o')
            # ใช้ .lower() เพื่อให้แน่ใจว่าตัวพิมพ์เล็ก/ใหญ่ไม่มีผล
            model_val = obj.current_model.api_value.lower() if obj.current_model.api_value else ""
            
            if "gemini" not in model_val:
                self.message_user(
                    request, 
                    f"⛔ ไม่สามารถทดสอบได้: ระบบปัจจุบันรองรับเฉพาะ Google Gemini แต่คุณเลือก '{obj.current_model.name}'", 
                    level=messages.ERROR
                )
                # ดีดกลับไปหน้าเดิมทันที ไม่รัน test_ai_connection
                return redirect(request.path)
                
        except AttributeError:
            # เผื่อกรณี Model ไม่มี field api_value (กัน Error)
            pass

        # 2. รันการทดสอบ (ถ้าผ่านเงื่อนไข Gemini มาแล้ว)
        # ส่ง API Key และ Model Name ไปเทส
        success, result_msg = test_ai_connection(obj.api_key, obj.current_model.api_value)

        # 3. บันทึกผลลัพธ์ลง Database
        obj.last_status_ok = success
        obj.last_checked_at = timezone.now()
        # ใช้ update_fields เพื่อ Save แค่ 2 คานี้ ไม่กระทบข้อมูลอื่น
        obj.save(update_fields=['last_status_ok', 'last_checked_at'])

        # 4. ส่งข้อความแจ้งเตือน (Banner บนหน้าเว็บ)
        if success:
            self.message_user(request, f"✅ {obj.current_model.name}: {result_msg}", level=messages.SUCCESS)
        else:
            self.message_user(request, f"❌ {obj.current_model.name}: {result_msg}", level=messages.ERROR)
        
        # 5. Redirect กลับมาที่หน้า "แก้ไข" ของ object นี้
        opts = obj._meta
        change_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_change', args=[obj.pk])
        
        return redirect(change_url)

    # =========================================================
    # 5. Display Methods (ส่วนตกแต่งตาราง)
    # =========================================================

    # สร้างป้าย Badge สถานะ
    def show_connection_status(self, obj):
        if obj.last_status_ok:
            return format_html(
                '<span style="background-color:#28a745; color:white; padding:5px 12px; border-radius:20px; font-weight:bold; font-size:12px;">✅ พร้อมใช้งาน</span>'
            )
        elif obj.last_checked_at is None:
            return format_html(
                '<span style="background-color:#6c757d; color:white; padding:5px 12px; border-radius:20px; font-size:12px;">⚪ รอการตรวจสอบ</span>'
            )
        else:
            return format_html(
                '<span style="background-color:#dc3545; color:white; padding:5px 12px; border-radius:20px; font-weight:bold; font-size:12px;">❌ เชื่อมต่อไม่ได้</span>'
            )
    
    show_connection_status.short_description = "สถานะ API"

    # แก้ไขชื่อฟังก์ชันที่พิมพ์ตกหล่น (tory_permission -> has_history_permission)
    def has_history_permission(self, request, obj=None):
        return False