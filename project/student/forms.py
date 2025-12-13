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

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True  # <--- บรรทัดนี้คือหัวใจสำคัญ แก้ ValueError

# 2. สร้าง Field ใหม่เพื่อให้ Validate ผ่าน (Optional แต่แนะนำ)
class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

# 3. นำไปใช้ใน Form ของคุณ
class FileSubmissionForm(forms.Form):
    files = MultipleFileField(  # <--- เปลี่ยนจาก forms.FileField เป็น MultipleFileField ที่เราสร้าง
        label="อัปโหลดไฟล์ (.py, .ipynb) (เลือกได้หลายไฟล์)",
        required=True
    )