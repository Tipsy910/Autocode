from django import forms
from room.models import Submission

class JoinRoomForm(forms.Form):
    code = forms.CharField(label='รหัสเชิญ', max_length=6)


class URLSubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['submitted_link'] # <--- ✅ แก้ไขให้ตรงกับ Model
        widgets = {
            'submitted_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://....'}),
        }
        labels = {
            'submitted_link': 'ลิงก์ผลงาน (URL)'
        }

class FileSubmissionForm(forms.Form):
    files = forms.FileField(
        widget=forms.FileInput(attrs={
            # 'multiple': True,  <--- ลบบรรทัดนี้ หรือคอมเมนต์ไว้
            'class': 'form-control' # <--- เหลือไว้แค่ class
        }),
        required=True,
        label="อัปโหลดไฟล์ (.py, .ipynb) (เลือกได้หลายไฟล์)"
    )