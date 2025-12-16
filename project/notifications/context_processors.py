from .models import Notification

def notifications(request):
    if request.user.is_authenticated:
        # 1. นับจำนวนที่ "ยังไม่อ่าน" (เอาไว้โชว์จุดแดง)
        unread_count = Notification.objects.filter(
            recipient=request.user, 
            is_read=False
        ).count()

        # 2. ดึงรายการแจ้งเตือน "ล่าสุด 10 รายการ" (เอาไว้โชว์ในลิสต์ ทั้งอ่านแล้วและยังไม่)
        # เรียงจากใหม่ไปเก่า (-created_at)
        recent_notis = Notification.objects.filter(
            recipient=request.user
        ).order_by('-created_at')[:10]

        return {
            'navbar_notifications': recent_notis,  # ส่งลิสต์ไปแสดงผล
            'unread_count': unread_count           # ส่งจำนวนไปโชว์จุดแดง
        }
    return {}