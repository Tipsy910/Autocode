from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from users.models import Students
from room.models import Room
from .forms import JoinRoomForm
from room.models import Room, Assignment, Announcement, Submission

@method_decorator(login_required, name='dispatch')
class student_dashboard(View):
    template_name = 'student/dashboard.html'
    
    def get(self, request, *args, **kwargs):
      
        joined_rooms = Room.objects.filter(students__user=request.user)
        form = JoinRoomForm() 
        
        context = {
            'joined_rooms': joined_rooms,
            'form': form,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data.get('invite_code') # แก้จาก code เป็น invite_code ให้ตรงกับ form
            try:
                room = Room.objects.get(invite_code=code) # ใช้ .get() จะเหมาะกับ try-except มากกว่า
                student_profile = Students.objects.get(user=request.user)
                room.students.add(student_profile)
                return redirect(reverse_lazy('student_dashboard')) 
            except Students.DoesNotExist:
                # กรณีนี้ไม่น่าเกิดถ้า user login อยู่ แต่ใส่ไว้ก็ดี
                form.add_error(None, 'ไม่พบโปรไฟล์นักเรียนของคุณ')
            except Room.DoesNotExist:

                form.add_error('invite_code', 'รหัสเข้าร่วมห้องเรียนไม่ถูกต้อง')
        
        # ถ้าย้ายโค้ดส่วนล่างมาไว้ตรงนี้ จะครอบคลุมทั้งกรณี form invalid และกรณี try-except fail
        joined_rooms = Room.objects.filter(students__user=request.user)
        context = {
            'joined_rooms': joined_rooms,
            'form': form, # form ที่มี error message จะถูกส่งกลับไป
        }
        return render(request, self.template_name, context)

@login_required
def student_room_detail_view(request, pk):
    # ดึงข้อมูลห้องเรียน
    room = get_object_or_404(Room, pk=pk)

    # ตรวจสอบสิทธิ์: นักเรียนต้องเป็นสมาชิกของห้องนี้เท่านั้น
    try:
        student_profile = request.user.student_profile
        if not room.students.filter(pk=student_profile.pk).exists():
            # ถ้าไม่ได้เป็นสมาชิก ให้ redirect หรือแสดงข้อผิดพลาด
            return redirect('student:dashboard') # กลับไปหน้า dashboard ของนักเรียน
    except AttributeError:
        # กรณี User ไม่มี student_profile
        return redirect('student:dashboard')

    # ดึงข้อมูลประกาศและงานทั้งหมดในห้อง
    announcements = Announcement.objects.filter(room=room)
    assignments = Assignment.objects.filter(room=room).order_by('-created_at')

    # --- ส่วนสำคัญ: คำนวณสถานะการส่งงานของนักเรียนคนนี้ ---
    # ดึงงานทุกชิ้นที่นักเรียนคนนี้เคยส่งในห้องนี้
    student_submissions = Submission.objects.filter(
        student=request.user, 
        assignment__in=assignments
    )
    # สร้าง map เพื่อให้ค้นหาได้เร็วขึ้น
    submission_map = {submission.assignment.id: submission for submission in student_submissions}

    for assignment in assignments:
        submission = submission_map.get(assignment.id)
        if submission:
            # TODO: ในอนาคตสามารถเช็คสถานะการตรวจ (Graded) ได้ที่นี่
            assignment.submission_status = 'SUBMITTED'
        else:
            assignment.submission_status = 'NOT_SUBMITTED'
    # --- จบส่วนคำนวณสถานะ ---

    context = {
        'room': room,
        'announcements': announcements,
        'assignments': assignments,
    }

    return render(request, 'student/room_detail.html', context)

def student_assignment_detail_view(request, assignment_id):
    # ในอนาคตเราจะใส่ Logic การดึงข้อมูลงานที่นี่
    # ตอนนี้แค่ render template ว่างๆ ไปก่อน
    
    # ลองดึงข้อมูล assignment มาเบื้องต้น
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    
    context = {
        'assignment': assignment,
    }
    return render(request, 'student/assignment_detail.html', context)