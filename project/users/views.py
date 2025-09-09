# /project/users/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import User, Students, Teachers
from .forms import StudentProfileImageForm, TeacherProfileImageForm # <-- Import ฟอร์มใหม่

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