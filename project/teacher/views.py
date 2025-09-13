from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic.edit import DeleteView 
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from room.models import Room, generate_invite_code, Assignment,Submission,Announcement, AnnouncementFile
from .forms import RoomForm, AssignmentForm, JoinRoomForm, AnnouncementForm
from django.db.models import Q
from django.contrib import messages 
# Create your views here.


class teacher_dashboard(View):
    template_name = 'teacher/dashboard.html'

    def get_teacher_profile(self, user):
        """Helper function to safely get teacher profile."""
        try:
            return user.teacher_profile
        except AttributeError:
            # กรณีที่ User ไม่มี teacher_profile (อาจจะเกิดขึ้นได้ยาก แต่เป็นการป้องกันที่ดี)
            return None

    def get(self, request, *args, **kwargs):
        teacher_profile = self.get_teacher_profile(request.user)
        if not teacher_profile:
            # ถ้าไม่มีโปรไฟล์อาจารย์ ก็ไม่ควรเห็นห้องใดๆ
            all_rooms = Room.objects.none()
        else:
            all_rooms = Room.objects.filter(
                Q(owner=request.user) | Q(teachers=teacher_profile)
            ).distinct()
        
        create_form = RoomForm() 
        join_form = JoinRoomForm()
        
        context = {
            'all_rooms': all_rooms,
            'create_form': create_form,
            'join_form': join_form,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        teacher_profile = self.get_teacher_profile(request.user)
        
        if not teacher_profile:
             # ป้องกันกรณีที่ไม่มีโปรไฟล์แต่พยายาม join/create
            return redirect('teacher:dashboard')

        if action == 'create_room':
            form = RoomForm(request.POST, request.FILES)
            if form.is_valid():
                room = form.save(commit=False)
                room.owner = request.user
                room.invite_code = generate_invite_code()
                room.save()
                # เพิ่มผู้สร้างเป็น teacher ในห้องด้วยก็ได้ (Optional)
                room.teachers.add(teacher_profile)
                return redirect('teacher:dashboard')
            return self.render_error(request, create_form=form)

        elif action == 'join_room':
            form = JoinRoomForm(request.POST)
            if form.is_valid():
                code = form.cleaned_data['code']
                try:
                    room_to_join = Room.objects.get(invite_code__iexact=code)
                    
                    if room_to_join.owner == request.user or room_to_join.teachers.filter(id=teacher_profile.id).exists():
                        form.add_error('code', 'คุณอยู่ในห้องเรียนนี้แล้ว')
                    else:
                        room_to_join.teachers.add(teacher_profile)
                        return redirect('teacher:dashboard')

                except Room.DoesNotExist:
                    form.add_error('code', 'ไม่พบห้องเรียนสำหรับรหัสนี้')
            return self.render_error(request, join_form=form)

        return redirect('teacher:dashboard')

    def render_error(self, request, create_form=None, join_form=None):
        """Helper method เพื่อ re-render หน้าพร้อมกับฟอร์มที่มี error"""
        teacher_profile = self.get_teacher_profile(request.user)
        all_rooms = Room.objects.filter(
            Q(owner=request.user) | Q(teachers=teacher_profile)
        ).distinct() if teacher_profile else Room.objects.none()

        context = {
            'all_rooms': all_rooms,
            'create_form': create_form or RoomForm(),
            'join_form': join_form or JoinRoomForm(),
        }
        return render(request, self.template_name, context)
@login_required
def teacher_room_detail_view(request, pk):
    # 2. แก้ไข Query ให้ตรวจสอบทั้ง owner และ teachers
    # ดึงโปรไฟล์อาจารย์ของ user ที่ login อยู่
    try:
        teacher_profile = request.user.teacher_profile
    except AttributeError:
        # ถ้า user ไม่มีโปรไฟล์อาจารย์ ก็ไม่ควรเข้าห้องได้
        return redirect('teacher:dashboard')

    # ใช้ Q object ในการสร้างเงื่อนไข 'OR'
    # คือหาห้องที่มี pk ตรงกัน และ (user เป็น owner OR user อยู่ใน list ของ teachers)
    room = get_object_or_404(
        Room, 
        Q(pk=pk) & (Q(owner=request.user) | Q(teachers=teacher_profile))
    )
    
    # --- [ ส่วนจัดการฟอร์มแก้ไข (โค้ดส่วนนี้เหมือนเดิม) ] ---
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            form.save()
            return redirect('room:teacher_detail', pk=room.pk)
    else:
        form = RoomForm(instance=room)
    # --- [ จบส่วนจัดการฟอร์ม ] ---

    students_in_room = room.students.all().order_by('user__first_name', 'user__last_name')
    assignments = Assignment.objects.filter(room=room).order_by('-created_at')
    announcements = Announcement.objects.filter(room=room)
    context = {
        'room': room,
        'students_in_room': students_in_room,
        'edit_form': form,
        'page_title': f"ห้องเรียน: {room.name}",
        'assignments': assignments,
        'announcement_form': AnnouncementForm(),
        'announcements': announcements,
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

    
@login_required
def create_announcement(request, room_pk):
    if request.method == 'POST':
        room = get_object_or_404(Room, pk=room_pk)
        
        # ตรวจสอบสิทธิ์ (โค้ดคล้ายๆ กับ create_assignment)
        is_owner = (request.user == room.owner)
        is_teacher = room.teachers.filter(user=request.user).exists()
        if not (is_owner or is_teacher):
            messages.error(request, "คุณไม่มีสิทธิ์สร้างประกาศในห้องนี้")
            return redirect('room:teacher_detail', pk=room_pk)

        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.room = room
            announcement.author = request.user
            announcement.save()

            # จัดการไฟล์ที่แนบมาหลายๆ ไฟล์
            for f in request.FILES.getlist('attached_files'):
                AnnouncementFile.objects.create(announcement=announcement, file=f)
            
            messages.success(request, "สร้างประกาศเรียบร้อยแล้ว")

    # ไม่ว่าจะสำเร็จหรือไม่ ก็กลับไปที่หน้าเดิม
    return redirect('room:teacher_detail', pk=room_pk)

class AnnouncementDeleteView(LoginRequiredMixin, DeleteView):
    model = Announcement
    
    def get_queryset(self):
        """
        กรองข้อมูลเพื่อความปลอดภัย: ผู้ใช้ลบได้เฉพาะประกาศที่ตัวเองสร้างเท่านั้น
        """
        queryset = super().get_queryset()
        return queryset.filter(author=self.request.user)

    def get_success_url(self):
        """
        หลังจากลบสำเร็จ ให้ redirect กลับไปที่หน้ารายละเอียดของห้องเรียน
        """
        room_pk = self.object.room.pk
        messages.success(self.request, "ลบประกาศเรียบร้อยแล้ว")
        return reverse('room:teacher_detail', kwargs={'pk': room_pk})

@login_required
def edit_announcement(request, pk):
    # อนุญาตเฉพาะ POST request เท่านั้น เพราะการแก้ไขจะทำผ่านฟอร์มใน Modal
    if request.method == 'POST':
        announcement = get_object_or_404(Announcement, pk=pk)
        
        # ตรวจสอบสิทธิ์: ต้องเป็นผู้สร้างประกาศเท่านั้น
        if announcement.author != request.user:
            messages.error(request, "คุณไม่มีสิทธิ์แก้ไขประกาศนี้")
            return redirect('room:teacher_detail', pk=announcement.room.pk)
            
        # เราใช้ฟอร์มเดิม แต่รับแค่ content มา
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, "แก้ไขประกาศเรียบร้อยแล้ว")
        else:
            messages.error(request, "เกิดข้อผิดพลาดในการแก้ไขประกาศ")

    # ไม่ว่าจะสำเร็จหรือไม่ ก็กลับไปที่หน้าห้องเรียนเดิม
    return redirect('room:teacher_detail', pk=announcement.room.pk)






@login_required
def create_assignment(request, room_id):
    room = get_object_or_404(Room, pk=room_id)

    # --- ส่วนที่แก้ไข: ตรวจสอบสิทธิ์ให้ครอบคลุมผู้สอนร่วม ---
    try:
        teacher_profile = request.user.teacher_profile
    except AttributeError:
        # ถ้าไม่มีโปรไฟล์อาจารย์ ก็ไม่มีสิทธิ์สร้างงาน
        return redirect('teacher:dashboard')

    # ตรวจสอบว่า user ไม่ใช่ทั้งเจ้าของ 'และ' ไม่ใช่ผู้สอนร่วม
    is_owner = (request.user == room.owner)
    is_teacher = room.teachers.filter(pk=teacher_profile.pk).exists()

    if not (is_owner or is_teacher):
        # ถ้าไม่มีสิทธิ์ ให้ redirect กลับไปหน้า detail ของห้อง (แบบอ่านอย่างเดียว)
        # หรือจะ redirect ไปหน้า dashboard ก็ได้
        return redirect('room:teacher_detail', pk=room.id)
    # --- จบส่วนที่แก้ไข ---

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.room = room
            assignment.author = request.user # <-- เพิ่มบรรทัดนี้เพื่อบันทึกผู้สร้าง
            assignment.save()
            form.save_m2m()
            return redirect('room:teacher_detail', pk=room.id)
    else:
        form = AssignmentForm()

    context = {
        'form': form,
        'room': room
    }
    return render(request, 'teacher/create_assignment.html', context)

@login_required
def teacher_assignment_detail(request, pk):
    # 2. ดึงข้อมูล Assignment และตรวจสอบสิทธิ์ความเป็นเจ้าของ
    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        teacher_profile = request.user.teacher_profile
    except AttributeError:
        return redirect('teacher:dashboard')

    is_owner = (request.user == assignment.room.owner)
    is_teacher = assignment.room.teachers.filter(pk=teacher_profile.pk).exists()
    if not (is_owner or is_teacher):
        # ถ้าไม่ใช่ทั้งเจ้าของและผู้สอนร่วม ก็ไม่มีสิทธิ์ดู
        return redirect('teacher:dashboard')
    
    # 3. ดึงข้อมูลนักเรียนและการส่งงาน
    students_in_room = assignment.room.students.all()
    submissions = Submission.objects.filter(assignment=assignment)
    
    # 4. จัดการข้อมูลเพื่อให้ง่ายต่อการแสดงผลใน Template
    # สร้าง dict เพื่อให้ค้นหา submission ของนักเรียนแต่ละคนได้ง่าย
    submission_map = {sub.student.id: sub for sub in submissions}
    
    # สร้าง list ที่มีข้อมูลครบถ้วนสำหรับนักเรียนแต่ละคน
    student_submissions = []
    for student in students_in_room:
        student_submissions.append({
            'student': student,
            'submission': submission_map.get(student.id) # จะได้ Submission object หรือ None
        })

    context = {
        'assignment': assignment,
        'student_submissions': student_submissions
    }
    
    return render(request, 'teacher/assignment_detail.html', context)

class AssignmentDeleteView(LoginRequiredMixin, DeleteView):
    model = Assignment
    # Template fallback (กรณีเข้า URL ตรงๆ), แต่หลักๆ เราจะใช้ Modal
    template_name = 'teacher/assignment_confirm_delete.html' 
    
    def get_queryset(self):
        """
        แก้ไข: กรองให้ลบได้เฉพาะ Assignment ที่ตัวเองเป็นคนสร้าง (author) เท่านั้น
        """
        queryset = super().get_queryset()
        return queryset.filter(author=self.request.user)

    def get_success_url(self):
        """
        หลังจากลบสำเร็จ ให้ redirect กลับไปที่หน้ารายละเอียดของ 'ห้องเรียน'
        ที่ Assignment นี้เคยอยู่
        """
        # self.object คือ assignment ที่เพิ่งถูกลบไป
        room_pk = self.object.room.pk
        return reverse('room:teacher_detail', kwargs={'pk': room_pk})

# teacher/views.py

@login_required
def edit_assignment(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    
    # --- ส่วนที่แก้ไข: ตรวจสอบสิทธิ์การแก้ไข ---
    if assignment.author != request.user:
        # ถ้าไม่ใช่ผู้สร้างงานชิ้นนี้ ก็ไม่มีสิทธิ์แก้ไข
        messages.error(request, "คุณไม่มีสิทธิ์แก้ไขงานชิ้นนี้ เนื่องจากไม่ใช่ผู้สร้าง")
        return redirect('teacher:assignment_detail', pk=assignment.pk)
    # --- จบส่วนที่แก้ไข ---

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, f"แก้ไขงาน '{assignment.title}' เรียบร้อยแล้ว")
            return redirect('teacher:assignment_detail', pk=assignment.pk)
    else:
        form = AssignmentForm(instance=assignment)

    context = {
        'form': form,
        'assignment': assignment
    }
    return render(request, 'teacher/edit_assignment.html', context)
