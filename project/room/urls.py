# room/urls.py
from django.urls import path
# เราจะ import view จากทั้งแอป teacher และ student
from teacher.views import teacher_room_detail_view
from student.views import student_room_detail_view

app_name = 'room'

urlpatterns = [
    # URL สำหรับอาจารย์: /room/5/
    path('<int:pk>/', teacher_room_detail_view, name='teacher_detail'),
    
    # URL สำหรับนักเรียน: /room/5/student/
    path('<int:pk>/student/', student_room_detail_view, name='student_detail'),
]