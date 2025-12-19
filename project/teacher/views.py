from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic.edit import DeleteView 
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from room.models import *
from .forms import *
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.core.exceptions import ObjectDoesNotExist # 📌 อย่าลืม import ตัวนี้ไว้บนสุด
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
    # ---------------------------------------------------------
    # 1. ส่วนดึงข้อมูลห้อง (Room Retrieval & Permission)
    # ---------------------------------------------------------
    try:
        teacher_profile = request.user.teacher_profile
    except AttributeError:
        return redirect('teacher:dashboard')

    # ดึงห้องที่ user เป็นเจ้าของ OR เป็นครูผู้ช่วย (แก้ปัญหาห้องซ้ำด้วย distinct)
    rooms_queryset = Room.objects.filter(
        Q(owner=request.user) | Q(teachers=teacher_profile)
    ).distinct()

    room = get_object_or_404(rooms_queryset, pk=pk)

    # ---------------------------------------------------------
    # 2. เตรียม Forms (Initialize)
    # ---------------------------------------------------------
    # สร้างฟอร์มเปล่าๆ ไว้ก่อน เพื่อส่งไป render กรณีเป็น GET request
    edit_form = RoomForm(instance=room) 
    announcement_form = AnnouncementForm()

    # ---------------------------------------------------------
    # 3. จัดการ POST Requests (เมื่อมีการกดปุ่ม Submit)
    # ---------------------------------------------------------
    if request.method == 'POST':
        # รับค่าจาก hidden input ที่เราฝังไว้ใน HTML เพื่อดูว่าทำรายการอะไร
        action = request.POST.get('action') 

        # === กรณี A: แก้ไขห้องเรียน (Edit Room) ===
        if action == 'edit_room':
            # 🔒 Security Check: ต้องเป็นเจ้าของห้องเท่านั้นถึงแก้ได้
            if room.owner != request.user:
                raise PermissionDenied("คุณไม่มีสิทธิ์แก้ไขห้องเรียนนี้")
            
            edit_form = RoomForm(request.POST, request.FILES, instance=room)
            if edit_form.is_valid():
                edit_form.save()
                return redirect('room:teacher_detail', pk=room.pk)

        # === กรณี B: สร้างประกาศใหม่ (Post Announcement) ===
        elif action == 'post_announcement':
            announcement_form = AnnouncementForm(request.POST)
            if announcement_form.is_valid():
                # save(commit=False) เพื่อเติมข้อมูลที่ขาดก่อนบันทึกจริง
                new_announcement = announcement_form.save(commit=False)
                new_announcement.room = room            # ผูกกับห้องนี้
                new_announcement.author = request.user# ผูกกับคนโพสต์
                new_announcement.save()
                files = request.FILES.getlist('attached_files') 
                
                for f in files:
                    # สร้าง object AnnouncementFile แยกทีละไฟล์ ผูกกับประกาศนี้
                    AnnouncementFile.objects.create(
                        announcement=new_announcement,
                        file=f
                    )
                return redirect('room:teacher_detail', pk=room.pk)
    
    # ---------------------------------------------------------
    # 4. เตรียม Context และ Render
    # ---------------------------------------------------------
    students_in_room = room.students.all().order_by('user__first_name', 'user__last_name')
    assignments = Assignment.objects.filter(room=room).order_by('-created_at')
    # ดึงประกาศทั้งหมด เรียงจากใหม่ไปเก่า
    announcements = Announcement.objects.filter(room=room).order_by('-created_at') 

    context = {
        'room': room,
        'page_title': f"ห้องเรียน: {room.name}",
        'students_in_room': students_in_room,
        'assignments': assignments,
        'announcements': announcements,
        
        # ส่งฟอร์มทั้ง 2 ตัวไปยัง Template
        'edit_form': edit_form,             # สำหรับ Modal แก้ไขห้อง
        'announcement_form': announcement_form, # สำหรับโพสต์ประกาศ
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
def edit_announcement(request, pk):
    # ดึงประกาศมา (ต้องเป็นของคนนี้เท่านั้น ถึงจะมีสิทธิ์แก้)
    announcement = get_object_or_404(Announcement, pk=pk, author=request.user)

    if request.method == 'POST':
        # 1. อัปเดตเนื้อหาข้อความ
        new_content = request.POST.get('content')
        if new_content:
            announcement.content = new_content
            announcement.save()

        # 2. ลบไฟล์เดิม (ที่เราติ๊กถูกมา)
        # รับ list ของ ID ที่ต้องการลบ
        delete_ids = request.POST.getlist('delete_file_ids') 
        if delete_ids:
            # ลบเฉพาะไฟล์ที่เป็นของประกาศนี้จริงๆ (เพื่อความปลอดภัย)
            AnnouncementFile.objects.filter(
                id__in=delete_ids, 
                announcement=announcement
            ).delete()

        # 3. เพิ่มไฟล์ใหม่ (ถ้ามี)
        new_files = request.FILES.getlist('new_files')
        for f in new_files:
            AnnouncementFile.objects.create(
                announcement=announcement,
                file=f
            )

        # เสร็จแล้วเด้งกลับไปหน้าเดิม
        return redirect('room:teacher_detail', pk=announcement.room.pk)

    # ถ้าไม่ใช่ POST (หรือ Error) ให้เด้งกลับไปที่เดิม
    return redirect('room:teacher_detail', pk=announcement.room.pk)

class AnnouncementDeleteView(LoginRequiredMixin, DeleteView):
    model = Announcement
    
    def get_queryset(self):
        """
        ดีมากครับ! การกรองตรงนี้ปลอดภัยที่สุด 
        ถ้าไม่ใช่เจ้าของ จะหา object ไม่เจอ และเด้ง 404 ให้เอง
        """
        queryset = super().get_queryset()
        return queryset.filter(author=self.request.user)

    def get_success_url(self):
        """
        redirect กลับไปที่ห้องเรียน
        """
        # self.object ยังคงเข้าถึงได้อยู่แม้จะถูกสั่งลบไปแล้วใน method delete()
        room_pk = self.object.room.pk 
        messages.success(self.request, "ลบประกาศเรียบร้อยแล้ว")
        return reverse('room:teacher_detail', kwargs={'pk': room_pk})

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
    # 1. ดึงข้อมูล Assignment และตรวจสอบสิทธิ์
    assignment = get_object_or_404(Assignment, pk=pk)
    
    try:
        teacher_profile = request.user.teacher_profile
    except AttributeError:
        return redirect('teacher:dashboard')

    is_owner = (request.user == assignment.room.owner)
    is_teacher = assignment.room.teachers.filter(pk=teacher_profile.pk).exists()
    if not (is_owner or is_teacher):
        return redirect('teacher:dashboard')
    
    # 2. ดึงนักเรียนทั้งหมดในห้อง (นี่คือตัวส่วน "ส่วน 2")
    students_in_room = assignment.room.students.select_related('user').order_by('user__first_name')
    
    # 3. ดึงงานที่ส่งมาทั้งหมด
    submissions = Submission.objects.filter(assignment=assignment).select_related('student', 'quiz')
    submission_map = {sub.student.id: sub for sub in submissions} # Key คือ User ID
    
    # 4. ตัวแปรเก็บสถิติ (เริ่มต้นเป็น 0)
    stats = {
        'total': students_in_room.count(), # จำนวนนักเรียนทั้งหมด
        'submitted': 0, # ส่งแล้ว (รวมทุกสถานะที่ส่งมา)
        'pending': 0,   # รอตรวจ (รอ AI หรือ รอครูอนุมัติ)
        'passed': 0,    # ผ่านแล้ว
        'reported': 0   # แจ้งปัญหา
    }

    student_submissions = []
    
    # 5. วนลูปนักเรียนทีละคน (เพื่อความแม่นยำ)
    for student in students_in_room:
        # ดึงงานส่งของนักเรียนคนนี้ (ถ้ามี)
        submission = submission_map.get(student.user.id)
        
        display_status = 'MISSING' # ค่าเริ่มต้น (ยังไม่ส่ง)
        
        if submission:
            # ✅ ถ้านักเรียนคนนี้มีงานส่ง -> นับ +1 ทันที
            stats['submitted'] += 1
            
            # --- เช็คสถานะย่อย ---
            
            # 1. กรณีมีการแจ้งปัญหา (Report)
            if submission.is_reported:
                display_status = 'REPORTED'
                stats['reported'] += 1
                stats['pending'] += 1 # ถือว่าต้องรอครูเข้าไปดู
                
            # 2. กรณีผ่านแล้ว (Approved)
            elif submission.status == 'PASSED':
                display_status = 'PASSED'
                stats['passed'] += 1
                
            # 3. กรณีถูกส่งคืน (Reject/Revision)
            elif submission.status == 'REJECT':
                display_status = 'REJECT'
                # ไม่นับเป็น pending หรือ passed เพราะถือว่าส่งกลับไปแล้ว
                
            # 4. กรณี AI ตรวจแล้ว (รอครูอนุมัติ)
            elif submission.status == 'GRADED': # <--- แก้ตรงนี้ (ใช้ status แทน is_graded)
                display_status = 'WAITING_APPROVAL'
                stats['pending'] += 1
                
            # 5. กรณีเพิ่งส่ง (รอ AI ตรวจ)
            else: # status == 'PENDING'
                display_status = 'SUBMITTED'
                stats['pending'] += 1 # รอ AI ตรวจ ก็ถือว่า Pending
        
        # เก็บข้อมูลเพื่อนำไปแสดงผลในตาราง
        student_submissions.append({
            'student': student,
            'submission': submission,
            'status': display_status
        })
        

    # เรียงลำดับ: แจ้งปัญหา > รอตรวจ > ส่งแล้ว > ผ่านแล้ว > ยังไม่ส่ง
    status_priority = {
        'REPORTED': 1,
        'WAITING_APPROVAL': 2,
        'SUBMITTED': 3,
        'REJECT': 4,
        'PASSED': 5,
        'MISSING': 6
    }
    student_submissions.sort(key=lambda x: status_priority.get(x['status'], 99))

    context = {
        'assignment': assignment,
        'student_submissions': student_submissions,
        'stats': stats, # 👈 ส่งตัวแปรสถิติที่คำนวณใหม่ไปให้หน้าเว็บ
    }
    
    return render(request, 'teacher/assignment_detail.html', context)
    # เรียงลำดับ: เอาคนที่มีปัญหาขึ้นก่อน -> ตามด้วยคนที่ส่งแล้ว -> คนยังไม่ส่ง
    # (Logic: REPORTED มาก่อนเพื่อน)
    student_submissions.sort(key=lambda x: 0 if x['display_status'] == 'REPORTED' else 1)

    context = {
        'assignment': assignment,
        'student_submissions': student_submissions
    }
    
    return render(request, 'teacher/assignment_detail.html', context)

class AssignmentDeleteView(LoginRequiredMixin, DeleteView):
    model = Assignment
    # template_name = 'teacher/assignment_confirm_delete.html' # ถ้าใช้ Modal กด Submit มาเลย บรรทัดนี้อาจไม่ได้ใช้ แต่ใส่กันไว้ก่อนได้ครับ
    
    def get_queryset(self):
        """
        แก้ไข: กรองให้ลบได้เฉพาะ
        1. คนสร้าง (author)
        2. หรือ เจ้าของห้อง (room.owner)
        """
        queryset = super().get_queryset()
        user = self.request.user

        # ใช้ Q Object เพื่อสร้างเงื่อนไข "หรือ" (OR)
        # ความหมาย: เอา Assignment ที่ (author คือ user) หรือ (room__owner คือ user)
        return queryset.filter(Q(author=user) | Q(room__owner=user))

    def get_success_url(self):
        """
        หลังจากลบสำเร็จ ให้ redirect กลับไปที่หน้ารายละเอียดของ 'ห้องเรียน'
        """
        room_pk = self.object.room.pk
        return reverse('room:teacher_detail', kwargs={'pk': room_pk})

    def delete(self, request, *args, **kwargs):
        """
        Override เมธอด delete เพื่อเพิ่ม Flash Message แจ้งเตือนก่อนลบจริง
        """
        obj = self.get_object() # ดึงข้อมูลงานที่จะลบมาเก็บไว้ก่อน (เดี๋ยวลบแล้วจะหาชื่อไม่เจอ)
        
        messages.success(request, f"ลบงาน '{obj.title}' เรียบร้อยแล้ว")
        
        return super().delete(request, *args, **kwargs)

@login_required
def edit_assignment(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)

    # ============================================================
    # 🔑 UPDATE PERMISSION: ให้เจ้าของห้องแก้ได้ด้วย
    # ============================================================
    
    # 1. เช็คว่าเป็นคนสร้างหรือไม่?
    is_author = (assignment.author == request.user)
    
    # 2. เช็คว่าเป็นเจ้าของห้องใหญ่หรือไม่? (เข้าถึงผ่าน assignment.room)
    # หมายเหตุ: ถ้าโมเดลคุณชื่ออื่น (เช่น assignment.classroom) ให้แก้ตรงนี้
    is_room_owner = (assignment.room.owner == request.user)

    # ถ้า "ไม่ใช่คนสร้าง" และ "ไม่ใช่เจ้าของห้อง" -> ดีดออก
    if not is_author and not is_room_owner:
        messages.error(request, "คุณไม่มีสิทธิ์แก้ไขงานชิ้นนี้ (สงวนสิทธิ์เฉพาะผู้สร้าง หรือเจ้าของห้อง)")
        return redirect('teacher:assignment_detail', pk=assignment.pk)

    # ============================================================

    if request.method == 'POST':
        # ✅ ถูกต้อง: มี request.FILES
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        
        if form.is_valid():
            # ============================================================
            # 🧹 ADD: เช็คว่ามีการอัปโหลดไฟล์ใหม่มาไหม? ถ้ามี ให้ลบอันเก่าทิ้ง
            # ============================================================
            
            # 1. เช็คไฟล์โจทย์ (problem_file)
            if 'problem_file' in request.FILES:
                # ถ้ามีไฟล์เก่าอยู่ ให้ลบทิ้งก่อน
                if assignment.problem_file:
                    try:
                        assignment.problem_file.delete(save=False)
                    except:
                        pass # ถ้าลบไม่ได้ (เช่นไฟล์หายไปแล้ว) ก็ปล่อยผ่าน

            # 2. เช็คไฟล์เทสเคส (test_case_file)
            if 'test_case_file' in request.FILES:
                if assignment.test_case_file:
                    try:
                        assignment.test_case_file.delete(save=False)
                    except:
                        pass
            # ============================================================

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

@login_required
def review_submission_view(request, pk):
    # 1. ดึงข้อมูลงานส่ง
    submission = get_object_or_404(Submission, pk=pk)
    
    # 2. เช็คสิทธิ์
    assignment = submission.assignment
    is_owner = assignment.room.owner == request.user
    is_ta = hasattr(request.user, 'teacher_profile') and assignment.room.teachers.filter(pk=request.user.teacher_profile.pk).exists()
    
    if not is_owner and not is_ta:
        messages.error(request, "คุณไม่มีสิทธิ์ตรวจงานนี้")
        return redirect('teacher:dashboard')

    # ✅ STEP 1: ดึง Quiz แบบปลอดภัย (Safe Fetch)
    # เราจะไม่เรียก submission.quiz ตรงๆ เพราะถ้าไม่มีมันจะ Error ทันที
    quiz_instance = None
    current_quiz_score = 0
    
    try:
        # ลองดึง quiz ถ้ามี
        if hasattr(submission, 'quiz'): 
            quiz_instance = submission.quiz
            current_quiz_score = quiz_instance.score
    except ObjectDoesNotExist:
        # ถ้าหาไม่เจอก็ให้เป็น None ไป โปรแกรมจะไม่พัง
        quiz_instance = None
        current_quiz_score = 0
    except Exception as e:
        print(f"Quiz access error: {e}")
        quiz_instance = None

    # 3. Logic การตรวจงาน (POST)
    if request.method == 'POST':
        form = GradingForm(request.POST)
        
        if form.is_valid():
            action = request.POST.get('action')
            
            # --- ดึงข้อมูลจาก Form ---
            new_ai_score = form.cleaned_data['score']
            new_comment = form.cleaned_data['feedback']
            new_quiz_score = form.cleaned_data.get('quiz_score')

            # --- อัปเดตข้อมูล Submission ---
            submission.teacher_comment = new_comment
            submission.ai_score = new_ai_score
            submission.graded_at = timezone.now()
            submission.is_reported = False 
            submission.is_graded = True 

            # --- ✅ STEP 2: อัปเดต Quiz เฉพาะตอนที่มี Quiz อยู่จริงเท่านั้น ---
            if quiz_instance and new_quiz_score is not None:
                quiz_instance.score = new_quiz_score
                quiz_instance.save()
                current_quiz_score = new_quiz_score

            # --- คำนวณคะแนนรวม ---
            ai_part = submission.ai_score if submission.ai_score else 0
            submission.score = ai_part + current_quiz_score

            # ========================================================
            # ✅ CASE 1: อนุมัติ (APPROVE) -> สถานะ PASSED
            # ========================================================
            if action == 'approve':
                submission.status = 'PASSED'
                
                # --- ✅ STEP 3: ลบ Quiz เก่าทิ้งเพื่อให้สร้างใหม่ (Safe Delete) ---
                if quiz_instance:
                    try:
                        quiz_instance.delete() # ลบจาก Database
                        quiz_instance = None   # เคลียร์ตัวแปร local
                        current_quiz_score = 0 
                    except Exception as e:
                        print(f"Error deleting quiz: {e}")

                # สำคัญ: รีเซ็ต flag เพื่อให้ปุ่ม 'เริ่มทำแบบทดสอบ' โผล่ที่ฝั่งนักเรียน
                submission.quiz_generated = False 
                submission.save() 

                # --- ส่งอีเมลแจ้งข่าวดี ---
                student_email = submission.student.email
                assignment_url = request.build_absolute_uri(
                    reverse('student:assignment_detail', args=[submission.assignment.id])
                )

                context = {
                    'student_name': submission.student.get_full_name(),
                    'assignment_title': submission.assignment.title,
                    'ai_score': submission.ai_score,
                    'teacher_comment': new_comment,
                    'action_url': assignment_url,
                }
                
                # (Render Email Template Code...)
                html_message = render_to_string('teacher/emails/approve_submission.html', context)
                plain_message = strip_tags(html_message)
                subject = f"✅ ยินดีด้วย! งาน '{submission.assignment.title}' ผ่านการตรวจสอบแล้ว"

                try:
                    send_mail(subject, plain_message, settings.DEFAULT_FROM_EMAIL, [student_email], html_message=html_message, fail_silently=True)
                    messages.success(request, f"อนุมัติงานเรียบร้อย (นักเรียนสามารถเริ่มทำแบบทดสอบได้)")
                except:
                    messages.warning(request, "บันทึกสถานะแล้ว แต่ส่งอีเมลไม่สำเร็จ")

            # ========================================================
            # ❌ CASE 2: ส่งคืน (REJECT) -> สถานะ REJECT
            # ========================================================
            elif action == 'reject':
                submission.status = 'REJECT'
                submission.is_graded = False 
                
                # --- ล้าง Quiz ทิ้ง (ถ้ามี) ---
                submission.quiz_generated = False
                if quiz_instance:
                    try:
                        quiz_instance.delete()
                    except:
                        pass
                
                submission.save()

                # --- ส่งอีเมลแจ้งงานแก้ ---
                # (Email Code same as before...)
                context = {
                    'student_name': submission.student.get_full_name(),
                    'assignment_title': submission.assignment.title,
                    'teacher_comment': new_comment,
                    'action_url': request.build_absolute_uri(reverse('student:assignment_detail', args=[submission.assignment.id])),
                }
                html_message = render_to_string('teacher/emails/reject_submission.html', context)
                plain_message = strip_tags(html_message)
                
                try:
                    send_mail(f"⚠️ งานถูกส่งคืนให้แก้ไข: {submission.assignment.title}", plain_message, settings.DEFAULT_FROM_EMAIL, [submission.student.email], html_message=html_message, fail_silently=True)
                    messages.warning(request, "ส่งคืนงานเรียบร้อยแล้ว")
                except:
                    pass

            # กรณี Save ธรรมดา (ไม่ใช่ Approve/Reject)
            if action not in ['approve', 'reject']:
                submission.save()
                messages.success(request, "บันทึกข้อมูลเรียบร้อย")
            
            return redirect('teacher:assignment_detail', pk=assignment.pk)

    # 4. กรณี GET (เปิดหน้าตรวจงาน)
    else:
        initial_data = {
            'score': submission.ai_score,
            'quiz_score': current_quiz_score, # ใช้ค่าที่ Safe Fetch มา
            'feedback': submission.teacher_comment
        }
        form = GradingForm(initial=initial_data)

    return render(request, 'teacher/review_submission.html', {
        'submission': submission,
        'form': form,
        'quiz': quiz_instance # ส่งตัวแปรที่ Safe แล้วไปหน้าเว็บ
    })

@login_required
def teacher_quiz_result_view(request, pk):
    # 1. ดึงข้อมูล Submission
    submission = get_object_or_404(Submission, pk=pk)
    
    # 2. ตรวจสอบสิทธิ์ (เจ้าของห้อง หรือ ครูผู้ช่วย)
    assignment = submission.assignment
    if assignment.room.owner != request.user and not assignment.room.teachers.filter(pk=request.user.teacher_profile.pk).exists():
        messages.error(request, "คุณไม่มีสิทธิ์ดูผลสอบนี้")
        return redirect('teacher:dashboard')

    # 3. เช็คว่ามี Quiz ไหม
    if not hasattr(submission, 'quiz'):
        messages.warning(request, "นักเรียนยังไม่ได้ทำแบบทดสอบ")
        return redirect('teacher:review_submission', pk=pk)

    quiz = submission.quiz
    questions = quiz.questions.prefetch_related('choices').all()
    
    # 4. ดึงคำตอบนักเรียนมา Map ใส่ Dict { question_id: choice_id }
    student_answers_dict = {
        ans.question.id: ans.selected_choice.id 
        for ans in quiz.student_answers.all()
    }

    return render(request, 'teacher/quiz_result.html', {
        'submission': submission,
        'quiz': quiz,
        'questions': questions,
        'student_answers_dict': student_answers_dict
    })

@login_required
def report_list_view(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    
    # Check permissions
    is_owner = (request.user == assignment.room.owner)
    is_teacher = assignment.room.teachers.filter(pk=request.user.teacher_profile.pk).exists()
    if not (is_owner or is_teacher):
        return redirect('teacher:dashboard')

    # Filter only reported submissions
    reported_submissions = Submission.objects.filter(
        assignment=assignment, 
        is_reported=True
    ).select_related('student')

    return render(request, 'teacher/report_list.html', {
        'assignment': assignment,
        'reported_submissions': reported_submissions
    })