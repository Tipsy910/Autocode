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
import requests
from urllib.parse import urlparse
import json
import ast 

def check_colab_link_accessibility(url):
    """
    ฟังก์ชันช่วยเช็ค:
    1. รูปแบบ URL ถูกต้อง
    2. Domain คือ colab.research.google.com เป๊ะๆ
    3. ลิงก์เปิดได้จริง (Public) ไม่ติด Login
    """
    # 1. เช็ค Domain แบบเข้มงวด
    try:
        parsed = urlparse(url)
        # ตรวจว่าต้องเป็น https และ domain ต้องเป๊ะ
        if parsed.scheme != "https" or parsed.netloc != "colab.research.google.com":
            return False, "ลิงก์ต้องขึ้นต้นด้วย https://colab.research.google.com/ เท่านั้น"
    except Exception:
        return False, "รูปแบบ URL ไม่ถูกต้อง"

    # 2. ยิง Request ไปเช็คว่าลิงก์เปิดได้ไหม (Ping)
    try:
        # ใส่ User-Agent เพื่อไม่ให้ Google บล็อกว่าเราเป็นบอท
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # timeout=5 คือถ้าเกิน 5 วิให้ตัดจบ (กันเว็บค้าง)
        response = requests.get(url, headers=headers, timeout=5)

        # ถ้า Google Redirect ไปหน้า Login (accounts.google.com) แสดงว่าไม่ได้เปิดแชร์
        if "accounts.google.com" in response.url or "signin" in response.url:
            return False, "ลิงก์นี้เป็นส่วนตัว (Private) กรุณาเปิดแชร์เป็น 'Anyone with the link' (ทุกคนที่มีลิงก์)"
        
        # ถ้า Response ไม่ใช่ 200 OK
        if response.status_code != 200:
            return False, f"ไม่สามารถเข้าถึงลิงก์ได้ (Status: {response.status_code})"
            
    except requests.exceptions.RequestException:
        return False, "ไม่สามารถเชื่อมต่อกับลิงก์ได้ (ลิงก์อาจเสียหรือหมดอายุ)"

    return True, ""

