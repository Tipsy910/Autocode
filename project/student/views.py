from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib.auth.decorators import login_required
from users.models import Students
from room.models import *
from django.utils import timezone
from .forms import JoinRoomForm
from student.forms import URLSubmissionForm, FileSubmissionForm
from django.contrib import messages
from .ai_utils import *
from django.db import transaction
from datetime import timedelta


class student_dashboard(LoginRequiredMixin, View):
    template_name = 'student/dashboard.html'
    
    def get(self, request, *args, **kwargs):
        # ใช้วิธีดึงข้อมูลที่มีประสิทธิภาพและปลอดภัยกว่า
        try:
            student_profile = request.user.student_profile
            joined_rooms = student_profile.joined_rooms.all()
        except AttributeError:
            # กรณี User ไม่มี student_profile
            joined_rooms = []
        
        context = {
            'joined_rooms': joined_rooms,
            'form': JoinRoomForm(), # ส่งฟอร์มเปล่าไปให้ Modal
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            # 1. แก้ไขให้ใช้ชื่อ field ที่ถูกต้องคือ 'code'
            code = form.cleaned_data.get('code')
            
            try:
                room_to_join = Room.objects.get(invite_code__iexact=code)
                student_profile = request.user.student_profile

                # 2. (ปรับปรุง) เพิ่มการตรวจสอบว่านักเรียนอยู่ในห้องนี้แล้วหรือยัง
                if room_to_join.students.filter(pk=student_profile.pk).exists():
                    messages.warning(request, 'คุณได้เข้าร่วมห้องเรียนนี้ไปแล้ว')
                else:
                    room_to_join.students.add(student_profile)
                    messages.success(request, f"เข้าร่วมห้อง '{room_to_join.name}' เรียบร้อยแล้ว")
                
                # 3. แก้ไข redirect ให้ถูกต้อง (ส่วนใหญ่ URL name จะมี namespace)
                return redirect('student:dashboard') 

            except Students.DoesNotExist:
                messages.error(request, 'เกิดข้อผิดพลาด: ไม่พบโปรไฟล์นักเรียนของคุณ')
            except Room.DoesNotExist:
                form.add_error('code', 'รหัสเข้าร่วมห้องเรียนไม่ถูกต้อง')
        
        # ถ้าย้ายโค้ดส่วนล่างมาไว้ตรงนี้ จะครอบคลุมทั้งกรณี form invalid และกรณี try-except fail
        # และใช้โค้ดเดียวกับใน get() เพื่อความสอดคล้อง
        try:
            student_profile = request.user.student_profile
            joined_rooms = student_profile.joined_rooms.all()
        except AttributeError:
            joined_rooms = []

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

@login_required
def student_assignment_detail_view(request, pk):
    # 1. ดึงข้อมูล Assignment
    assignment = get_object_or_404(Assignment, pk=pk)
    user = request.user
    
    # 2. ตรวจสอบว่า User เป็นนักเรียนจริงหรือไม่
    try:
        # เช็คชื่อ Model ดีๆ ว่าเป็น Student หรือ Students
        if not hasattr(user, 'student_profile'):
             # สมมติว่า Model ชื่อ Student
             raise Student.DoesNotExist 
        student_profile = user.student_profile
    except Exception: # ดัก Exception กว้างๆ ไว้ก่อนกรณีหา Model ไม่เจอ
        messages.error(request, 'บัญชีของคุณไม่ใช่บัญชีนักเรียน')
        return redirect('student:dashboard')

    # 3. ตรวจสอบสิทธิ์ว่านักเรียนอยู่ในห้องเรียนนี้หรือไม่
    if student_profile not in assignment.room.students.all():
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าถึงงานนี้ (ไม่อยู่ในห้องเรียน)')
        return redirect('student:dashboard')

    # เตรียมตัวแปรเพื่อเช็คประเภทการส่ง (สำหรับ Frontend)
    allowed_types_list = assignment.allowed_submission_types.values_list('identifier', flat=True)
    allow_file_submission = 'FILE' in allowed_types_list or 'PY' in allowed_types_list
    allow_url_submission = 'URL' in allowed_types_list

    # 4. ดึง Submission เดิม (ถ้าเคยส่งแล้ว)
    submission = Submission.objects.filter(student=user, assignment=assignment).first()

    # จัดการ Quiz Object แบบปลอดภัย
    quiz = None 
    if submission and hasattr(submission, 'quiz'):
        quiz = getattr(submission, 'quiz', None)

    # =========================================================
    # 🛑 LOGIC ควบคุมสิทธิ์การส่งงาน
    # =========================================================
    now = timezone.now()
    is_overdue = now > assignment.due_date
    has_done_quiz = True if quiz and quiz.is_completed else False # เช็คเพิ่มว่า is_completed ไหม

    can_submit = True
    disable_reason = ""

    # เงื่อนไขที่ 1: งานผ่านแล้ว (PASSED) -> ปิด
    if submission and submission.status == 'PASSED':
        can_submit = False
        disable_reason = "งานนี้ผ่านการตรวจสอบแล้ว"

    # เงื่อนไขที่ 2: เลยกำหนดส่ง และ ไม่อนุญาตให้ส่งช้า (และไม่ใช่การแก้ตัว)
    elif is_overdue and not assignment.allow_late_submission:
        # ข้อยกเว้น: ถ้าสถานะเป็น REJECT (ให้แก้) ต้องยอมให้ส่งใหม่ได้เสมอ แม้จะเลยเวลา
        if submission and submission.status == 'REJECT':
            can_submit = True 
        else:
            can_submit = False
            disable_reason = "หมดเวลาส่งงานแล้ว (ไม่อนุญาตให้ส่งล่าช้า)"
    
    # เงื่อนไขที่ 3: (Optional) ถ้าทำ Quiz ไปแล้วอาจจะห้ามส่งใหม่
    # if has_done_quiz: ...

    # =========================================================
    # 📤 HANDLE POST REQUEST (การส่งงาน)
    # =========================================================
    if request.method == 'POST':
        # เช็คสิทธิ์ก่อนเริ่ม Process
        if not can_submit:
            messages.error(request, f"ไม่สามารถส่งงานได้: {disable_reason}")
            return redirect('student:assignment_detail', pk=pk)

        try:
            with transaction.atomic():
                # สร้างหรือดึง Submission Object
                submission, created = Submission.objects.get_or_create(
                    student=user, 
                    assignment=assignment
                )

                # อัปเดตเวลาส่ง
                submission.submitted_at = timezone.now()
                
                # เช็ค Late Submission
                if is_overdue:
                    submission.is_late = True
                
                # ✅ รีเซ็ตสถานะเป็น "WAITING" เพื่อรอตรวจใหม่
                submission.status = 'WAITING'
                submission.is_graded = False  # Reset flag การตรวจ
                
                form_valid = False
                
                # --- กรณี A: ส่งแบบ URL ---
                if 'submit_url' in request.POST:
                    url_form = URLSubmissionForm(request.POST, instance=submission)
                    if url_form.is_valid():
                        sub_instance = url_form.save(commit=False)
                        sub_instance.submission_type = SubmissionType.objects.get(identifier='URL')
                        sub_instance.save()
                        
                        # ล้างไฟล์เก่าทิ้ง
                        sub_instance.files.all().delete()
                        form_valid = True

                # --- กรณี B: ส่งแบบ File Upload ---
                elif 'submit_file' in request.POST:
                    file_form = FileSubmissionForm(request.POST, request.FILES)
                    if file_form.is_valid():
                        uploaded_files = request.FILES.getlist('files')
                        
                        # Save Submission Type ก่อน
                        submission.submission_type = SubmissionType.objects.get(identifier='FILE')
                        submission.submitted_link = None 
                        submission.save() 

                        # ลบไฟล์เก่าและบันทึกไฟล์ใหม่
                        submission.files.all().delete() 
                        for f in uploaded_files:
                            SubmissionFile.objects.create(submission=submission, file=f)
                        
                        form_valid = True

                # -----------------------------------------------
                # 🤖 AI AUTO GRADING
                # -----------------------------------------------
                if form_valid:
                    # บันทึกสถานะ WAITING ลง DB ก่อนเรียก AI (กันเหนียว)
                    submission.save()

                    print(f"--- 🚀 AI Grading Started for: {user.email} ---")
                    try:
                        # เรียก AI
                        score, feedback = evaluate_submission_with_ai(submission)

                        # อัปเดตผลลัพธ์
                        submission.ai_score = score
                        submission.ai_feedback = feedback
                        submission.is_graded = True
                        
                        # Reset สถานะ Quiz (เพื่อให้สร้าง Quiz ใหม่ถ้าจำเป็น)
                        submission.quiz_generated = False 
                        
                        # (Optional) ถ้าคะแนน AI ดีมาก อาจจะให้ PASSED เลยก็ได้ แล้วแต่ Logic
                        # if score >= 80: submission.status = 'PASSED'
                        
                        submission.save()

                        # เช็คชื่อฟิลด์คะแนนเต็มดีๆ (score หรือ max_score)
                        max_score = getattr(assignment, 'max_score', 100) 
                        messages.success(request, f'ส่งงานเรียบร้อย! AI ตรวจเบื้องต้นได้: {score}/{max_score}')
                    
                    except Exception as e:
                        print(f"❌ AI Error: {e}")
                        # บันทึก Error Message ไว้ให้นักเรียน/ครูเห็น
                        submission.ai_feedback = f"ระบบได้รับงานแล้ว (แต่ AI ประมวลผลขัดข้อง: {str(e)})"
                        submission.save()
                        messages.warning(request, 'บันทึกการส่งงานสำเร็จ (ระบบตรวจอัตโนมัติขัดข้องชั่วคราว)')

                    return redirect('student:assignment_detail', pk=assignment.pk)
                
                else:
                    messages.error(request, 'กรุณาตรวจสอบข้อมูลไฟล์หรือลิงก์ที่ส่ง')

        except Exception as e:
            print(f"System Error: {e}")
            messages.error(request, f'เกิดข้อผิดพลาดในระบบ: {e}')

    # =========================================================
    # 👀 HANDLE GET REQUEST
    # =========================================================
    
    # เตรียม Form
    url_initial = submission if submission and submission.submission_type and submission.submission_type.identifier == 'URL' else None
    url_form = URLSubmissionForm(instance=url_initial)
    file_form = FileSubmissionForm() 

    context = {
        'assignment': assignment,
        'submission': submission,
        'quiz': quiz,
        'url_form': url_form,
        'file_form': file_form,
        'allow_url_submission': allow_url_submission,
        'allow_file_submission': allow_file_submission,
        'can_submit': can_submit,
        'disable_reason': disable_reason,
        'is_overdue': is_overdue,
        'has_done_quiz': has_done_quiz
    }

    return render(request, 'student/assignment_detail.html', context)
    
@login_required
def generate_quiz_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment
    
    # 1. เช็คสิทธิ์ต่างๆ
    if submission.status != 'PASSED':
        messages.error(request, "ไม่สามารถสร้างแบบทดสอบได้ งานยังไม่ได้รับการอนุมัติ")
        return redirect('student:assignment_detail', pk=assignment.pk)
    
    if not assignment.enable_ai_quiz:
        messages.error(request, "งานนี้อาจารย์ปิดระบบแบบทดสอบไว้")
        return redirect('student:assignment_detail', pk=assignment.pk)

    # 2. ป้องกันการสร้างซ้ำ (ใช้ filter.exists() ชัวร์สุด)
    if Quiz.objects.filter(submission=submission).exists():
        messages.info(request, "แบบทดสอบมีอยู่แล้ว กำลังพาไปหน้าทำแบบทดสอบ...")
        # Redirect ไปหน้าทำข้อสอบ (สมมติชื่อ url คือ student:take_quiz)
        return redirect('student:take_quiz', pk=submission.pk)

    try:
        # 👇 ดึงค่า Config จาก Assignment
        n_questions = assignment.quiz_question_count
        n_choices = assignment.quiz_choice_count

        # 👇 เรียก AI (ฟังก์ชันนี้อาจใช้เวลา 5-10 วินาที)
        questions_data = generate_quiz_with_ai(submission, n_questions, n_choices)
        
        if not questions_data:
            raise Exception("AI ไม่สามารถสร้างคำถามได้ (ข้อมูลว่างเปล่า)")

        # 3. บันทึกลง Database (Atomic)
        with transaction.atomic():
            quiz = Quiz.objects.create(
                submission=submission,
                total_questions=len(questions_data) # ใช้จำนวนจริงที่ AI ส่งมา
            )
            
            for idx, q_data in enumerate(questions_data, 1):
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    text=q_data['question_text'],
                    order=idx
                )
                
                # Loop สร้างตัวเลือก
                for c_data in q_data['choices']:
                    QuizChoice.objects.create(
                        question=question,
                        text=c_data['text'],
                        is_correct=c_data['is_correct']
                    )
            
            # อัปเดตสถานะ Submission (ถ้ามีฟิลด์นี้)
            submission.quiz_generated = True
            submission.save()
        
        messages.success(request, "สร้างแบบทดสอบสำเร็จ! เริ่มทำข้อสอบได้เลย")
        return redirect('student:take_quiz', pk=submission.pk)

    except Exception as e:
        # ⚠️ ดักจับ Error แล้วแจ้งเตือนแทนการปล่อยจอขาว
        print(f"Error generating quiz: {e}") # ปริ้นท์ลง console ไว้อ่านตอน debug
        messages.error(request, f"เกิดข้อผิดพลาดในการสร้างแบบทดสอบ: {str(e)}")
        return redirect('student:assignment_detail', pk=assignment.pk)

