# room/views.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from .models import AIConfiguration, AIModelOption
from .forms import AIConfigurationForm
from .utils import test_ai_connection  # อย่าลืม import ฟังก์ชันเทสที่เราเพิ่งเขียน

# ==========================================
# Helper Function: เช็คว่าเป็น Admin หรือไม่
# ==========================================
def is_admin(user):
    return user.is_authenticated and user.is_superuser

# ==========================================
# View: หน้าตั้งค่า AI (สำหรับ Admin)
# ==========================================
@login_required(login_url='/login/')
@user_passes_test(is_admin) 
def admin_ai_settings_view(request):
    # 1. ดึง Config ล่าสุดมาเตรียมไว้ (ถ้ามี)
    config = AIConfiguration.objects.last()
    
    # 2. ถ้ามีการส่งข้อมูลมา (กดปุ่ม Save หรือ Test)
    if request.method == 'POST':
        
        # สร้าง Form รับค่าจากที่กรอกมา
        form = AIConfigurationForm(request.POST, instance=config)

        # ---------------------------------------------------
        # กรณี A: กดปุ่ม "เช็คสถานะ" (name="test_connection")
        # ---------------------------------------------------
        if 'test_connection' in request.POST:
            # ดึงค่า API Key ที่กรอกมา (ยังไม่บันทึกลง DB ก็ได้)
            api_key = request.POST.get('api_key')
            model_id = request.POST.get('current_model') # ได้มาเป็น ID

            # ตรวจสอบว่ากรอกครบไหม
            if not api_key:
                messages.error(request, "กรุณากรอก API Key ก่อนทดสอบ")
            elif not model_id:
                messages.error(request, "กรุณาเลือกโมเดลก่อนทดสอบ")
            else:
                try:
                    # ดึง Object โมเดลจาก Database เพื่อเอาค่า api_value (เช่น gemini-1.5-flash)
                    model_option = AIModelOption.objects.get(id=model_id)
                    
                    # ส่งไป Test ที่ utils.py
                    success, result_msg = test_ai_connection(api_key, model_option.api_value)
                    
                    if success:
                        messages.success(request, f"✅ {model_option.name}: {result_msg}")
                    else:
                        messages.error(request, f"❌ {model_option.name}: {result_msg}")
                        
                except AIModelOption.DoesNotExist:
                    messages.error(request, "ไม่พบข้อมูลโมเดลที่เลือกในระบบ")

            # หมายเหตุ: กด Test เสร็จ เราจะ render หน้าเดิมพร้อมข้อมูลที่กรอกค้างไว้ 
            # (ไม่ต้อง redirect เพื่อให้ Admin ตัดสินใจต่อว่าจะ Save ไหม)

        # ---------------------------------------------------
        # กรณี B: กดปุ่ม "บันทึก" (Submit ปกติ)
        # ---------------------------------------------------
        else:
            if form.is_valid():
                form.save()
                messages.success(request, "บันทึกการตั้งค่า AI เรียบร้อยแล้ว")
                return redirect('admin_ai_settings') # เปลี่ยนเป็นชื่อ URL name ที่คุณตั้งไว้
            else:
                messages.error(request, "เกิดข้อผิดพลาด กรุณาตรวจสอบข้อมูล")

    # 3. กรณีเป็น GET Request (เปิดหน้าเว็บครั้งแรก)
    else:
        form = AIConfigurationForm(instance=config)

    # 4. ส่งข้อมูลไปที่ Template
    return render(request, 'admin_panel/ai_settings.html', {
        'form': form
    })