from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from users.models import Students
from room.models import Room, Assignment, Announcement, Submission, SubmissionType, SubmissionFile
from django.utils import timezone
from .forms import JoinRoomForm
from student.forms import URLSubmissionForm, FileSubmissionForm
from django.contrib import messages
from dotenv import load_dotenv
import os
import google.generativeai as genai
import json
from pydantic import BaseModel, Field
from typing import List, Optional

# ===================================================================
# AI SETUP (วางไว้ด้านบนไฟล์ ต่อจาก Imports)
# ===================================================================

# --- 2. สร้าง Model Pydantic สำหรับ "Feedback" ---
class AiFeedback(BaseModel):
    score: int = Field(description="คะแนนที่ประเมินได้ (เต็ม 10)")
    feedback: str = Field(description="ข้อความ Feedback โดยละเอียดสำหรับนักเรียน")

# (หมายเหตุ: เราสร้าง Pydantic ของ Quiz ไว้เผื่อ แต่ยังไม่ใช้)
class AiChoice(BaseModel):
    choice_text: str = Field(description="ข้อความในตัวเลือก")
    is_correct: bool = Field(description="ตัวเลือกนี้ถูกหรือผิด")

class AiQuestion(BaseModel):
    question_text: str = Field(description="ข้อความคำถาม")
    choices: List[AiChoice] = Field(description="ลิสต์ของตัวเลือก 4 ข้อ")

class AiQuiz(BaseModel):
    questions: List[AiQuestion] = Field(description="ลิสต์ของคำถาม")

load_dotenv()
# --- 3. ตั้งค่า API KEY ---
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    print("❌ (CONFIG) ไม่พบ GOOGLE_API_KEY")

# --- 4. สร้าง Model และ Function เรียก AI (แบบ Structured) ---
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"🚨 (CONFIG) ไม่สามารถโหลด Gemini Model: {e}")
    model = None # ตั้งค่าเป็น None ถ้าโหลดไม่สำเร็จ

PROMPT_GRADING_INTELLIGENT = """
คุณคือผู้ช่วยสอน (TA) ผู้เชี่ยวชาญด้านการเขียนโค้ด Python
งานหลักของคุณคือการตรวจประเมิน "โค้ดของนักเรียน" ว่าทำงานได้ถูกต้องตรงตาม "คำอธิบายโจทย์" หรือไม่

คุณจะได้รับข้อมูล 3 ส่วน:
1. "คำอธิบายโจทย์" (นี่คือ Requirement หลักที่ใช้ตัดสิน)
2. "โค้ดของนักเรียน"
3. "Test Case" (นี่คือส่วนเสริม ถ้ามีก็ใช้ประกอบ ถ้าไม่มีก็ไม่เป็นไร)

โปรดประเมินว่าโค้ดของนักเรียนแก้ปัญหานี้ได้ถูกต้องหรือไม่ ให้คะแนน (เต็ม 10)
และให้ Feedback โดยละเอียด โดยเน้นที่การเปรียบเทียบกับ "คำอธิบายโจทย์" เป็นหลัก

--- 1. คำอธิบายโจทย์ (โจทย์หลัก) ---
{problem_description}
--- END คำอธิบายโจทย์ ---

--- 2. โค้ดของนักเรียน ---
{student_code}
--- END โค้ดของนักเรียน ---

--- 3. TEST CASE (ส่วนเสริม ถ้ามี) ---
{test_case_data}
--- END TEST CASE ---

กรุณาประเมินผลและตอบกลับตาม Schema ที่กำหนด
"""


