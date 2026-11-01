from django.urls import path
from . import views

urlpatterns = [
    path("healthz/", views.health_check, name="health_check"),
    path("settings/", views.user_settings, name="user_settings"),
    path("register/", views.register, name="register"),
    path("add/", views.add_expense, name="add_expense"),
    path("list/", views.monthly_list, name="monthly_list"),
    path("", views.dashboard, name="dashboard"),
    path("edit/<uuid:pk>/", views.edit_expense, name="edit_expense"),
    path("delete/<uuid:pk>/", views.delete_expense, name="delete_expense"),
    path("firebase-token-login/", views.firebase_token_login, name="firebase_token_login"),
    path("dashboard/pdf/", views.download_dashboard_pdf, name="dashboard_pdf"),
]