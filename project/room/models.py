from django.db import models
from django.conf import settings
import string
import random
from users.models import Students, Teachers
from django.contrib.auth.models import User

# ฟังก์ชันที่สร้างรหัสเชิญที่ไม่ซ้ำกัน
def generate_invite_code():
    length = 6
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        if not Room.objects.filter(invite_code=code).exists():
            return code

def assignment_problem_file_path(instance, filename):
    # Path: media/problem_files/room_1/assign_5/problem.pdf
    return f"problem_files/room_{instance.room.id}/assign_{instance.id}/{filename}"

def assignment_test_case_file_path(instance, filename):
    """
    สร้าง Path: media/test_case_files/room_<id>/assign_<id>/filename
    """
    return f"test_case_files/room_{instance.room.id}/assign_{instance.id}/{filename}"

def submission_file_path(instance, filename):
    # สร้าง Path: media/submission_files/room_1/assign_5/user_10/filename.pdf
    return f"submission_files/room_{instance.submission.assignment.room.id}/assign_{instance.submission.assignment.id}/user_{instance.submission.student.id}/{filename}"

class Room(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_rooms')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    invite_code = models.CharField(max_length=6, unique=True, default=generate_invite_code)
    students = models.ManyToManyField(Students, related_name='joined_rooms', blank=True)
    teachers = models.ManyToManyField(Teachers, related_name='taught_rooms', blank=True)
    cover_image = models.ImageField(
        upload_to='rooms/covers/',  # จะเก็บไฟล์ไว้ที่ media/rooms/covers/
        blank=True,                 # อนุญาตให้ field นี้ว่างได้
        null=True                   # อนุญาตให้เป็น null ในฐานข้อมูล
    )

    def __str__(self):
        return self.name

class SubmissionType(models.Model):
    name = models.CharField(max_length=100, help_text="ชื่อที่แสดงผล เช่น 'ไฟล์ Python', 'Google Colab Link'")
    identifier = models.CharField(max_length=10, unique=True, help_text="ชื่อเฉพาะสำหรับอ้างอิงในโค้ด เช่น 'PY', 'URL', 'IPYNB'")

    def __str__(self):
        return self.name

class Assignment(models.Model):
    """
    โมเดลสำหรับ "งานหลัก" ที่อาจารย์สร้าง
    พร้อมการตั้งค่าสำหรับควิซที่จะถูกสร้างโดย AI
    """
    room = models.ForeignKey('room.Room', on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    score = models.FloatField(blank=True, null=True)
    allow_late_submission = models.BooleanField(default=False, verbose_name="อนุญาตให้ส่งเกินเวลา")

    # --- ส่วนตั้งค่าสำหรับ AI Quiz Generation ---
    test_case_file = models.FileField(
        upload_to= assignment_test_case_file_path, blank=True, null=True,
        help_text="ไฟล์ Test Case (.json, .txt, .zip) เพื่อให้ AI ใช้อ้างอิงสร้างควิซ"
    )
    
    problem_file = models.FileField(
        upload_to=assignment_problem_file_path,
        blank=True, 
        null=True,
        help_text="อัปโหลดไฟล์โจทย์ (PDF, PNG, JPG)"
    )
    
    quiz_question_count = models.PositiveIntegerField(
        default=5, help_text="จำนวนคำถามในควิซที่ต้องการให้ AI สร้าง"
    )
    quiz_choice_count = models.PositiveIntegerField(
        default=4, help_text="จำนวนตัวเลือกในแต่ละคำถาม"
    )
    # -----------------------------------------
    allowed_submission_types = models.ManyToManyField(
        SubmissionType, 
        related_name='assignments',
        blank=True,
        help_text="เลือกประเภทไฟล์ที่อนุญาตให้นักเรียนส่งสำหรับงานชิ้นนี้"
    )
    
    enable_ai_quiz = models.BooleanField(
        default=True, 
        help_text="เปิดให้นักเรียนสร้างแบบทดสอบจาก AI หรือไม่"
    )
    
    author = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    related_name='created_assignments')

    
    created_at = models.DateTimeField(auto_now_add=True)

    quiz_time_limit = models.PositiveIntegerField(
        default=10, 
        verbose_name="เวลาทำแบบทดสอบ (นาที)",
        help_text="ระบุเวลาเป็นนาที (เช่น 15)"
    )

    def __str__(self):
        return self.title

class Submission(models.Model):
    assignment = models.ForeignKey('room.Assignment', on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    # 1. ระบุประเภทของการส่งงานครั้งนี้
    submission_type = models.ForeignKey(
        SubmissionType, 
        on_delete=models.PROTECT, # ป้องกันการลบประเภทไฟล์ที่มีการส่งงานแล้ว
        related_name='submissions',
        null=True, # ตั้งเป็น null=True เพื่อให้ migration ผ่านได้ง่ายสำหรับข้อมูลเก่า
        blank=True
    )
    
    # 2. เพิ่ม field ใหม่สำหรับเก็บลิงก์
    submitted_link = models.URLField(
        max_length=500, # เผื่อสำหรับ URL ยาวๆ
        blank=True,
        null=True
    )
    # ----------------------------------------
    ai_score = models.IntegerField(
        default=0, 
        help_text="คะแนน (เต็ม 10) ที่ได้จาก AI"
    )
    ai_feedback = models.TextField(
        blank=True, 
        null=True, 
        help_text="Feedback ที่ AI สร้างให้"
    )
    quiz_generated = models.BooleanField(default=False)
    quiz_score = models.IntegerField(default=0, help_text="คะแนนที่นักเรียนทำได้จาก Quiz")
    
    # สถานะของงาน
    STATUS_CHOICES = [
        ('PENDING', 'รอส่ง/รอตรวจ'),
        ('GRADED', 'AI ตรวจแล้ว (รออนุมัติ)'),
        ('PASSED', 'ผ่านแล้ว (Approved)'),
        ('REJECT', 'ส่งคืนให้แก้ไข (Revision)'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # การแจ้งปัญหาการตรวจจากนักเรียน
    is_reported = models.BooleanField(default=False, help_text="นักเรียนกดแจ้งปัญหาการตรวจ")
    report_reason = models.TextField(blank=True, null=True, help_text="เหตุผลที่แจ้งปัญหา")
    
    # ความเห็นจากอาจารย์ (Optional)
    teacher_comment = models.TextField(blank=True, null=True, help_text="ความเห็นจากอาจารย์")
    
    # วันที่อาจารย์กดตรวจ
    graded_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f'Submission by {self.student.username} for {self.assignment.title}'

class SubmissionFile(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=submission_file_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"File for submission {self.submission.id} ({self.file.name})"


class Announcement(models.Model):
    """
    โมเดลสำหรับเก็บประกาศ 1 ชิ้น
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='announcements')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] # เรียงจากใหม่สุดไปเก่าสุดเสมอ

    def __str__(self):
        return f"Announcement in {self.room.name}"

class AnnouncementFile(models.Model):
    """
    โมเดลสำหรับเก็บไฟล์ 1 ไฟล์ ที่แนบไปกับประกาศ
    """
    announcement = models.ForeignKey(
        Announcement, 
        on_delete=models.CASCADE, 
        related_name='files' # <-- ทำให้เราเรียก .files.all() จาก announcement ได้
    )
    file = models.FileField(upload_to='announcements/files/')

    def __str__(self):
        # ดึงชื่อไฟล์จาก path
        return self.file.name.split('/')[-1]
    
class Quiz(models.Model):
    # ผูกกับ Submission (1 การส่งงาน มี 1 ควิซ)
    submission = models.OneToOneField(
        'Submission', 
        on_delete=models.CASCADE, 
        related_name='quiz' 
    )
    
    # วันที่สร้างควิซ
    created_at = models.DateTimeField(auto_now_add=True)
    
    # เก็บเวลาที่นักเรียนเริ่มกดทำ
    started_at = models.DateTimeField(null=True, blank=True)

    # คะแนนที่ทำได้จริง (เช่น สอบได้ 4)
    score = models.IntegerField(default=0, help_text="คะแนนที่นักเรียนทำได้")
    
    # คะแนนเต็ม/จำนวนข้อทั้งหมด (เช่น เต็ม 5) -> สำคัญมาก เอาไว้คำนวณเกรด
    total_questions = models.IntegerField(default=0, help_text="จำนวนข้อสอบทั้งหมดในชุดนี้")

    # สถานะว่าทำเสร็จหรือยัง (True = ส่งกระดาษคำตอบแล้ว)
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        status = "Completed" if self.is_completed else "Pending"
        return f"Quiz for {self.submission.student.user.email} - {status} ({self.score}/{self.total_questions})"

# ==========================================
# 2. ตารางเก็บคำถาม (Question)
# ==========================================
class QuizQuestion(models.Model):
    # ผูกกับ Quiz ถ้าลบ Quiz คำถามจะหายไปด้วย
    quiz = models.ForeignKey(
        Quiz, 
        on_delete=models.CASCADE, 
        related_name='questions'
    )
    
    text = models.TextField(help_text="โจทย์คำถาม")
    order = models.PositiveIntegerField(default=0, help_text="ลำดับข้อ (1, 2, 3...)")

    class Meta:
        ordering = ['order'] # สั่งให้เรียงตามลำดับเสมอเวลาดึงข้อมูล

    def __str__(self):
        return f"ข้อที่ {self.order}: {self.text[:50]}..."

# ==========================================
# 3. ตารางเก็บตัวเลือก (Choices)
# ==========================================
class QuizChoice(models.Model):
    # ผูกกับ Question ถ้าลบคำถาม ตัวเลือกจะหายไปด้วย
    question = models.ForeignKey(
        QuizQuestion, 
        on_delete=models.CASCADE, 
        related_name='choices'
    )
    
    text = models.CharField(max_length=255, help_text="ข้อความตัวเลือก")
    is_correct = models.BooleanField(default=False, help_text="ทำเครื่องหมายถ้าเป็นข้อที่ถูก")

    def __str__(self):
        mark = "✅" if self.is_correct else ""
        return f"{mark} {self.text}"

class QuizAnswer(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='student_answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(QuizChoice, on_delete=models.CASCADE)

    def __str__(self):
        return f"Ans: {self.selected_choice} for {self.question}"