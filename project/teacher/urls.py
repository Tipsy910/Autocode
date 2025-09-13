from django.urls import path
from .views import *
app_name = 'teacher'
urlpatterns = [
    path('dashboard/', teacher_dashboard.as_view(), name='dashboard'),
    path('room/<int:pk>/delete/', RoomDeleteView.as_view(), name='room_delete'),
    path('room/<int:room_id>/create-assignment/',create_assignment, name='create_assignment'),
    path('assignment/<int:pk>/', teacher_assignment_detail, name='assignment_detail'),
    path('assignment/<int:pk>/delete/', AssignmentDeleteView.as_view(), name='assignment_delete'),
    path('assignment/<int:pk>/edit/', edit_assignment, name='assignment_edit'),
    path('room/<int:room_pk>/announce/', create_announcement, name='create_announcement'),
    path('announcement/<int:pk>/edit/', edit_announcement, name='announcement_edit'),
    path('announcement/<int:pk>/delete/', AnnouncementDeleteView.as_view(), name='announcement_delete'),
]