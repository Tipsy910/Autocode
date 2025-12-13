from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('read/<int:noti_id>/', views.mark_as_read, name='mark_as_read'),
]