from django.urls import path
from . import views

app_name = 'notifications' # 👈 สำคัญตรงนี้

urlpatterns = [
    path('history/', views.notification_history_view, name='notification_history'), # 👈 ชื่อนี้ใช้ใน redirect
    path('read/<int:noti_id>/', views.mark_as_read, name='mark_as_read'),
]