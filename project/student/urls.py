from django.urls import path
from student.views import *
app_name = 'student'
urlpatterns = [
    path('dashboard/', student_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/', student_room_detail_view, name='room_detail'),
    path('assignment/<int:pk>/', student_assignment_detail_view, name='assignment_detail'),
]