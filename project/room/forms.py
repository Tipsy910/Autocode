from .models import AIConfiguration, AIModelOption
from django import forms

class AIConfigurationForm(forms.ModelForm):
    class Meta:
        model = AIConfiguration
        fields = ['is_active', 'api_key', 'current_model']
        # widgets เดิมของคุณที่ทำให้หน้าตาสวย และซ่อน Password
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'api_key': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'API Key'}), # ✅ ใส่ PasswordInput ตรงนี้
            'current_model': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'current_model': 'เลือกโมเดล AI ที่ต้องการใช้',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ ดึงเฉพาะโมเดลที่ Active มาแสดง (Code เดิมของคุณ)
        self.fields['current_model'].queryset = AIModelOption.objects.filter(is_active=True)

    # ✅✅ เพิ่มฟังก์ชันนี้เข้าไป! เพื่อป้องกันการเลือก Model ซ้ำ
    def clean_current_model(self):
        model = self.cleaned_data.get('current_model')
        
        # ค้นหาว่าใน Database มีการใช้โมเดลนี้ไปหรือยัง
        existing = AIConfiguration.objects.filter(current_model=model)
        
        # ถ้าเป็นการแก้ไข (Edit) ให้ยกเว้นตัวเอง
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
            
        if existing.exists():
            raise forms.ValidationError(f"❌ โมเดล '{model.name}' ถูกตั้งค่าไปแล้ว กรุณาเลือกอันอื่น")
            
        return model