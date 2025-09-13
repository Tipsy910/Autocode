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
    allowed_submission_types = models.ManyToManyField(
        SubmissionType, 
        related_name='assignments',
        blank=True,
        help_text="เลือกประเภทไฟล์ที่อนุญาตให้นักเรียนส่งสำหรับงานชิ้นนี้"
    )
    
    author = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    related_name='created_assignments')


    created_at = models.DateTimeField(auto_now_add=True)

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
    
    # --- ส่วนที่เปลี่ยนแปลงและเพิ่มเข้ามา ---
    
    # 1. ระบุประเภทของการส่งงานครั้งนี้
    submission_type = models.ForeignKey(
        SubmissionType, 
        on_delete=models.PROTECT, # ป้องกันการลบประเภทไฟล์ที่มีการส่งงานแล้ว
        related_name='submissions',
        null=True, # ตั้งเป็น null=True เพื่อให้ migration ผ่านได้ง่ายสำหรับข้อมูลเก่า
        blank=True
    )

    # 2. แก้ไข field เดิมให้สามารถเว้นว่างได้
    submitted_file = models.FileField(
        upload_to='submissions/files/',
        blank=True, 
        null=True
    )
    
    # 3. เพิ่ม field ใหม่สำหรับเก็บลิงก์
    submitted_link = models.URLField(
        max_length=500, # เผื่อสำหรับ URL ยาวๆ
        blank=True,
        null=True
    )

    # ----------------------------------------
    
    quiz_generated = models.BooleanField(default=False)

    def __str__(self):
        return f'Submission by {self.student.username} for {self.assignment.title}'

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
        return f"Announcement in {self.room.name} by {self.author.email}"

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