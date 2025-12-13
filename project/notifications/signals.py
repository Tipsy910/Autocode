# notifications/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

from notifications.models import Notification

# ✅ แก้ไขตรงนี้: เปลี่ยน 'classroom' เป็น 'room' ตามชื่อแอปของคุณ
@receiver(post_save, sender='room.Assignment') 
def create_assignment_notification(sender, instance, created, **kwargs):
    """
    ทำงานอัตโนมัติเมื่ออาจารย์สร้าง Assignment ใหม่
    """
    if created:
        assignment = instance
        room = assignment.room
        students = room.students.all()
        
        # เตรียมลิงก์
        base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
        assignment_link = f"{base_url}/student/assignment/{assignment.id}/"

        # --- ส่วนที่ 1: สร้าง Notification ในเว็บ ---
        notification_list = []
        for student_profile in students:
            noti = Notification(
                recipient=student_profile.user,
                message=f"📚 งานใหม่: {assignment.title} ({room.name})",
                link=f"/student/assignment/{assignment.id}/"
            )
            notification_list.append(noti)
        
        Notification.objects.bulk_create(notification_list)
        print(f"🔔 Created in-app notifications for {len(notification_list)} students.")

        # --- ส่วนที่ 2: ส่งอีเมล ---
        subject = f"📚 งานใหม่: {assignment.title} - วิชา {room.name}"
        from_email = settings.DEFAULT_FROM_EMAIL
        
        for student_profile in students:
            try:
                user = student_profile.user
                if user.email:
                    context = {
                        'student_name': user.first_name or user.username,
                        'room_name': room.name,
                        'assignment_title': assignment.title,
                        'due_date': assignment.due_date,
                        'score': assignment.score,
                        'action_url': assignment_link
                    }
                    
                    html_message = render_to_string('notifications/emails/new_assignment.html', context)
                    plain_message = strip_tags(html_message)

                    send_mail(
                        subject,
                        plain_message,
                        from_email,
                        [user.email],
                        html_message=html_message,
                        fail_silently=True
                    )
            except Exception as e:
                print(f"❌ Failed to send email: {e}")