@login_required
def take_quiz_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment

    # 🔴 [แก้ไข 1] เช็คว่ามี Quiz หรือยัง "ก่อน" ที่จะดึงตัวแปร quiz
    # ใช้ getattr เพื่อความปลอดภัย หรือเช็ค hasattr ก่อน
    if not hasattr(submission, 'quiz'):
        messages.error(request, "ยังไม่พบแบบทดสอบ กรุณาสร้างก่อน")
        return redirect('student:assignment_detail', pk=assignment.pk)

    # เมื่อมั่นใจว่ามี Quiz ค่อยดึงมาใช้
    quiz = submission.quiz

    # เช็คว่าทำเสร็จไปแล้วหรือยัง
    if quiz.is_completed:
        messages.info(request, "คุณทำแบบทดสอบนี้ไปแล้ว")
        return redirect('student:assignment_detail', pk=assignment.pk)

    # 1. ถ้าเพิ่งเข้าครั้งแรก ให้บันทึกเวลาเริ่ม
    if not quiz.started_at:
        quiz.started_at = timezone.now()
        quiz.save()
    
    # 2. คำนวณเวลาหมดเขต (End Time)
    end_time = quiz.started_at + timedelta(minutes=assignment.quiz_time_limit)
    
    # 3. คำนวณเวลาที่เหลือ
    now = timezone.now()
    remaining_time = (end_time - now).total_seconds()
    
    if remaining_time < 0:
        remaining_time = 0

    # --- กรณีส่งคำตอบ (POST) ---
    if request.method == 'POST':
        # 🔴 [แก้ไข 2] Server-side Time Check: ป้องกันการโกงเวลา
        # เผื่อเวลาให้ Network Delay สัก 60 วินาที (buffer)
        if now > (end_time + timedelta(seconds=60)):
            messages.error(request, "หมดเวลาส่งข้อสอบแล้ว! ระบบไม่บันทึกคะแนน")
            return redirect('student:assignment_detail', pk=assignment.pk)

        score = 0
        # ใช้ related_name หรือ query ให้ถูกต้อง
        questions = quiz.questions.all() 
        total = questions.count()
        
        with transaction.atomic():
            # ลบคำตอบเก่าทิ้งก่อน (กรณี Re-submit หรือ Logic อื่นๆ)
            QuizAnswer.objects.filter(quiz=quiz).delete()

            for question in questions:
                selected_choice_id = request.POST.get(f'question_{question.id}')
                
                if selected_choice_id:
                    # filter ด้วย question เพื่อมั่นใจว่า Choice นี้เป็นของคำถามข้อนี้จริงๆ (กันมั่ว)
                    selected_choice = question.choices.filter(id=selected_choice_id).first()
                    
                    if selected_choice:
                        # 1. บันทึกคำตอบ
                        QuizAnswer.objects.create(
                            quiz=quiz,
                            question=question,
                            selected_choice=selected_choice
                        )

                        # 2. ตรวจคะแนน
                        if selected_choice.is_correct:
                            score += 1
        
        # บันทึกผลลัพธ์ลง Quiz
        quiz.score = score
        quiz.is_completed = True
        quiz.save()
        
        # (Optional) ถ้าคุณมี field เก็บ status ใน Submission อาจจะอัปเดตตรงนี้ด้วยก็ได้
        # submission.quiz_score = score
        # submission.save()
        
        messages.success(request, f"สอบเสร็จสิ้น! คุณได้ {score} / {total} คะแนน")
        return redirect('student:assignment_detail', pk=assignment.pk)

    # --- กรณีเปิดหน้าสอบ (GET) ---
    return render(request, 'student/take_quiz.html', {
        'submission': submission,
        'quiz': quiz,
        'questions': quiz.questions.all(),
        'remaining_time': remaining_time,
    })

