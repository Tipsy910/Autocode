# ไฟล์: users/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.hashers import make_password
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import CharWidget
from .models import User, Students, Teachers 

# ---------------------------------------------------------
# ส่วนที่ 1: UserResource 
# ---------------------------------------------------------
class UserResource(resources.ModelResource):
    
    # รับค่า 'id' จาก Excel
    personal_id = fields.Field(attribute='personal_id', column_name='id', widget=CharWidget())
    
    # รับค่า 'password'
    password = fields.Field(attribute='password', column_name='password', widget=CharWidget())

    class Meta:
        model = User
        # ระบุ field ที่จะให้บันทึกลง DB (ไม่ต้องมี full_name_temp)
        fields = ('email', 'first_name', 'last_name', 'role', 'personal_id', 'password', 'is_active')
        import_id_fields = ('email',) 
        skip_unchanged = True

    def before_import_row(self, row, **kwargs):
        # 1. จัดการ Email
        email = str(row.get('email', '')).strip().lower()
        row['email'] = email
        
        # 2. จัดการ Password
        raw_password = str(row.get('password', '')).strip()
        if raw_password.endswith('.0'): 
            raw_password = raw_password[:-2]
            
        if raw_password:
            row['password'] = make_password(raw_password)
        
        # 3. แยกชื่อ-นามสกุล
        full_name = str(row.get('name', '')).strip()
        if full_name:
            parts = full_name.split(' ', 1)
            row['first_name'] = parts[0]
            row['last_name'] = parts[1] if len(parts) > 1 else ""

        # 4. จัดการ Role
        role = str(row.get('role', '')).strip().upper()
        valid_roles = ['STUDENT', 'TEACHER', 'ADMIN']
        if role not in valid_roles:
            role = 'STUDENT'
        row['role'] = role

        # 5. เคลียร์ค่า id
        pid = str(row.get('id', '')).strip()
        if pid.endswith('.0'): pid = pid[:-2]
        if pid.lower() == 'none': pid = ""
        row['id'] = pid

        row['is_active'] = True 

    # -----------------------------------------------------------
    # จุดที่แก้คือบรรทัดนี้ครับ 👇 (เติม **kwargs เข้าไป)
    # -----------------------------------------------------------
    def after_save_instance(self, instance, row=None, **kwargs):
        """ สร้าง Profile นักเรียน/อาจารย์ หลังจาก User บันทึกเสร็จแล้ว """
        
        # ดึงค่า dry_run มาจาก kwargs แทนการรับตรงๆ
        dry_run = kwargs.get('dry_run', False)
        
        if dry_run: return 

        full_name_str = f"{instance.first_name} {instance.last_name}".strip()

        if instance.role == "STUDENT":
            Teachers.objects.filter(user=instance).delete()
            Students.objects.update_or_create(user=instance, defaults={"name": full_name_str})
            
        elif instance.role == "TEACHER":
            Students.objects.filter(user=instance).delete()
            Teachers.objects.update_or_create(user=instance, defaults={"name": full_name_str})
            
        else: # ADMIN
            Students.objects.filter(user=instance).delete()
            Teachers.objects.filter(user=instance).delete()


# ---------------------------------------------------------
# ส่วนที่ 2: UserAdmin
# ---------------------------------------------------------
@admin.register(User)
class UserAdmin(ImportExportModelAdmin, BaseUserAdmin):
    resource_class = UserResource

    list_display = ("email", "first_name", "last_name", "personal_id", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("email", "personal_id", "first_name")
    ordering = ("email",)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'personal_id', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password', 'role', 'personal_id', 'first_name', 'last_name'),
        }),
    )

@admin.register(Students)
class StudentsAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_user_email', 'get_student_id')
    search_fields = ('name', 'user__email', 'user__personal_id')
    # เพื่อให้กรองตามห้องเรียนได้
    list_filter = ('joined_rooms',) 

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(role='STUDENT')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_user_email(self, obj):
        return obj.user.email
    get_user_email.short_description = 'Email'

    def get_student_id(self, obj):
        return obj.user.personal_id
    get_student_id.short_description = 'Student ID'

@admin.register(Teachers)
class TeachersAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_user_email')
    search_fields = ('name', 'user__email')
    list_filter = ('taught_rooms',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(role='TEACHER')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_user_email(self, obj):
        return obj.user.email
    get_user_email.short_description = 'Email'