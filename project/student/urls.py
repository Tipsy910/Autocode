from django.urls import path
from student.views import student_dashboard, student_room_detail_view, student_assignment_detail_view, take_quiz
app_name = 'student'
urlpatterns = [
    path('dashboard/', student_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/', student_room_detail_view, name='room_detail'),
    path('assignment/<int:pk>/', student_assignment_detail_view, name='assignment_detail'),
    path('submission/<int:pk>/take-quiz/', take_quiz, name='take_quiz'),
]