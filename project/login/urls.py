from django.urls import path
from .views import login_view , logout_user
urlpatterns = [
    path("", login_view,name="login"),
    path("logout/",logout_user, name="logout"),
]