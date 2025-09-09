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

# In your app's models.py

# from rooms.models import Room

class Assignment(models.Model):
    """
    โมเดลสำหรับ "งานหลัก" ที่อาจารย์สร้าง
    พร้อมการตั้งค่าสำหรับควิซที่จะถูกสร้างโดย AI
    """
    room = models.ForeignKey('room.Room', on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)

    # --- ส่วนตั้งค่าสำหรับ AI Quiz Generation ---
    test_case_file = models.FileField(
        upload_to='assignments/test_cases/', blank=True, null=True,
        help_text="ไฟล์ Test Case (.json, .txt, .zip) เพื่อให้ AI ใช้อ้างอิงสร้างควิซ"
    )
    quiz_question_count = models.PositiveIntegerField(
        default=5, help_text="จำนวนคำถามในควิซที่ต้องการให้ AI สร้าง"
    )
    quiz_choice_count = models.PositiveIntegerField(
        default=4, help_text="จำนวนตัวเลือกในแต่ละคำถาม"
    )
    # -----------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Submission(models.Model):
    assignment = models.ForeignKey('room.Assignment', on_delete=models.CASCADE, related_name='submissions')
    
    # --- จุดที่ต้องตรวจสอบ ---
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # <-- ต้องเป็นแบบนี้เท่านั้น ห้ามเป็น User โดยตรง
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    # -----------------------

    submitted_file = models.FileField(upload_to='submissions/files/')
    submitted_at = models.DateTimeField(auto_now_add=True)
    quiz_generated = models.BooleanField(default=False)

    def __str__(self):
        # การเข้าถึง field ของ User model ต้องทำผ่าน self.student
        return f'Submission by {self.student.email} for {self.assignment.title}'

# --- โมเดลสำหรับควิซที่ AI สร้างขึ้นมาโดยเฉพาะ ---

class GeneratedQuiz(models.Model):
    """
    โมเดลสำหรับเก็บ "ชุดควิซ" ที่ AI สร้างขึ้นสำหรับ Submission ชิ้นเดียว
    (One-to-One Relationship กับ Submission)
    """
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name='generated_quiz')
    created_at = models.DateTimeField(auto_now_add=True)
    # ข้อมูลการทำควิซของนักเรียน
    score = models.FloatField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Quiz for Submission ID: {self.submission.id}"

class GeneratedQuestion(models.Model):
    """
    เก็บคำถาม 1 ข้อ ที่ AI สร้างขึ้น
    """
    quiz = models.ForeignKey(GeneratedQuiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    correct_answer_text = models.TextField(help_text="เก็บ text ของคำตอบที่ถูกต้องที่ AI บอกมา") # เพื่อใช้เปรียบเทียบ

class GeneratedChoice(models.Model):
    """
    เก็บตัวเลือก 1 ตัว ที่ AI สร้างขึ้น
    """
    question = models.ForeignKey(GeneratedQuestion, on_delete=models.CASCADE, related_name='choices')
    choice_text = models.TextField()