# users/forms.py
from django import forms
from .models import User, Students, Teachers

class UserImportForm(forms.Form):
    file = forms.FileField(label="Excel (.xlsx) หรือ CSV (.csv)")
    dry_run = forms.BooleanField(
        required=False, initial=False,
        help_text="ทดสอบก่อน (ไม่บันทึกจริง)"
    )



class StudentProfileImageForm(forms.ModelForm):
    class Meta:
        model = Students
        fields = ['profile_image']

class TeacherProfileImageForm(forms.ModelForm):
    class Meta:
        model = Teachers
        fields = ['profile_image']