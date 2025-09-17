from django.urls import path
from .views import student_dashboard, student_room_detail_view, student_assignment_detail_view
app_name = 'student'
urlpatterns = [
    path('dashboard/', student_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/', student_room_detail_view, name='room_detail'),
    path('assignment/<int:assignment_id>/', student_assignment_detail_view, name='student_assignment_detail'),
]