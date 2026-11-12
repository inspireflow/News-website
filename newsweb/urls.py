from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("article/<slug:slug>/", views.article, name="article"),
    path("category/<slug:slug>/", views.category_page, name="category"),
    path("about/", views.about, name="about"),
    path("search/", views.search, name="search"),
    path("accounts/login/", views.PublicLoginView.as_view(), name="account_login"),
    path("accounts/signup/", views.register, name="account_register"),
    path("accounts/logout/", views.public_logout, name="account_logout"),
    path("subscription/", views.subscription_plans, name="subscription_plans"),
    path(
        "subscription/request/",
        views.subscription_request,
        name="subscription_request_form",
    ),
    path(
        "subscription/request/<int:plan_id>/",
        views.subscription_request,
        name="subscription_request",
    ),
    path(
        "subscription/review/<int:pk>/<str:action>/<str:token>/",
        views.subscription_email_review,
        name="subscription_email_review",
    ),
    path(
        "subscription/cancel/<int:pk>/",
        views.subscription_cancel,
        name="subscription_cancel",
    ),
    path(
        "subscription/status/",
        views.subscription_status,
        name="subscription_status",
    ),
    path(
        "search-suggestions/",
        views.search_suggestions,
        name="search_suggestions",
    ),
]