def call_gemini_structured(prompt_text, pydantic_schema_class):
    """
    เรียก Gemini API ในโหมด Structured Output (บังคับตอบตาม Schema)
    """
    print("\n--- ⏳ กำลังส่งคำสั่ง (Structured) ให้ Gemini ---")
    
    # ตรวจสอบว่า Model พร้อมใช้งานหรือไม่
    if model is None:
        print("🚨 (CALL_GEMINI) Model ไม่ได้ถูกโหลด")
        return None
        
    try:
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=pydantic_schema_class # 👈 บังคับ Schema
        )
        
        response = model.generate_content(
            prompt_text,
            generation_config=generation_config
        )
        
        print("✅ Gemini ตอบกลับ (Structured) สำเร็จ")
        return response.text
        
    except Exception as e:
        print(f"🚨 เกิดข้อผิดพลาดในการเรียก Gemini (Structured): {e}")
        return None

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
    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        student_profile = request.user.student_profile
    except Students.DoesNotExist:
        messages.error(request, 'ไม่พบบัญชีนักเรียนของคุณ')
        return redirect('student:dashboard') # (หรือหน้า login)
    
    # --- ตรวจสอบสิทธิ์ ---
    if student_profile not in assignment.room.students.all():
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าถึงงานนี้')
        return redirect('student:dashboard')
        
    # --- ดึงข้อมูลการส่งงานเดิม (ถ้ามี) ---
    try:
        submission = Submission.objects.get(student=request.user, assignment=assignment)
    except Submission.DoesNotExist:
        submission = None

    # =================================================
    # --- ⭐️ LOGIC การจัดการ POST (การส่งงาน) ---
    # =================================================
    if request.method == 'POST':
        
        # 1. ดึงหรือสร้าง Object Submission หลัก
        submission, created = Submission.objects.get_or_create(
            student=request.user,
            assignment=assignment
        )
        
        # --- 2.1 กรณีส่งเป็น URL (เช็คจาก name="submit_url") ---
        if 'submit_url' in request.POST:
            form = URLSubmissionForm(request.POST, instance=submission)
            if form.is_valid():
                try:
                    url_sub_type = SubmissionType.objects.get(identifier='URL') 
                except SubmissionType.DoesNotExist:
                    messages.error(request, 'ระบบมีปัญหา: ไม่พบประเภทการส่งงานแบบ URL')
                    return redirect('student:assignment_detail', pk=assignment.pk)

                sub_instance = form.save(commit=False)
                sub_instance.submission_type = url_sub_type
                sub_instance.submitted_at = timezone.now()
                
                # รีเซ็ตค่า AI (เพราะส่ง Link จะไม่ตรวจ)
                sub_instance.ai_score = 0
                sub_instance.ai_feedback = None
                sub_instance.quiz_generated = False
                sub_instance.save()
                
                # เคลียร์ไฟล์เก่า (ถ้าเคยส่งไฟล์)
                sub_instance.files.all().delete()
                
                messages.success(request, 'ส่งงาน (Link) เรียบร้อยแล้ว')
                return redirect('student:assignment_detail', pk=assignment.pk)

        # --- 2.2 กรณีส่งเป็น FILE UPLOAD (เช็คจาก name="submit_file") ---
        elif 'submit_file' in request.POST:
            form = FileSubmissionForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    # (ปรับ identifier ตามที่คุณตั้งค่าในระบบ)
                    file_sub_type = SubmissionType.objects.get(identifier='PY') 
                except SubmissionType.DoesNotExist:
                    messages.error(request, 'ระบบมีปัญหา: ไม่พบประเภทการส่งงานแบบ File')
                    return redirect('student:assignment_detail', pk=assignment.pk)

                # อัปเดต Submission หลัก
                submission.submission_type = file_sub_type
                submission.submitted_at = timezone.now()
                submission.submitted_link = None # เคลียร์ Link เก่า
                submission.save()
                
                # เคลียร์ไฟล์เก่าทั้งหมด (ส่งทับ)
                submission.files.all().delete()
                
                # วน Loop บันทึกไฟล์ใหม่
                uploaded_files = request.FILES.getlist('files')
                for f in uploaded_files:
                    SubmissionFile.objects.create(
                        submission=submission,
                        file=f
                    )
                
                # -----------------------------------------------------------------
                #  🤖 START: สั่ง AI ตรวจงานอัตโนมัติ (เฉพาะ Feedback)
                # -----------------------------------------------------------------
                print("--- 🤖 เริ่มการตรวจด้วย AI ---")
                try:
                    # --- 1. ดึงข้อมูลที่ "ต้องมี" ---
                    student_file_obj = submission.files.first()
                    problem_description = assignment.description
                    
                    if not api_key:
                        raise Exception("ไม่พบ GOOGLE_API_KEY ในระบบ")
                    if model is None:
                         raise Exception("Gemini Model ไม่พร้อมใช้งาน")
                    if not student_file_obj:
                         raise Exception("ไม่พบไฟล์โค้ดที่นักเรียนส่ง")
                    if not problem_description:
                        raise Exception("อาจารย์ยังไม่ได้ใส่ 'คำอธิบายโจทย์' (Description)")

                    # อ่านโค้ดนักเรียน
                    student_code = student_file_obj.file.read().decode('utf-8')
                    student_file_obj.file.seek(0)
                    
                    # --- 2. ดึงข้อมูล "ส่วนเสริม" (Test Case) ---
                    test_case_data = "ไม่มี Test Case ให้ (ให้ AI ประเมินจากโจทย์และโค้ดโดยตรง)"
                    test_case_file_obj = assignment.test_case_file
                    
                    if test_case_file_obj:
                        test_case_data = test_case_file_obj.file.read().decode('utf-8')
                        test_case_file_obj.file.seek(0)
                        print("--- ℹ️ พบ Test Case ส่วนเสริม ---")

                    # --- 3. สร้าง Prompt ---
                    final_prompt = PROMPT_GRADING_INTELLIGENT.format(
                        problem_description=problem_description, # 👈 ป้อนโจทย์
                        student_code=student_code,             # 👈 ป้อนโค้ด
                        test_case_data=test_case_data          # 👈 ป้อน Test Case (ถ้ามี)
                    )
                    
                    # --- 4. เรียก AI (แบบ Structured) ---
                    ai_response_grading = call_gemini_structured(
                        final_prompt, 
                        AiFeedback  # (ยังใช้ Schema Feedback เหมือนเดิม)
                    )
                    
                    if ai_response_grading:
                        data = json.loads(ai_response_grading)
                        submission.ai_feedback = data.get('feedback', 'AI processing error.')
                        submission.ai_score = data.get('score', 0)
                        submission.quiz_generated = False # ยังไม่สร้างควิซ
                        submission.save()
                        print("✅ บันทึก Feedback (Intelligent) จาก AI สำเร็จ")
                        messages.success(request, f'ส่งงานเรียบร้อยแล้ว ระบบตรวจ AI สำเร็จ')
                    else:
                        raise Exception("AI ไม่สามารถประมวลผลคำขอได้ (ได้ค่า None)")
                        
                except Exception as e:
                    print(f"--- 🚨 เกิดข้อผิดพลาดระหว่างการตรวจ AI: {e} ---")
                    submission.ai_feedback = f"เกิดข้อผิดพลาดในการประมวลผล AI: {e}"
                    submission.ai_score = 0
                    submission.quiz_generated = False
                    submission.save()
                    messages.warning(request, f'ส่งงานสำเร็จ แต่เกิดปัญหาในการตรวจ AI: {e}')
                # -----------------------------------------------------------------
                #  🤖 END: สิ้นสุดการตรวจ AI
                # -----------------------------------------------------------------
                return redirect('student:assignment_detail', pk=assignment.pk)


    # =================================================
    # --- ⭐️ LOGIC การจัดการ GET (การแสดงผล) ---
    # =================================================
    
    # 1. ดึงข้อมูลประเภทการส่งที่อนุญาต (จาก M2M field)
    allowed_identifiers = {t.identifier for t in assignment.allowed_submission_types.all()}
    allow_url_submission = 'URL' in allowed_identifiers
    allow_file_submission = 'PY' in allowed_identifiers or 'IPYNB' in allowed_identifiers
    
    # 2. สร้าง Form เปล่า
    url_form = URLSubmissionForm()
    file_form = FileSubmissionForm()
    
    # 3. ถ้ามี submission เดิมอยู่ ให้โหลดข้อมูลมาใส่ Form
    if submission:
        if submission.submission_type and submission.submission_type.identifier == 'URL':
            url_form = URLSubmissionForm(instance=submission)
        # (File Form ไม่ต้อง pre-populate)

    context = {
        'assignment': assignment,
        'submission': submission,
        'url_form': url_form,
        'file_form': file_form,
        'allow_url_submission': allow_url_submission,
        'allow_file_submission': allow_file_submission,
    }
    return render(request, 'student/assignment_detail.html', context)