@login_required
def quiz_result_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    
    if not hasattr(submission, 'quiz') or not submission.quiz.is_completed:
        messages.error(request, "คุณยังไม่ได้ทำแบบทดสอบ")
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    quiz = submission.quiz
    questions = quiz.questions.prefetch_related('choices').all()
    
    # ดึงคำตอบของนักเรียนมาเก็บใน Dictionary เพื่อให้ใช้ง่ายใน Template
    # Format: { question_id: selected_choice_id }
    student_answers_dict = {
        ans.question.id: ans.selected_choice.id 
        for ans in quiz.student_answers.all()
    }

    return render(request, 'student/quiz_result.html', {
        'submission': submission,
        'quiz': quiz,
        'questions': questions,
        'student_answers_dict': student_answers_dict
    })

@login_required
def report_ai_issue_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    
    # เช็คสิทธิ์ว่าเป็นเจ้าของงานจริงไหม
    if submission.student != request.user:
        messages.error(request, "คุณไม่มีสิทธิ์แจ้งปัญหาในงานนี้")
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    if request.method == 'POST':
        reason = request.POST.get('report_reason', '').strip()
        
        if reason:
            submission.is_reported = True
            submission.report_reason = reason
            submission.save()
            
            messages.success(request, "แจ้งปัญหาเรียบร้อยแล้ว อาจารย์จะเข้ามาตรวจสอบเร็วๆ นี้")
        else:
            messages.warning(request, "กรุณาระบุเหตุผลในการแจ้งปัญหา")

    return redirect('student:assignment_detail', pk=submission.assignment.pk)

