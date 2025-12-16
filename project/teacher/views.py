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

@login_required
def edit_assignment(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)

    if assignment.author != request.user:
        messages.error(request, "คุณไม่มีสิทธิ์แก้ไขงานชิ้นนี้ เนื่องจากไม่ใช่ผู้สร้าง")
        return redirect('teacher:assignment_detail', pk=assignment.pk)

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
    
    # 2. เช็คสิทธิ์: คนดูต้องเป็นเจ้าของห้อง หรือครูผู้ช่วย
    assignment = submission.assignment
    is_owner = assignment.room.owner == request.user
    is_ta = hasattr(request.user, 'teacher_profile') and assignment.room.teachers.filter(pk=request.user.teacher_profile.pk).exists()
    
    if not is_owner and not is_ta:
        messages.error(request, "คุณไม่มีสิทธิ์ตรวจงานนี้")
        return redirect('teacher:dashboard')

    # 3. Logic การตรวจงาน (POST)
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('teacher_comment', '')
        ai_score = request.POST.get('ai_score')

        # อัปเดตข้อมูลพื้นฐาน (คะแนน AI และคอมเมนต์)
        submission.teacher_comment = comment
        if ai_score:
            submission.ai_score = int(ai_score)
        
        submission.graded_at = timezone.now()
        submission.is_reported = False # รีเซ็ตสถานะการรายงาน (ถ้ามี)
        
# ========================================================
        # ✅ CASE 1: อนุมัติ (APPROVE) -> ให้ผ่าน + ส่งเมลแจ้งข่าวดี
        # ========================================================
        if action == 'approve':
            submission.status = 'PASSED' 
            
            # --- เตรียมส่งอีเมล (เพิ่มใหม่) ---
            student_email = submission.student.user.email
            assignment_url = request.build_absolute_uri(
                reverse('student:assignment_detail', args=[submission.assignment.id])
            )

            context = {
                'student_name': submission.student.name,
                'assignment_title': submission.assignment.title,
                'ai_score': submission.ai_score,
                'teacher_comment': comment,
                'action_url': assignment_url,
            }

            html_message = render_to_string('teacher/emails/approve_submission.html', context)
            plain_message = strip_tags(html_message)
            subject = f"✅ ยินดีด้วย! งาน '{submission.assignment.title}' ผ่านการตรวจสอบแล้ว"

            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[student_email],
                    html_message=html_message,
                    fail_silently=True
                )
                messages.success(request, f"บันทึกผล 'ผ่าน' และแจ้งเตือนนักเรียนเรียบร้อย (คะแนน: {submission.ai_score})")
            except Exception as e:
                print(f"❌ Email Error: {e}")
                messages.warning(request, "บันทึกสถานะผ่านแล้ว แต่ส่งอีเมลไม่สำเร็จ")
            
        # ========================================================
        # ❌ CASE 2: ส่งคืน (REJECT) -> ให้แก้ + ส่งเมล
        # ========================================================
        elif action == 'reject':
            submission.status = 'REJECT'
            
            # --- 2.1 ล้างบาง Quiz (สำคัญมาก) ---
            submission.quiz_generated = False
            if hasattr(submission, 'quiz'):
                submission.quiz.delete()
                print(f"🗑️ Deleted Quiz for submission {submission.id}")
            
            # --- 2.2 เตรียมส่งอีเมลแจ้งเตือน (HTML Email) ---
            student_email = submission.student.email
            
            # สร้าง URL ลิงก์กลับไปหน้างานของนักเรียน
            assignment_url = request.build_absolute_uri(
                reverse('student:assignment_detail', args=[submission.assignment.id])
            )

            # ข้อมูลที่จะส่งไปใน Template
            context = {
                'student_name': submission.student.get_full_name(), # หรือ submission.student.user.get_full_name()
                'assignment_title': submission.assignment.title,
                'teacher_comment': comment,
                'action_url': assignment_url,
            }

            # เรนเดอร์ HTML เป็น String
            html_message = render_to_string('teacher/emails/reject_submission.html', context)
            plain_message = strip_tags(html_message) # สร้าง Text ธรรมดาเผื่อไว้

            subject = f"⚠️ งาน '{submission.assignment.title}' ถูกส่งคืนให้แก้ไข"
            
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,      # ข้อความล้วน
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[student_email],
                    html_message=html_message,  # ✅ ข้อความ HTML
                    fail_silently=True
                )
                messages.warning(request, "บันทึกสถานะ 'ส่งคืน' และแจ้งเตือนนักเรียนทางเมลเรียบร้อยแล้ว")
            except Exception as e:
                print(f"❌ Email Error: {e}")
                messages.warning(request, "บันทึกสถานะแล้ว แต่ส่งเมลแจ้งเตือนไม่สำเร็จ")
                
        # บันทึกข้อมูลลงฐานข้อมูล
        submission.save()
        
        # บันทึกเสร็จ กลับไปหน้ารายละเอียดงาน (รายชื่อนักเรียน)
        return redirect('teacher:assignment_detail', pk=assignment.pk)

    # 4. กรณี GET (เปิดหน้าตรวจงาน)
    # ส่งข้อมูล Quiz ไปด้วยเผื่ออาจารย์อยากดู (ถ้ามี)
    quiz = getattr(submission, 'quiz', None)

    return render(request, 'teacher/review_submission.html', {
        'submission': submission,
        'quiz': quiz
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