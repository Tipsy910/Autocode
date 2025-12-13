from django.db import models
from django.conf import settings # ✅ 1. ใช้ settings แทนการ import User ตรงๆ

class Notification(models.Model):
    # ✅ 2. เปลี่ยน User เป็น settings.AUTH_USER_MODEL
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        # ตรงนี้ต้องระวังนิดนึง เพราะ settings.AUTH_USER_MODEL เป็นแค่ string
        # แต่ self.recipient คือ Object User จริงๆ ใช้งานได้ปกติ
        return f"To {self.recipient.email}: {self.message}"