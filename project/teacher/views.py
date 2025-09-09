from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic.edit import DeleteView 
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from room.models import Room, generate_invite_code
from .forms import RoomForm
# Create your views here.


class teacher_dashboard(View):
    template_name = 'teacher/dashboard.html'

    def get(self, request, *args, **kwargs):
        all_rooms = Room.objects.filter(owner=request.user)
        form = RoomForm() # <--- สำคัญ: เราต้องส่งฟอร์มเปล่าไปให้ template เสมอ
        context = {
            'all_rooms': all_rooms,
            'form': form, # <--- เพื่อให้ Modal นำไปใช้สร้าง input field
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        # ส่วน post นี้ไม่ต้องแก้ไขอะไรเลย มันทำงานถูกต้องอยู่แล้ว
        all_rooms = Room.objects.filter(owner=request.user)
        form = RoomForm(request.POST,request.FILES) # <--- เพิ่ม request.FILES เพื่อรองรับการอัพโหลดไฟล์
        
        if form.is_valid():
            room = form.save(commit=False)
            room.owner = request.user
            room.invite_code = generate_invite_code()
            room.save()
            return redirect(reverse_lazy('teacher:dashboard'))
        else:
            # ถ้าฟอร์มไม่ผ่าน ก็ render หน้าเดิมพร้อม error
            context = {
                'all_rooms': all_rooms,
                'form': form,
            }
            return render(request, self.template_name, context)
def teacher_room_detail_view(request, pk):
    # ดึงข้อมูลห้องเรียน (โค้ดเดิมของคุณ ดีอยู่แล้ว)
    room = get_object_or_404(Room, pk=pk, owner=request.user)
    
    # --- [ เพิ่มส่วนจัดการฟอร์มแก้ไข ] ---
    if request.method == 'POST':
        # ถ้ามีการส่งฟอร์มมา (นี่คือการพยายาม "แก้ไข")
        form = RoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            form.save() # บันทึกการเปลี่ยนแปลง
            return redirect('room:teacher_detail', pk=room.pk) # กลับไปหน้าเดิม
            # หมายเหตุ: แก้ 'room:teacher_detail' ให้ตรงกับชื่อ URL ของคุณ
    else:
        # ถ้าเป็นการเปิดหน้าเว็บปกติ (GET request)
        # สร้างฟอร์มโดยใส่ instance=room เพื่อให้ฟอร์มมีข้อมูลเก่าแสดงอยู่
        form = RoomForm(instance=room)
    # --- [ จบส่วนจัดการฟอร์ม ] ---

    # ดึงรายชื่อนักเรียน (โค้ดเดิมของคุณ ดีอยู่แล้ว)
    students_in_room = room.students.all().order_by('user__first_name', 'user__last_name')
    
    context = {
        'room': room,
        'students_in_room': students_in_room,
        'edit_form': form, # <-- เพิ่มฟอร์มเข้าไปใน context เพื่อให้ template เรียกใช้ได้
        'page_title': f"ห้องเรียน: {room.name}",
    }
    return render(request, 'teacher/room_detail.html', context)

class RoomDeleteView(LoginRequiredMixin, DeleteView):
    """
    View สำหรับจัดการการลบห้องเรียน
    - GET request: จะแสดงหน้า template เพื่อให้ผู้ใช้ยืนยัน
    - POST request: จะทำการลบข้อมูลออกจากฐานข้อมูล
    """
    model = Room
    template_name = 'teacher/room_confirm_delete.html'  # Template ที่จะสร้างในขั้นตอนถัดไป
    success_url = reverse_lazy('teacher:dashboard')     # Redirect ไปหน้า dashboard หลังลบสำเร็จ

    def get_queryset(self):
        """
        **ส่วนสำคัญเพื่อความปลอดภัย**
        กรองข้อมูลเพื่อให้แน่ใจว่าอาจารย์จะสามารถลบได้เฉพาะห้องที่ตัวเองเป็นเจ้าของเท่านั้น
        """
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        """
        ส่งข้อมูลเพิ่มเติมไปยัง Template (ถ้าต้องการ)
        """
        context = super().get_context_data(**kwargs)
        # `object` คือ room ที่กำลังจะถูกลบ Django ใส่มาให้เราอัตโนมัติ
        context['page_title'] = f'ยืนยันการลบห้อง: {self.object.name}'
        return context