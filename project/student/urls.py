from django.urls import path
from student.views import *
app_name = 'student'
urlpatterns = [
    path('dashboard/', student_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/', student_room_detail_view, name='room_detail'),
    path('assignment/<int:pk>/', student_assignment_detail_view, name='assignment_detail'),
    path('submission/<int:pk>/generate-quiz/', generate_quiz_view, name='generate_quiz'),
    path('submission/<int:pk>/take-quiz/', take_quiz_view, name='take_quiz'),
]