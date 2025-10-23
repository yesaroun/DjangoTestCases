from django.urls import path
from . import views

app_name = "test_manager"

urlpatterns = [
    path("refund/process/", views.process_refund, name="process_refund"),
    path(
        "test/scenario/<int:user_id>/",
        views.test_scenario_info,
        name="test_scenario_info",
    ),
]
