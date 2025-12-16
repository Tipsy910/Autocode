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


@receiver(post_save, sender='room.Submission') 
def notify_submission_status_change(sender, instance, created, **kwargs):
    """
    ทำงานเมื่อสถานะการส่งงานเปลี่ยนแปลง (เช่น อาจารย์ส่งคืน หรือ ให้ผ่าน)
    """
    # ถ้าเป็นการสร้างครั้งแรก (นักเรียนเพิ่งกดส่ง) เราอาจจะไม่ต้องแจ้งเตือนตัวเอง
    # หรือถ้าต้องการแจ้งว่า "ส่งสำเร็จ" ก็เอา if created ออกได้
    if created:
        return

    submission = instance
    student_user = submission.student # สมมติว่าเป็น FK ไปหา User
    assignment = submission.assignment
    
    # เช็คสถานะเพื่อสร้างข้อความที่เหมาะสม
    message = ""
    verb = ""
    
    if submission.status == 'REJECT':
        message = f"⚠️ งานถูกส่งคืน: {assignment.title} (กรุณาแก้ไข)"
        verb = "ส่งคืนงาน"
    elif submission.status == 'PASSED':
        message = f"✅ งานผ่านแล้ว: {assignment.title}"
        verb = "ตรวจแล้ว"
    else:
        # ถ้าเป็นสถานะอื่น (เช่น Pending) อาจไม่ต้องแจ้งเตือน
        return

    # --- ส่วนที่ 1: สร้าง Notification ในเว็บ ---
    # ลิงก์ไปยังหน้ารายละเอียดงานของนักเรียน
    link = f"/student/assignment/{assignment.id}/"
    
    # ป้องกันการแจ้งเตือนซ้ำ (Optional): เช็คว่ามีการแจ้งเตือนล่าสุดเรื่องเดิมไปหรือยัง
    # ถ้าไม่ซีเรียสเรื่องแจ้งเตือนซ้ำตอนกด Save หลายรอบ ก็ลบ 3 บรรทัดนี้ได้
    recent_noti = Notification.objects.filter(
        recipient=student_user,
        link=link,
        is_read=False
    ).last()
    
    # ถ้ายังไม่มีแจ้งเตือน หรือข้อความเปลี่ยนไป ให้สร้างใหม่
    if not recent_noti or recent_noti.message != message:
        Notification.objects.create(
            recipient=student_user,
            message=message,
            link=link
        )
        print(f"🔔 Notified student {student_user.email} about status: {submission.status}")