from django import forms
from room.models import Room, Assignment, Announcement

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name','cover_image']

class AssignmentForm(forms.ModelForm):
    # กำหนด widget สำหรับ due_date แยกต่างหากเพื่อให้ปรับแต่งได้ง่าย
    due_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'}
        ),
        required=False,
        label="กำหนดส่ง"
    )

    class Meta:
        model = Assignment
        
        # 1. เพิ่ม 'score' และ 'allowed_submission_types' เข้าไปใน fields
        fields = [
            'title', 
            'description',
            'problem_file',
            'due_date', 
            'score',  # <-- เพิ่มเข้ามา
            'allowed_submission_types', # <-- เพิ่มเข้ามา
            'test_case_file', 
            'quiz_question_count', 
            'quiz_choice_count',
            'enable_ai_quiz',
            'allow_late_submission',
            'quiz_time_limit',
        ]
        
        # 2. เพิ่ม Label ที่จะแสดงในฟอร์มสำหรับ field ใหม่
        labels = {
            'title': 'หัวข้อ/ชื่องาน',
            'description': 'คำอธิบาย (ไม่บังคับ)',
            'score': 'คะแนนเต็ม', # <-- เพิ่มเข้ามา
            'allowed_submission_types': 'ประเภทการส่งงานที่อนุญาต', # <-- เพิ่มเข้ามา
            'test_case_file': 'ไฟล์ Test Case (สำหรับ AI)',
            'quiz_question_count': 'จำนวนคำถามที่ต้องการให้ AI สร้าง',
            'quiz_choice_count': 'จำนวนตัวเลือกต่อคำถาม',
            'allow_late_submission': 'อนุญาตให้ส่งเกินเวลา',
        }
        
        # 3. กำหนด Widget สำหรับ field ใหม่ๆ และปรับของเก่าให้สวยงาม
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'score': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}), # <-- เพิ่มเข้ามา
            'allowed_submission_types': forms.CheckboxSelectMultiple, # <-- ใช้ Checkbox เพื่อให้เลือกง่าย
            'problem_file': forms.FileInput(attrs={'class': 'form-control'}),
            'test_case_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'enable_ai_quiz': forms.CheckboxInput(attrs={
                'class': 'form-check-input', 
                'role': 'switch',}),
            'quiz_question_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'quiz_choice_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '2'}),
            'allow_late_submission': forms.CheckboxInput(attrs={
                'class': 'form-check-input', 
                'role': 'switch',}),
        }

class JoinRoomForm(forms.Form):
    code = forms.CharField(label='รหัสเชิญ', max_length=6)

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ประกาศอะไรบางอย่างถึงชั้นเรียนของคุณ...'
            })
        }
        labels = {
            'content': '' # ไม่ต้องแสดง Label
        }