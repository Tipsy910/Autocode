import google.generativeai as genai
from room.models import AIConfiguration

def test_ai_connection(api_key, model_api_value):
    """
    ฟังก์ชันสำหรับ Admin กดปุ่ม 'เช็คสถานะ'
    หน้าที่: ลองส่งข้อความสั้นๆ ไปหา Google เพื่อดูว่า Model นี้ยังตอบกลับไหม
    
    Args:
        api_key (str): Key ที่กรอกในฟอร์ม
        model_api_value (str): ชื่อโมเดลที่ส่งไป API (เช่น 'gemini-1.5-flash')
        
    Returns:
        (bool, str): (สำเร็จหรือไม่, ข้อความตอบกลับ/Error)
    """
    try:
        # 1. ตั้งค่า Key
        genai.configure(api_key=api_key)
        
        # 2. เลือกโมเดล (ตามที่ Admin เลือกใน Dropdown)
        model = genai.GenerativeModel(model_api_value)
        
        # 3. ลองส่งข้อความสั้นๆ (Ping)
        # ใช้คำว่าง่ายๆ เพื่อประหยัด Token และดูว่ามันตอบสนองไหม
        response = model.generate_content("Ping")
        
        # 4. เช็คผลลัพธ์
        if response:
            # ถ้าตอบกลับมาได้ แปลว่า โมเดลนี้ยังเปิดใช้งานปกติ (Alive)
            return True, f"ใช้งานได้ปกติ (Status: OK)"
        else:
            return False, "เชื่อมต่อได้ แต่ไม่มีข้อมูลตอบกลับ (Empty Response)"
            
    except Exception as e:
        # ถ้าพังตรงนี้ แปลว่า:
        # - ชื่อโมเดลผิด (Google เลิกใช้รุ่นนี้แล้ว) -> 404 Not Found
        # - API Key ผิด -> 400 Invalid Key
        # - เน็ตหลุด
        return False, f"ใช้งานไม่ได้ (Error: {str(e)})"

def get_active_model():
    """
    ฟังก์ชันสำหรับดึง Model ตัวที่ Active ล่าสุดจาก Database
    คืนค่า: object model ที่พร้อมใช้งาน หรือ None ถ้าหาไม่เจอ
    """
    # 1. ดึงค่า Config ที่ Active = True
    config = AIConfiguration.objects.filter(is_active=True).first()
    
    # 2. ถ้าไม่มีการตั้งค่า หรือไม่มี API Key ให้จบการทำงาน
    if not config or not config.api_key:
        print("❌ AI Config Error: ไม่พบการตั้งค่า Active หรือไม่มี API Key")
        return None

    try:
        # 3. ตั้งค่า Key ใหม่ทุกครั้งที่เรียก (เผื่อแอดมินเพิ่งเปลี่ยนมา)
        genai.configure(api_key=config.api_key)
        
        # 4. โหลด Model ตามชื่อที่ระบุใน Database
        model_name = config.current_model.api_value
        model = genai.GenerativeModel(model_name)
        
        return model
        
    except Exception as e:
        print(f"🚨 Error loading model: {e}")
        return None