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
        student_profile = user.student_profile
    except Students.DoesNotExist:
        messages.error(request, 'บัญชีของคุณไม่ใช่บัญชีนักเรียน')
        return redirect('student:dashboard') # หรือหน้าอื่นที่เหมาะสม

    # 3. ตรวจสอบสิทธิ์ว่านักเรียนอยู่ในห้องเรียนนี้หรือไม่
    if student_profile not in assignment.room.students.all():
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าถึงงานนี้ (ไม่อยู่ในห้องเรียน)')
        return redirect('student:dashboard')

    # 4. ดึง Submission เดิม (ถ้าเคยส่งแล้ว)
    submission = Submission.objects.filter(student=user, assignment=assignment).first()

    # =========================================================
    # 🛑 HANDLE POST REQUEST (การส่งงาน)
    # =========================================================
    if request.method == 'POST':
        # ใช้ Transaction เพื่อความปลอดภัยของข้อมูล (ถ้า Error ให้ Rollback ทั้งหมด)
        try:
            with transaction.atomic():
                # สร้างหรือดึง Submission Object
                submission, created = Submission.objects.get_or_create(
                    student=user, 
                    assignment=assignment
                )
                submission.submitted_at = timezone.now()
                
                form_valid = False
                
                # --- กรณี A: ส่งแบบ URL (Colab) ---
                if 'submit_url' in request.POST:
                    url_form = URLSubmissionForm(request.POST, instance=submission)
                    if url_form.is_valid():
                        sub_instance = url_form.save(commit=False)
                        # ต้องมั่นใจว่ามี Type 'URL' ใน DB
                        sub_instance.submission_type = SubmissionType.objects.get(identifier='URL')
                        sub_instance.save()
                        
                        # ล้างไฟล์เก่าทิ้ง (เพราะส่งแบบ URL แทนแล้ว)
                        sub_instance.files.all().delete()
                        form_valid = True

                # --- กรณี B: ส่งแบบ File Upload ---
                elif 'submit_file' in request.POST:
                    file_form = FileSubmissionForm(request.POST, request.FILES)
                    # หมายเหตุ: file_form อาจจะไม่ต้อง bind instance ก็ได้ถ้าเราจัดการไฟล์เอง
                    if file_form.is_valid():
                        submission.submission_type = SubmissionType.objects.get(identifier='PY')
                        submission.submitted_link = None # ล้าง Link เก่าทิ้ง
                        submission.save()

                        # ลบไฟล์เก่าแล้วบันทึกไฟล์ใหม่
                        submission.files.all().delete()
                        for f in request.FILES.getlist('files'):
                            SubmissionFile.objects.create(submission=submission, file=f)
                        
                        form_valid = True

                # -----------------------------------------------
                # 🤖 AI AUTO GRADING (ทำงานเมื่อฟอร์มถูกต้อง)
                # -----------------------------------------------
                if form_valid:
                    print(f"--- 🚀 เริ่มต้นการตรวจ AI สำหรับ: {user.email} ---")
                    try:
                        # เรียกฟังก์ชันจาก ai_utils.py
                        score, feedback = evaluate_submission_with_ai(submission)

                        # บันทึกผล
                        submission.ai_score = score
                        submission.ai_feedback = feedback
                        submission.is_graded = True
                        
                        # Reset สถานะ Quiz (เพราะส่งงานใหม่ Quiz เก่าอาจไม่ตรงแล้ว)
                        submission.quiz_generated = False 
                        submission.save()

                        messages.success(request, f'ส่งงานเรียบร้อย! AI ตรวจแล้วได้คะแนน: {score}/{assignment.score}')
                    
                    except Exception as e:
                        print(f"❌ AI Error: {e}")
                        # บันทึกว่าส่งแล้ว แต่ AI มีปัญหา (จะได้ไม่ Error 500)
                        submission.ai_feedback = f"ระบบรับงานแล้ว แต่ AI ขัดข้องชั่วคราว: {e}"
                        submission.save()
                        messages.warning(request, 'ส่งงานสำเร็จ (แต่ระบบตรวจอัตโนมัติขัดข้องในขณะนี้)')

                    return redirect('student:assignment_detail', pk=assignment.pk)
                else:
                    messages.error(request, 'กรุณาตรวจสอบข้อมูลที่กรอก (Form Invalid)')

        except Exception as e:
            print(f"System Error: {e}")
            messages.error(request, f'เกิดข้อผิดพลาดในระบบ: {e}')

    # =========================================================
    # 👀 HANDLE GET REQUEST (เตรียมข้อมูลแสดงผล)
    # =========================================================
    
    # 1. เตรียม Form (ถ้ามี submission เดิม ให้โหลดค่ามาใส่)
    url_form = URLSubmissionForm(instance=submission) if submission and submission.submission_type and submission.submission_type.identifier == 'URL' else URLSubmissionForm()
    file_form = FileSubmissionForm() # File form มักจะไม่ pre-fill ไฟล์กลับเข้าไป

    # 2. เช็คว่า Assignment นี้อนุญาตให้ส่งแบบไหนบ้าง (เพื่อไปคุม Frontend)
    allowed_types = assignment.allowed_submission_types.all()
    allowed_identifiers = {t.identifier for t in allowed_types}

    context = {
        'assignment': assignment,
        'submission': submission,
        'url_form': url_form,
        'file_form': file_form,
        'allow_url_submission': 'URL' in allowed_identifiers,
        'allow_file_submission': 'PY' in allowed_identifiers or 'IPYNB' in allowed_identifiers,
    }

    return render(request, 'student/assignment_detail.html', context)

    # 1. ดึงข้อมูล Submission และคำถามที่เกี่ยวข้อง
    submission = get_object_or_404(Submission, pk=pk, user=request.user)
    questions = submission.generated_questions.all().order_by('order')
    
    if not questions:
        # ถ้าไม่มีควิซ ให้เด้งกลับไปหน้างาน
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    # --- กรณีส่งคำตอบ (POST) ---
    if request.method == 'POST':
        score = 0
        total_questions = questions.count()
        results = [] # เก็บผลลัพธ์ไว้โชว์ว่าข้อไหนถูก/ผิด

        for question in questions:
            # ชื่อ field ใน html คือ "question_ID"
            selected_choice_id = request.POST.get(f'question_{question.id}')
            
            is_correct = False
            correct_choice = question.choices.filter(is_correct=True).first()
            
            if selected_choice_id:
                selected_choice = GeneratedChoice.objects.filter(id=selected_choice_id).first()
                if selected_choice and selected_choice.is_correct:
                    score += 1
                    is_correct = True
            
            results.append({
                'question': question,
                'is_correct': is_correct,
                'correct_choice': correct_choice
            })

        # (Optional) คุณอาจจะอยากบันทึกคะแนน Quiz ลง Database ตรงนี้
        # submission.quiz_score = score 
        # submission.save()

        # ส่งผลลัพธ์ไปหน้า Result
        return render(request, 'student/quiz_result.html', {
            'submission': submission,
            'score': score,
            'total': total_questions,
            'results': results
        })

    # --- กรณีเปิดหน้าเว็บ (GET) ---
    return render(request, 'student/take_quiz.html', {
        'submission': submission,
        'questions': questions
    })
    