def validate_file_content(uploaded_file):
    """
    ฟังก์ชันเปิดอ่านเนื้อหาไฟล์เพื่อเช็คว่าเป็น .py หรือ .ipynb ของจริงหรือไม่
    """
    filename = uploaded_file.name.lower()
    
    try:
        # อ่านไฟล์ทั้งหมดขึ้นมาใน Memory เพื่อตรวจสอบ
        content = uploaded_file.read()
        
        # ⚠️ สำคัญมาก: อ่านเสร็จต้องเลื่อน cursor กลับไปที่จุดเริ่มต้น (0) 
        # ไม่งั้นตอน save ลง database ไฟล์จะกลายเป็นไฟล์เปล่า
        uploaded_file.seek(0)
        
        # --- กรณีเป็น .ipynb (ต้องเป็น JSON และมีคีย์ 'cells') ---
        if filename.endswith('.ipynb'):
            try:
                # ลองแปลง bytes เป็น string แล้วโหลด JSON
                data = json.loads(content.decode('utf-8'))
                
                # เช็คโครงสร้างพื้นฐานของ Notebook
                if 'cells' not in data or 'metadata' not in data:
                    return False, "ไฟล์ .ipynb เสียหาย หรือโครงสร้างไม่ถูกต้อง"
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False, "ไม่ใช่ไฟล์ Jupyter Notebook ที่ถูกต้อง (อาจเป็นไฟล์อื่นเปลี่ยนนามสกุลมา)"

        # --- กรณีเป็น .py (ต้องเป็น Text ที่ Compile เป็น Python ได้) ---
        elif filename.endswith('.py'):
            try:
                source_code = content.decode('utf-8')
                # ลอง parse ดูว่าเป็น Python Syntax หรือไม่
                ast.parse(source_code)
            except UnicodeDecodeError:
                return False, "ไฟล์นี้ไม่ใช่ Text File (อาจเป็น Binary/Image เปลี่ยนชื่อมา)"
            except SyntaxError:
                # ถ้า Parse ไม่ผ่าน แปลว่า Syntax ผิด แต่ก็ยังถือว่าเป็น Text File ได้ 
                # แต่ถ้าจะเอาชัวร์ว่าส่งโค้ดรันได้ ให้ return False ตรงนี้ได้เลย
                # ในที่นี้ขออนุญาตปล่อยผ่านกรณี Syntax Error (เผื่อเด็กเขียนโค้ดผิดแต่ส่งไฟล์ถูกประเภท)
                pass 
                
    except Exception as e:
        return False, f"เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}"

    return True, ""

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
    try:
        # พยายามหางาน
        assignment = Assignment.objects.get(pk=pk)
    except Assignment.DoesNotExist:
        # ถ้าหาไม่เจอ (งานถูกลบ) ให้เด้งกลับ Dashboard
        return render(request, 'student/assignment_not_found.html')
    user = request.user
    
    # 2. ตรวจสอบว่า User เป็นนักเรียนจริงหรือไม่
    try:
        if not hasattr(user, 'student_profile'):
             raise Exception("User has no student profile") 
        student_profile = user.student_profile
    except Exception:
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
    has_done_quiz = True if quiz and quiz.is_completed else False 

    can_submit = True
    disable_reason = ""

    # เงื่อนไขที่ 1: งานผ่านแล้ว (PASSED) -> ปิด
    if submission and submission.status == 'PASSED':
        can_submit = False
        disable_reason = "งานนี้ผ่านการตรวจสอบแล้ว"

    # เงื่อนไขที่ 2: เลยกำหนดส่ง และ ไม่อนุญาตให้ส่งช้า (และไม่ใช่การแก้ตัว)
    elif is_overdue and not assignment.allow_late_submission:
        if submission and submission.status == 'REJECT':
            can_submit = True 
        else:
            can_submit = False
            disable_reason = "หมดเวลาส่งงานแล้ว (ไม่อนุญาตให้ส่งล่าช้า)"
    
    # =========================================================
    # 📤 HANDLE POST REQUEST (การส่งงาน)
    # =========================================================
    if request.method == 'POST':
        if not can_submit:
            messages.error(request, f"ไม่สามารถส่งงานได้: {disable_reason}")
            return redirect('student:assignment_detail', pk=pk)

        try:
            with transaction.atomic():
                # 1. ดึง Object มาก่อน (แต่ยังไม่ต้องแก้ค่า Status/Time)
                submission, created = Submission.objects.get_or_create(
                    student=user, 
                    assignment=assignment
                )

                # ตัวแปรสำหรับเช็คว่าผ่านการตรวจสอบหรือยัง
                form_valid = False
                
                # --- กรณี A: ส่งแบบ URL ---
                if 'submit_url' in request.POST:
                    # 🛡️ GUARD: เช็คว่ามีไฟล์ติดมาด้วยไหม?
                    # ถ้า User เผลอแนบไฟล์ไว้ แล้วมากดส่ง URL เราควรเตือน เพราะเขาอาจกดปุ่มผิด
                    if len(request.FILES) > 0:
                        messages.warning(request, "⚠️ คุณมีการแนบไฟล์ค้างไว้! หากต้องการส่ง URL กรุณานำไฟล์ออกก่อน หรือหากต้องการส่งไฟล์ ให้กดปุ่ม 'ส่งงาน' ในแท็บไฟล์")
                        return redirect('student:assignment_detail', pk=pk)
                    
                    url_form = URLSubmissionForm(request.POST, instance=submission)
                    
                    if url_form.is_valid():
                        raw_link = url_form.cleaned_data.get('submitted_link').strip() # strip() ตัดช่องว่างหัวท้าย
                        
                        # ✅ เรียกฟังก์ชันตรวจสอบความปลอดภัยและการเข้าถึง
                        is_valid_link, error_message = check_colab_link_accessibility(raw_link)

                        if not is_valid_link:
                            messages.error(request, f"❌ {error_message}")
                            # หยุดการทำงาน ไม่บันทึก และ redirect กลับ
                            return redirect('student:assignment_detail', pk=pk)

                        # --- ถ้าผ่านทุกด่าน ก็บันทึกตามปกติ ---
                        submission.submitted_at = timezone.now()
                        submission.status = 'WAITING' 
                        submission.is_late = is_overdue
                        submission.is_graded = False
                        
                        sub_instance = url_form.save(commit=False)
                        sub_instance.submission_type = SubmissionType.objects.get(identifier='URL')
                        sub_instance.save()
                        
                        sub_instance.files.all().delete()
                        form_valid = True
                        messages.success(request, "ส่งลิงก์งานเรียบร้อยแล้ว")
                    else:
                        # 🔴 จุดแก้ไข: ดัก Error ของ URL ตรงนี้เลย (แก้ปัญหา System Error)
                        print(f"❌ URL Form Error: {url_form.errors}")
                        # แปลง Error เป็นข้อความ string เพื่อแสดง
                        err_msg = ""
                        for field, errors in url_form.errors.items():
                            err_msg += f"{field}: {', '.join(errors)} "
                        messages.error(request, f'ข้อมูลลิงก์ไม่ถูกต้อง: {err_msg}')

                # --- กรณี B: ส่งแบบ File Upload ---
                elif 'submit_file' in request.POST:
                    
                    submitted_link = request.POST.get('submitted_link', '').strip()
                    if submitted_link:
                         messages.warning(request, "⚠️ คุณมีการกรอก URL ค้างไว้! กรุณาลบ URL ออกก่อนส่งไฟล์ เพื่อป้องกันความสับสน")
                         return redirect('student:assignment_detail', pk=pk)

                    file_form = FileSubmissionForm(request.POST, request.FILES)
                    
                    if file_form.is_valid():
                        uploaded_files = request.FILES.getlist('files')
                        
                        # 🔍 CHECK 2: ตรวจสอบทั้งนามสกุล และ "ไส้ใน"
                        for f in uploaded_files:
                            # 2.1 เช็คนามสกุลก่อน (เร็ว)
                            if not f.name.lower().endswith(('.py', '.ipynb')):
                                messages.error(request, f"❌ ไฟล์ '{f.name}' นามสกุลไม่ถูกต้อง! (รับเฉพาะ .py, .ipynb)")
                                return redirect('student:assignment_detail', pk=pk)
                            
                            # 2.2 เช็คเนื้อหาไฟล์ (Advanced)
                            is_valid_content, err_msg = validate_file_content(f)
                            if not is_valid_content:
                                messages.error(request, f"❌ ไฟล์ '{f.name}' มีปัญหา: {err_msg}")
                                return redirect('student:assignment_detail', pk=pk)

                        # --- ถ้าผ่านทุกไฟล์ Save ได้เลย ---
                        submission.submitted_at = timezone.now()
                        submission.status = 'WAITING'
                        submission.is_late = is_overdue
                        submission.is_graded = False
                        
                        submission.submission_type = SubmissionType.objects.get(identifier='FILE')
                        submission.submitted_link = None 
                        submission.save() 

                        submission.files.all().delete() 
                        for f in uploaded_files:
                            SubmissionFile.objects.create(submission=submission, file=f)
                        
                        form_valid = True
                        messages.success(request, "ส่งไฟล์งานเรียบร้อยแล้ว") # เพิ่มแจ้งเตือนความสำเร็จ
                    
                    else:
                        print(f"❌ File Form Error: {file_form.errors}")
                        messages.error(request, 'ไฟล์ที่อัปโหลดไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง')

                # -----------------------------------------------
                # 🤖 AI AUTO GRADING (ทำงานเมื่อ form_valid = True เท่านั้น)
                # -----------------------------------------------
                if form_valid:
                    submission.save()
                    print(f"--- 🚀 AI Grading Started for: {user.email} ---")
                    try:
                        score, feedback = evaluate_submission_with_ai(submission)
                        
                        submission.ai_score = score
                        submission.ai_feedback = feedback
                        submission.is_graded = True
                        submission.quiz_generated = False 
                        submission.save()

                        max_score = getattr(assignment, 'max_score', 100) 
                        messages.success(request, f'ส่งงานเรียบร้อย! AI ตรวจได้: {score}/{max_score}')
                    
                    except Exception as e:
                        print(f"❌ AI Error: {e}")
                        submission.ai_feedback = f"ระบบได้รับงานแล้ว (AI ขัดข้อง: {str(e)})"
                        submission.save()
                        messages.warning(request, 'ส่งงานสำเร็จ (ระบบตรวจอัตโนมัติขัดข้องชั่วคราว)')

                    return redirect('student:assignment_detail', pk=assignment.pk)
                
                # ลบ else: สุดท้ายออก เพราะย้ายไปจัดการในแต่ละ if/elif แล้ว

        except Exception as e:
            print(f"System Error: {e}")
            messages.error(request, f'เกิดข้อผิดพลาดในระบบ: {e}')

    # =========================================================
    # 👀 HANDLE GET REQUEST
    # =========================================================
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

