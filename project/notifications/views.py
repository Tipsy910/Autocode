from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Notification
from room.models import Room

# ✅ 1. ฟังก์ชันแสดงประวัติการแจ้งเตือนทั้งหมด (History)
@login_required
def notification_history_view(request):
    # 1. ดึงแจ้งเตือนพื้นฐาน (ใช้ได้ทั้ง นร. และ ครู)
    query = Notification.objects.filter(recipient=request.user)
    
    # 2. Logic การกรองห้องเรียน
    selected_room_id = request.GET.get('room')
    if selected_room_id and selected_room_id.isdigit():
        query = query.filter(room_id=selected_room_id)
    
    # จัดลำดับ
    notification_list = query.order_by('-created_at')

    # 3. Pagination
    paginator = Paginator(notification_list, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 4. ✅ (แก้ตรงนี้) ดึงรายชื่อห้องเพื่อทำ Dropdown (รองรับทั้ง Teacher และ Student)
    available_rooms = [] # เปลี่ยนชื่อตัวแปรให้สื่อความหมายกลางๆ

    # กรณีเป็นนักเรียน
    if hasattr(request.user, 'student_profile'):
         available_rooms = Room.objects.filter(students=request.user.student_profile)
    
    # ✅ กรณีเป็นอาจารย์ (เพิ่มส่วนนี้)
    elif hasattr(request.user, 'teacher_profile'):
         # ดึงห้องที่อาจารย์คนนี้เป็นเจ้าของ (ชื่อ Field 'teacher' ใน Room Model อาจต่างกัน เช็คด้วยนะครับ)
         available_rooms = Room.objects.filter(teachers=request.user.teacher_profile)

    context = {
        'notifications': page_obj,
        'student_rooms': available_rooms, # ส่งไปในชื่อเดิม หรือจะเปลี่ยนชื่อ key ก็ได้ (แต่ต้องไปแก้ html ด้วย)
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

@login_required
def mark_all_as_read(request):
    # 1. ดึงแจ้งเตือนของ User นี้ ที่ยังไม่ได้อ่าน (is_read=False)
    # 2. สั่ง update ทีเดียวทั้งหมด (ไม่ต้องวนลูป)
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    
    # 3. เด้งกลับไปหน้าเดิม
    return redirect(request.META.get('HTTP_REFERER', '/'))