@login_required
def generate_quiz_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment # ดึง Assignment ออกมา

    # 2. ป้องกันการสร้างซ้ำ (ถ้ามีแล้ว ให้ไปหน้าทำข้อสอบเลย)
    if hasattr(submission, 'quiz_set'):
        messages.info(request, "แบบทดสอบมีอยู่แล้ว")
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    try:
        # 👇 ดึงค่า Config จาก Assignment
        n_questions = assignment.quiz_question_count
        n_choices = assignment.quiz_choice_count

        # 👇 ส่งค่าไปให้ฟังก์ชัน AI
        questions_data = generate_quiz_with_ai(submission, n_questions, n_choices)
        
        if not questions_data:
            raise Exception("AI ไม่ส่งข้อมูลกลับมา")

        # บันทึกลง Database
        with transaction.atomic():
            quiz = Quiz.objects.create(submission=submission,total_questions=n_questions)
            
            for idx, q_data in enumerate(questions_data, 1):
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    text=q_data['question_text'],
                    order=idx
                )
                
                # AI อาจจะส่งมาเกินหรือขาด เราต้องดักไว้ หรือ Loop ตามที่ AI ส่งมา
                # แต่ถ้า AI ทำงานถูก มันจะส่งมาตามจำนวน n_choices
                for c_data in q_data['choices']:
                    QuizChoice.objects.create(
                        question=question,
                        text=c_data['text'],
                        is_correct=c_data['is_correct']
                    )
            
            submission.quiz_generated = True
            submission.save()

        messages.success(request, f"สร้างแบบทดสอบ {n_questions} ข้อเรียบร้อยแล้ว!")

    except Exception as e:
        print(f"Error: {e}")
        messages.error(request, "เกิดข้อผิดพลาดในการสร้างแบบทดสอบ")

    return redirect('student:assignment_detail', pk=submission.assignment.pk)

@login_required
def take_quiz_view(request, pk):
    submission = get_object_or_404(Submission, pk=pk)
    
    # เช็คว่ามี Quiz หรือยัง
    if not hasattr(submission, 'quiz'):
        messages.error(request, "ยังไม่พบแบบทดสอบ กรุณาสร้างก่อน")
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    quiz = submission.quiz

    # ถ้าทำเสร็จแล้ว ไม่ให้ทำซ้ำ (หรือแล้วแต่ Logic คุณ)
    if quiz.is_completed:
        messages.info(request, "คุณทำแบบทดสอบนี้ไปแล้ว")
        # อาจจะสร้างหน้า result แยก หรือส่งกลับไปหน้าเดิม
        return redirect('student:assignment_detail', pk=submission.assignment.pk)

    # --- กรณีส่งคำตอบ (POST) ---
    if request.method == 'POST':
        score = 0
        total = quiz.questions.count()
        
        # ใช้ Transaction เพื่อความปลอดภัย
        with transaction.atomic():
            # ลบคำตอบเก่าทิ้งก่อน (กรณีเผื่อมีระบบสอบแก้ตัวในอนาคต)
            QuizAnswer.objects.filter(quiz=quiz).delete()

            for question in quiz.questions.all():
                selected_choice_id = request.POST.get(f'question_{question.id}')
                
                if selected_choice_id:
                    selected_choice = question.choices.filter(id=selected_choice_id).first()
                    
                    if selected_choice:
                        # ✅ 1. บันทึกคำตอบที่นักเรียนเลือกลง DB
                        QuizAnswer.objects.create(
                            quiz=quiz,
                            question=question,
                            selected_choice=selected_choice
                        )

                        # ✅ 2. ตรวจว่าถูกไหม
                        if selected_choice.is_correct:
                            score += 1
        
        # บันทึกคะแนนรวม
        quiz.score = score
        quiz.is_completed = True
        quiz.save()
        
        messages.success(request, f"สอบเสร็จสิ้น! คุณได้ {score} / {total} คะแนน")
        # เปลี่ยน Redirect ไปหน้า Assignment Detail เหมือนเดิม
        return redirect('student:assignment_detail', pk=submission.assignment.pk)
    # --- กรณีเปิดหน้าสอบ (GET) ---
    return render(request, 'student/take_quiz.html', {
        'submission': submission,
        'quiz': quiz
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