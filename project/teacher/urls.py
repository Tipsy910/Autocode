from django.urls import path
from .views import teacher_dashboard,RoomDeleteView
app_name = 'teacher'
urlpatterns = [
    path('dashboard/', teacher_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/delete/', RoomDeleteView.as_view(), name='room_delete')
]