
from django.urls import path
from . import dashboard_views as views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.dashboard_login, name="login"),
    path("logout/", views.dashboard_logout, name="logout"),
    path("", views.overview, name="overview"),
    path("analytics/", views.analytics, name="analytics"),

    path("posts/", views.post_list, name="posts"),
    path("posts/add/", views.post_create, name="post_create"),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_edit"),
    path("posts/<int:pk>/delete/", views.post_delete, name="post_delete"),

    path("categories/", views.category_list, name="categories"),
    path("categories/add/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),

    path("sections/", views.section_list, name="sections"),
    path("sections/add/", views.section_create, name="section_create"),
    path("sections/<int:pk>/edit/", views.section_edit, name="section_edit"),
    path("sections/<int:pk>/delete/", views.section_delete, name="section_delete"),

    path("settings/", views.site_settings, name="settings"),
    path("subscriptions/", views.subscription_management, name="subscriptions"),
    path(
        "subscription-plans/",
        views.subscription_plan_management,
        name="subscription_plans",
    ),
    path(
        "subscription-plans/add/",
        views.subscription_plan_create,
        name="subscription_plan_create",
    ),
    path(
        "subscription-plans/<int:pk>/edit/",
        views.subscription_plan_edit,
        name="subscription_plan_edit",
    ),
    path(
        "subscriptions/<int:pk>/",
        views.subscription_detail,
        name="subscription_detail",
    ),
    path(
        "subscriptions/<int:pk>/schedule-expiry/",
        views.subscription_schedule_expiry,
        name="subscription_schedule_expiry",
    ),
    path(
        "subscriptions/<int:pk>/<str:action>/",
        views.subscription_action,
        name="subscription_action",
    ),
    path(
        "subscription-emails/<int:delivery_id>/retry/",
        views.subscription_email_retry,
        name="subscription_email_retry",
    ),
]
