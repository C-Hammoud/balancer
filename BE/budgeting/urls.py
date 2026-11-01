from django.urls import path
from . import views

app_name = "budgeting"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("alerts/", views.alert_list, name="alert_list"),
    path("alerts/<str:pk>/resolve/", views.alert_resolve, name="alert_resolve"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/expenses/", views.transaction_expenses_inquiry, name="transaction_expenses_inquiry"),
    path("transactions/add/", views.transaction_add, name="transaction_add"),
    path("transactions/upload/", views.transaction_upload, name="transaction_upload"),
    path("transactions/<str:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("transactions/consumption-to-transaction/", views.consumption_add_to_transaction, name="consumption_add_to_transaction"),
    path("transactions/consumption-add-all/", views.consumption_add_all_to_transactions, name="consumption_add_all_to_transactions"),
    path("budgets/", views.budget_list, name="budget_list"),
    path("budgets/add/", views.budget_add, name="budget_add"),
    path("budgets/<int:year>/<int:month>/<str:category_id>/", views.budget_edit, name="budget_edit"),
    path("savings/", views.savings_list, name="savings_list"),
    path("savings/<int:year>/<int:month>/", views.savings_edit, name="savings_edit"),
    path("commitments/", views.commitment_list, name="commitment_list"),
    path("commitments/add/", views.commitment_add, name="commitment_add"),
    path("commitments/<str:pk>/edit/", views.commitment_edit, name="commitment_edit"),
    path("financial-standing/", views.financial_standing_list, name="financial_standing_list"),
    path("financial-standing/add/", views.financial_standing_add, name="financial_standing_add"),
    path("config/categories/", views.config_categories, name="config_categories"),
    path("config/merchant-links/", views.config_merchant_links, name="config_merchant_links"),
    path("config/merchant-links/<str:pk>/edit/", views.config_merchant_links_edit, name="config_merchant_links_edit"),
    path("config/merchant-links/<str:pk>/delete/", views.config_merchant_links_delete, name="config_merchant_links_delete"),
    path("config/type-maps/", views.config_type_maps, name="config_type_maps"),
    path("config/type-maps/<str:pk>/clear/", views.config_type_maps_clear, name="config_type_maps_clear"),
    path("config/thresholds/", views.config_thresholds, name="config_thresholds"),
    path("config/thresholds/<str:pk>/delete/", views.config_thresholds_delete, name="config_thresholds_delete"),
]
