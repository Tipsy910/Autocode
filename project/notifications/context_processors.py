from .models import Notification

def notifications(request):
    if request.user.is_authenticated:
        # ดึงแจ้งเตือนที่ยังไม่อ่าน
        unread_notis = Notification.objects.filter(recipient=request.user, is_read=False)
        return {
            'unread_notifications': unread_notis,
            'unread_count': unread_notis.count()
        }
    return {}