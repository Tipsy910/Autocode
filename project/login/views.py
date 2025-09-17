from django.shortcuts import render

# Create your views here.
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.shortcuts import render, redirect

User = get_user_model()

def login_view(request):


    if request.method == 'POST':
        email = request.POST.get('email').strip().lower()
        password = request.POST.get('password')

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome {user.email}")
            if user.role.lower() == 'admin':
                return redirect('admin_dashboard')
            elif user.role.lower() == 'student':
                return redirect('student:dashboard')
            else:
                return redirect('teacher:dashboard')


    return render(request, 'login/login.html')


def logout_user(request):
    logout(request)
    messages.success(request, 'คุณได้ออกจากระบบเรียบร้อยแล้ว')
    return redirect('login')
