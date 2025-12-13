from django.shortcuts import get_object_or_404, redirect 
from django.contrib.auth.decorators import login_required
from .models import Notification

@login_required
def mark_as_read(request, noti_id):
    noti = get_object_or_404(Notification, id=noti_id, recipient=request.user)
    
    # 1. ทำเครื่องหมายว่าอ่านแล้ว
    noti.is_read = True
    noti.save()
    
    # 2. Redirect ไปยังลิงก์ปลายทาง (ถ้ามี)
    if noti.link:
        return redirect(noti.link)
    
    # ถ้าไม่มีลิงก์ ให้กลับหน้าเดิม
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def mark_as_read(request, noti_id):
    noti = get_object_or_404(Notification, id=noti_id, recipient=request.user)
    
    # 1. ทำเครื่องหมายว่าอ่านแล้ว
    noti.is_read = True
    noti.save()
    
    # 2. Redirect ไปยังลิงก์ปลายทาง (ถ้ามี)
    if noti.link:
        return redirect(noti.link)
    
    # ถ้าไม่มีลิงก์ ให้กลับหน้าเดิม
    return redirect(request.META.get('HTTP_REFERER', '/'))