# users/forms.py
from django import forms
from .models import User, Students, Teachers

class StudentProfileImageForm(forms.ModelForm):
    class Meta:
        model = Students
        fields = ['profile_image']

class TeacherProfileImageForm(forms.ModelForm):
    class Meta:
        model = Teachers
        fields = ['profile_image']