from django.urls import path
from .views import student_dashboard, student_room_detail_view, student_assignment_detail_view
urlpatterns = [
    path('', student_dashboard.as_view(), name='student_dashboard'),
    path('room/<int:room_id>/', student_room_detail_view, name='student_room_detail'),
    path('assignment/<int:assignment_id>/', student_assignment_detail_view, name='student_assignment_detail'),
]