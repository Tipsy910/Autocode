# /project/users/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import User, Students, Teachers
from .forms import StudentProfileImageForm, TeacherProfileImageForm # <-- Import ฟอร์มใหม่
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.contrib.auth.views import( PasswordChangeView, PasswordChangeDoneView,PasswordResetView, 
    PasswordResetDoneView, 
    PasswordResetConfirmView, 
    PasswordResetCompleteView)
@login_required
def profile_view(request):
    user = request.user
    profile = None
    ImageForm = None # ตัวแปรสำหรับเก็บคลาสฟอร์มที่ถูกต้อง

    # ตรวจสอบ role เพื่อดึงโปรไฟล์และเลือกฟอร์มที่ถูกต้อง
    if user.role == User.Roles.STUDENT and hasattr(user, 'student_profile'):
        profile = user.student_profile
        ImageForm = StudentProfileImageForm
    elif user.role == User.Roles.TEACHER and hasattr(user, 'teacher_profile'):
        profile = user.teacher_profile
        ImageForm = TeacherProfileImageForm

    if request.method == 'POST' and ImageForm:
        # --- ส่วนจัดการการอัปโหลดรูป (POST request) ---
        form = ImageForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('users:profile') # กลับมาที่หน้าโปรไฟล์
    else:
        # --- ส่วนแสดงผลปกติ (GET request) ---
        form = ImageForm() if ImageForm else None

    context = {
        'user': user,
        'profile': profile,
        'image_form': form, # <-- ส่งฟอร์มไปให้ Template
    }
    return render(request, 'users/profile.html', context)

class MyPasswordChangeView(PasswordChangeView):
    template_name = 'users/password_change.html' # ระบุไฟล์ HTML ที่คุณสร้างไว้
    success_url = reverse_lazy('password_change_done') # ทำเสร็จแล้วไปไหน (ชื่อ URL name)

# ✅ 2. View สำหรับหน้าแจ้งผลสำเร็จ
class MyPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'users/password_change_done.html' # ระบุไฟล์ HTML แจ้งผล

# 1. หน้าแบบฟอร์มขอรีเซ็ตรหัสผ่าน
class MyPasswordResetView(PasswordResetView):
    template_name = 'users/password_reset.html'
    email_template_name = 'users/password_reset_email.html' # เนื้อหาในอีเมล
    success_url = reverse_lazy('users:password_reset_done')

# 2. หน้าแจ้งว่าส่งอีเมลไปแล้ว
class MyPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'users/password_reset_done.html'

# 3. หน้ากรอกรหัสผ่านใหม่ (ลิงก์จากอีเมลจะเด้งมาหน้านี้)
class MyPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'users/password_reset_confirm.html'
    success_url = reverse_lazy('users:password_reset_complete')

# 4. หน้าแจ้งว่าเปลี่ยนรหัสสำเร็จแล้ว
class MyPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'users/password_reset_complete.html'