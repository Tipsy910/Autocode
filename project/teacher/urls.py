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
    path('announcement/<int:pk>/edit/', edit_announcement, name='announcement_edit'),
    path('announcement/<int:pk>/delete/', AnnouncementDeleteView.as_view(), name='announcement_delete'),
    path('assignment/<int:pk>/submissions/', review_submission_view, name= 'review_submission'),
    path('submission/<int:pk>/quiz-result/', teacher_quiz_result_view, name='quiz_result'),
    path('assignment/<int:pk>/reported/', report_list_view, name='report_list'),
]