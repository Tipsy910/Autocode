from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('profile/', views.profile_view, name='profile'),
    path('password-change/', views.MyPasswordChangeView.as_view(), name='password_change'),
    path('password-change/done/', views.MyPasswordChangeDoneView.as_view(), name='password_change_done'),
    path('password-reset/', views.MyPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.MyPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.MyPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset-complete/', views.MyPasswordResetCompleteView.as_view(), name='password_reset_complete'),
]
