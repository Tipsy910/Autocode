from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from users.models import Students
from room.models import Room
from .forms import JoinRoomForm
from room.models import Room, Assignment

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
def student_room_detail_view(request, room_id):

    room = get_object_or_404(Room, id=room_id, students__user=request.user)

    assignments = Assignment.objects.filter(room=room).order_by('-due_date')
    
    context = {
        'room': room,
        'assignments': assignments, # <--- ส่งรายการงานไปที่ template
        'page_title': f"เข้าห้องเรียน: {room.name}",
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