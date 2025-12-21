# notifications/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from notifications.models import Notification

# ✅ 1. แจ้งเตือนเมื่ออาจารย์สั่งงานใหม่ (Assignment)
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
            # ตรวจสอบว่า user มีอยู่จริง
            if student_profile.user:
                noti = Notification(
                    recipient=student_profile.user,
                    message=f"📚 งานใหม่: {assignment.title} ({room.name})",
                    link=f"/student/assignment/{assignment.id}/",
                    room=room  # ✅ ใส่ข้อมูล Room
                )
                notification_list.append(noti)
        
        if notification_list:
            Notification.objects.bulk_create(notification_list)
            print(f"🔔 Created in-app notifications for {len(notification_list)} students.")

        # --- ส่วนที่ 2: ส่งอีเมล ---
        subject = f"📚 งานใหม่: {assignment.title} - วิชา {room.name}"
        from_email = settings.DEFAULT_FROM_EMAIL
        
        for student_profile in students:
            try:
                user = student_profile.user
                if user and user.email:
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


# ✅ 2. แจ้งเตือนเมื่อสถานะการส่งงานเปลี่ยน (Submission Status)
@receiver(post_save, sender='room.Submission') 
def notify_submission_status_change(sender, instance, created, **kwargs):
    """
    ทำงานเมื่อสถานะการส่งงานเปลี่ยนแปลง (PASSED หรือ REJECT)
    จะทำการ 1. แจ้งเตือนในเว็บ และ 2. ส่งอีเมลหานักเรียน
    """
    if created:
        return

    submission = instance
    student_user = submission.student
    assignment = submission.assignment
    room = assignment.room # ✅ ดึง Room เตรียมไว้
    
    # ดึง Base URL เพื่อสร้างลิงก์เต็มในอีเมล
    base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
    relative_link = f"/student/assignment/{assignment.id}/"
    full_url = f"{base_url}{relative_link}"

    # เตรียมตัวแปรสำหรับ Logic
    message = ""
    should_notify = False
    
    # =========================================================
    # CASE 1: งานผ่าน (PASSED)
    # =========================================================
    if submission.status == 'PASSED':
        message = f"✅ งานผ่านแล้ว: {assignment.title}"
        should_notify = True
        
        # --- ส่งอีเมล (Approve) ---
        try:
            subject = f"✅ ยินดีด้วย! งาน '{assignment.title}' ผ่านการตรวจสอบแล้ว"
            context = {
                'student_name': student_user.get_full_name() or student_user.username,
                'assignment_title': assignment.title,
                'ai_score': submission.ai_score,
                'teacher_comment': submission.teacher_comment,
                'action_url': full_url,
            }
            html_message = render_to_string('notifications/emails/approve_submission.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject, 
                plain_message, 
                settings.DEFAULT_FROM_EMAIL, 
                [student_user.email], 
                html_message=html_message, 
                fail_silently=True
            )
            print(f"📧 Sent Approve Email to {student_user.email}")
        except Exception as e:
            print(f"❌ Failed to send Approve Email: {e}")

    # =========================================================
    # CASE 2: ส่งคืน (REJECT)
    # =========================================================
    elif submission.status == 'REJECT':
        message = f"⚠️ งานถูกส่งคืน: {assignment.title} (กรุณาแก้ไข)"
        should_notify = True

        # --- ส่งอีเมล (Reject) ---
        try:
            subject = f"⚠️ แจ้งแก้ไขงาน: {assignment.title}"
            context = {
                'student_name': student_user.get_full_name() or student_user.username,
                'assignment_title': assignment.title,
                'teacher_comment': submission.teacher_comment,
                'action_url': full_url,
            }
            html_message = render_to_string('notifications/emails/reject_submission.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject, 
                plain_message, 
                settings.DEFAULT_FROM_EMAIL, 
                [student_user.email], 
                html_message=html_message, 
                fail_silently=True
            )
            print(f"📧 Sent Reject Email to {student_user.email}")
        except Exception as e:
            print(f"❌ Failed to send Reject Email: {e}")

    # =========================================================
    # 🔔 ส่วนสร้าง Web Notification (ใช้ร่วมกัน)
    # =========================================================
    if should_notify:
        # เช็คกันซ้ำ (Notification De-duplication)
        recent_noti = Notification.objects.filter(
            recipient=student_user,
            link=relative_link,
            is_read=False
        ).last()
        
        # ถ้าไม่มีแจ้งเตือนล่าสุด หรือข้อความเปลี่ยนไป ให้สร้างใหม่
        if not recent_noti or recent_noti.message != message:
            Notification.objects.create(
                recipient=student_user,
                message=message,
                link=relative_link,
                room=room  # ✅ ใส่ข้อมูล Room (สำคัญสำหรับการกรอง)
            )
            print(f"🔔 Web Notification Created: {message}")


# ✅ 3. แจ้งเตือนเมื่อมีประกาศใหม่ (Announcement)
@receiver(post_save, sender='room.Announcement') 
def notify_new_announcement(sender, instance, created, **kwargs):
    """
    ทำงานเมื่อมีการโพสต์ประกาศใหม่ในห้องเรียน
    ✅ แจ้งเตือนเฉพาะในแอป (ไม่ส่งเมล)
    """
    if created:
        post = instance
        room = post.room       
        author = post.author   
        
        # ดึงรายชื่อนักเรียนทั้งหมดในห้อง
        students = room.students.all()
        
        # ลิงก์ไปยังหน้าห้องเรียน
        relative_link = f"/student/room/{room.id}/"

        notification_list = []
        
        for student_profile in students:
            # เช็คความปลอดภัย: ต้องมี user และ ต้องไม่ใช่คนโพสต์เอง
            if student_profile.user and student_profile.user != author:
                
                # ตัดข้อความให้สั้นลงถ้าประกาศยาวเกินไป
                short_content = post.content[:30] + "..." if len(post.content) > 30 else post.content
                
                noti = Notification(
                    recipient=student_profile.user,
                    message=f"📢 ประกาศใหม่จาก {author.first_name}: {short_content}",
                    link=relative_link,
                    room=room, # ✅ ใส่ข้อมูล Room
                    is_read=False
                )
                notification_list.append(noti)
        
        if notification_list:
            Notification.objects.bulk_create(notification_list)
            print(f"🔔 Created {len(notification_list)} notifications for new announcement in {room.name}")