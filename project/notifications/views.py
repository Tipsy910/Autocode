from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Notification

# ✅ 1. ฟังก์ชันแสดงประวัติการแจ้งเตือนทั้งหมด (History)
@login_required
def notification_history_view(request):
    # 1. ดึงแจ้งเตือนพื้นฐาน
    query = Notification.objects.filter(recipient=request.user)
    
    # 2. ✅ Logic การกรองห้องเรียน
    selected_room_id = request.GET.get('room')
    if selected_room_id and selected_room_id.isdigit():
        query = query.filter(room_id=selected_room_id)
    
    # จัดลำดับ
    notification_list = query.order_by('-created_at')

    # 3. Pagination (เหมือนเดิม)
    paginator = Paginator(notification_list, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 4. ✅ ดึงรายชื่อห้องที่นักเรียนคนนี้อยู่ (เพื่อไปทำ Dropdown)
    # ปรับ query ตามความสัมพันธ์ใน Model ของคุณ เช่น student_profile.rooms.all()
    # ตัวอย่าง:
    student_rooms = []
    if hasattr(request.user, 'student_profile'):
         # สมมติว่า Room มี field students ManyToMany
         student_rooms = Room.objects.filter(students=request.user.student_profile)

    context = {
        'notifications': page_obj,
        'student_rooms': student_rooms,        # ส่งรายชื่อห้องไป
        'selected_room_id': int(selected_room_id) if selected_room_id and selected_room_id.isdigit() else None
    }
    return render(request, 'notifications/notification_history.html', context)


# ✅ 2. ฟังก์ชันกดอ่านแจ้งเตือนรายตัว (Mark as Read & Redirect)
@login_required
def mark_as_read(request, noti_id):
    noti = get_object_or_404(Notification, id=noti_id, recipient=request.user)
    
    # ทำเครื่องหมายว่าอ่านแล้ว
    if not noti.is_read:
        noti.is_read = True
        noti.save()
    
    # Redirect ไปยังลิงก์ปลายทาง (ถ้ามี)
    if noti.link:
        return redirect(noti.link)
    
    # ถ้าไม่มีลิงก์ ให้กลับหน้าเดิมที่กดมา
    return redirect(request.META.get('HTTP_REFERER', '/'))