from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="account_login")
def dashboard(request):
    return render(request, "dashboard/dashboard.html", {"user": request.user})  