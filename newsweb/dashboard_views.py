from datetime import timedelta
import calendar

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncDate, TruncMonth
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Post,
    Category,
    Section,
    SiteSettings,
    PageView,
    Subscription,
    SubscriptionEmail,
    SubscriptionPlan,
)
from .forms import (
    PostForm,
    CategoryForm,
    SectionForm,
    SiteSettingsForm,
    SubscriptionExpiryForm,
    SubscriptionReasonForm,
    SubscriptionPlanForm,
)
from .subscription_services import (
    cancel_subscription,
    deliver_subscription_email,
    expire_due_subscriptions,
    review_subscription,
    retry_subscription_email,
    schedule_subscription_expiry,
)


def staff_check(user):
    return user.is_authenticated and user.is_staff


staff_required = user_passes_test(
    staff_check,
    login_url="/dashboard/login/",
)


def dashboard_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard:overview")

    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None and user.is_staff:
            login(request, user)
            return redirect("dashboard:overview")

        error = "Invalid username or password."

    return render(request, "dashboard/login.html", {
        "error": error,
    })


@staff_required
@require_POST
def dashboard_logout(request):
    logout(request)
    return redirect("dashboard:login")


@staff_required
def overview(request):
    today = timezone.localdate()
    start_day = today - timedelta(days=6)
    start_time = timezone.make_aware(
        timezone.datetime.combine(
            start_day,
            timezone.datetime.min.time(),
        )
    )

    daily_data = {
        row["day"]: row["total"]
        for row in PageView.objects.filter(
            viewed_at__gte=start_time,
        ).annotate(
            day=TruncDate("viewed_at"),
        ).values("day").annotate(
            total=Count("id"),
        )
    }

    chart = []

    for i in range(7):
        day = start_day + timedelta(days=i)
        chart.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%d %b"),
            "views": daily_data.get(day, 0),
        })

    max_views = max((item["views"] for item in chart), default=0)

    for item in chart:
        item["percent"] = (
            round(item["views"] / max_views * 100)
            if max_views else 0
        )

    popular_posts = Post.objects.filter(
        status="published",
    ).annotate(
        views=Count("page_views"),
    ).order_by("-views", "-created_at")[:5]

    context = {
        "total_posts": Post.objects.count(),
        "published_posts": Post.objects.filter(status="published").count(),
        "draft_posts": Post.objects.filter(status="draft").count(),
        "total_categories": Category.objects.count(),
        "total_sections": Section.objects.count(),
        "today_views": PageView.objects.filter(
            viewed_at__date=today,
        ).count(),
        "week_views": PageView.objects.filter(
            viewed_at__date__gte=start_day,
            viewed_at__date__lte=today,
        ).count(),
        "chart": chart,
        "popular_posts": popular_posts,
        "recent_posts": Post.objects.select_related(
            "category",
        ).order_by("-created_at")[:6],
        "chart_data": _dashboard_chart_data(today),
    }

    return render(request, "dashboard/overview.html", context)


def _dashboard_chart_data(today):
    """Return analytics assembled from existing posts and page-view records."""
    days = [today - timedelta(days=offset) for offset in range(83, -1, -1)]
    activity_rows = Post.objects.filter(
        created_at__date__gte=days[0],
        created_at__date__lte=today,
    ).annotate(
        day=TruncDate("created_at"),
    ).values("day").annotate(
        total=Count("id"),
    )
    activity = {row["day"]: row["total"] for row in activity_rows}

    daily_rows = PageView.objects.filter(
        viewed_at__date__gte=today - timedelta(days=29),
        viewed_at__date__lte=today,
    ).annotate(
        day=TruncDate("viewed_at"),
    ).values("day").annotate(
        total=Count("id"),
    )
    daily_views = {row["day"]: row["total"] for row in daily_rows}
    recent_days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]

    current_month = today.replace(day=1)
    month_starts = [current_month]
    for _ in range(11):
        previous_month = month_starts[-1] - timedelta(days=1)
        month_starts.append(previous_month.replace(day=1))
    month_starts.reverse()

    monthly_view_rows = PageView.objects.filter(
        viewed_at__date__gte=month_starts[0],
        viewed_at__date__lte=today,
    ).annotate(
        month=TruncMonth("viewed_at"),
    ).values("month").annotate(
        total=Count("id"),
    )
    monthly_views = {
        row["month"].date().replace(day=1): row["total"]
        for row in monthly_view_rows
    }
    monthly_post_rows = Post.objects.filter(
        created_at__date__gte=month_starts[0],
        created_at__date__lte=today,
    ).annotate(
        month=TruncMonth("created_at"),
    ).values("month").annotate(
        total=Count("id"),
    )
    monthly_posts = {
        row["month"].date().replace(day=1): row["total"]
        for row in monthly_post_rows
    }
    published_month_rows = Post.objects.filter(
        status=Post.PUBLISHED,
        created_at__date__gte=month_starts[0],
        created_at__date__lte=today,
    ).annotate(
        month=TruncMonth("created_at"),
    ).values("month").annotate(
        total=Count("id"),
    )
    monthly_published = {
        row["month"].date().replace(day=1): row["total"]
        for row in published_month_rows
    }

    categories = list(
        Category.objects.annotate(
            articles=Count("posts", distinct=True),
            views=Count("posts__page_views", distinct=True),
        ).order_by("-articles", "name")[:8]
    )
    authors = list(
        Post.objects.values("author").annotate(
            articles=Count("id", distinct=True),
            views=Count("page_views"),
        ).order_by("-articles", "author")[:8]
    )
    popular_posts = list(
        Post.objects.filter(status=Post.PUBLISHED).annotate(
            views=Count("page_views"),
        ).order_by("-views", "-created_at")[:5]
    )

    month_views = sum(
        row["total"] for row in monthly_view_rows
        if row["month"].date().replace(day=1) == current_month
    )
    month_articles = Post.objects.filter(
        status=Post.PUBLISHED,
        created_at__date__gte=current_month,
        created_at__date__lte=today,
    ).count()
    view_goal = 1000
    article_goal = 20
    view_progress = min(round(month_views / view_goal * 100), 100)
    article_progress = min(round(month_articles / article_goal * 100), 100)

    return {
        "views": {
            "7d": {
                "labels": [day.strftime("%a") for day in recent_days[-7:]],
                "values": [daily_views.get(day, 0) for day in recent_days[-7:]],
            },
            "30d": {
                "labels": [day.strftime("%d %b") for day in recent_days],
                "values": [daily_views.get(day, 0) for day in recent_days],
            },
            "12m": {
                "labels": [calendar.month_abbr[month.month] for month in month_starts],
                "values": [monthly_views.get(month, 0) for month in month_starts],
            },
        },
        "monthly_articles": [monthly_posts.get(month, 0) for month in month_starts],
        "monthly_published": [monthly_published.get(month, 0) for month in month_starts],
        "monthly_drafts": [
            max(monthly_posts.get(month, 0) - monthly_published.get(month, 0), 0)
            for month in month_starts
        ],
        "categories": {
            "labels": [category.name for category in categories],
            "articles": [category.articles for category in categories],
            "views": [category.views for category in categories],
        },
        "authors": {
            "labels": [author["author"] for author in authors],
            "articles": [author["articles"] for author in authors],
            "views": [author["views"] for author in authors],
        },
        "popular": {
            "labels": [post.title for post in popular_posts],
            "values": [post.views for post in popular_posts],
        },
        "activity": [
            {"date": day.isoformat(), "count": activity.get(day, 0)}
            for day in days
        ],
        "goals": {
            "articles": {
                "value": month_articles,
                "target": article_goal,
                "progress": article_progress,
            },
            "views": {
                "value": month_views,
                "target": view_goal,
                "progress": view_progress,
            },
        },
        "performance": round((article_progress + view_progress) / 2),
        "traffic_sources_sample": {
            "labels": ["Direct", "Search", "Social", "Referral"],
            "values": [42, 31, 18, 9],
        },
    }


@staff_required
def analytics(request):
    return render(request, "dashboard/analytics.html", {
        "chart_data": _dashboard_chart_data(timezone.localdate()),
    })


@staff_required
def post_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    posts = Post.objects.select_related(
        "category", "section",
    )

    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
        )

    if status in dict(Post.STATUS_CHOICES):
        posts = posts.filter(status=status)

    page = Paginator(posts, 20).get_page(request.GET.get("page"))
    return render(request, "dashboard/post.html", {
        "posts": page.object_list,
        "page_obj": page,
        "query": query,
        "status": status,
    })


@staff_required
def post_create(request):
    is_submitted = request.method == "POST"
    form = PostForm(
        data=request.POST if is_submitted else None,
        files=request.FILES if is_submitted else None,
    )

    if is_submitted:
        if form.is_valid():
            form.save()
            messages.success(request, "News post created successfully.")
            return redirect("dashboard:posts")

        messages.error(request, "Please correct the errors below.")

    return render(request, "dashboard/posts_form.html", {
        "form": form,
        "heading": "Add News",
    })


@staff_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    is_submitted = request.method == "POST"

    form = PostForm(
        data=request.POST if is_submitted else None,
        files=request.FILES if is_submitted else None,
        instance=post,
    )

    if is_submitted:
        if form.is_valid():
            form.save()
            messages.success(request, "News post updated successfully.")
            return redirect("dashboard:posts")

        messages.error(request, "Please correct the errors below.")

    return render(request, "dashboard/posts_form.html", {
        "form": form,
        "heading": "Edit News",
        "post": post,
    })


@staff_required
def post_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)

    if request.method == "POST":
        post.delete()
        messages.success(request, "News post deleted.")
        return redirect("dashboard:posts")

    return render(request, "dashboard/confirm_delete.html", {
        "object": post,
        "cancel_url": "dashboard:posts",
    })


@staff_required
def category_list(request):
    return render(request, "dashboard/categories.html", {
        "categories": Category.objects.all(),
        "form": CategoryForm(),
    })


@staff_required
def category_create(request):
    form = CategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category created.")
        return redirect("dashboard:categories")

    return render(request, "dashboard/categories.html", {
        "categories": Category.objects.all(),
        "form": form,
    })


@staff_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category updated.")
        return redirect("dashboard:categories")

    return render(request, "dashboard/category_form.html", {
        "form": form,
        "heading": "Edit Category",
    })


@staff_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        try:
            category.delete()
            messages.success(request, "Category deleted.")
        except ProtectedError:
            messages.error(
                request,
                "This category has news posts. Reassign or delete those posts first.",
            )
        return redirect("dashboard:categories")

    return render(request, "dashboard/confirm_delete.html", {
        "object": category,
        "cancel_url": "dashboard:categories",
    })


@staff_required
def section_list(request):
    return render(request, "dashboard/sections.html", {
        "sections": Section.objects.all(),
        "form": SectionForm(),
    })


@staff_required
def section_create(request):
    form = SectionForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Section created.")
        return redirect("dashboard:sections")

    return render(request, "dashboard/sections.html", {
        "sections": Section.objects.all(),
        "form": form,
    })


@staff_required
def section_edit(request, pk):
    section = get_object_or_404(Section, pk=pk)
    form = SectionForm(request.POST or None, instance=section)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Section updated.")
        return redirect("dashboard:sections")

    return render(request, "dashboard/section_form.html", {
        "form": form,
        "heading": "Edit Section",
    })


@staff_required
def section_delete(request, pk):
    section = get_object_or_404(Section, pk=pk)

    if request.method == "POST":
        section.delete()
        messages.success(request, "Section deleted.")
        return redirect("dashboard:sections")

    return render(request, "dashboard/confirm_delete.html", {
        "object": section,
        "cancel_url": "dashboard:sections",
    })


@staff_required
def site_settings(request):
    settings_obj, _ = SiteSettings.objects.get_or_create(pk=1)

    form = SiteSettingsForm(
        request.POST or None,
        request.FILES or None,
        instance=settings_obj,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Website settings saved.")
        return redirect("dashboard:settings")

    return render(request, "dashboard/settings.html", {
        "form": form,
    })


@staff_required
def subscription_management(request):
    expire_due_subscriptions()
    subscriptions = Subscription.objects.select_related(
        "user",
        "plan",
        "approved_by",
        "rejected_by",
        "cancelled_by",
    )
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    plan_id = request.GET.get("plan", "")

    if query:
        name_matches = Q()
        for term in query.split():
            name_matches &= (
                Q(full_name__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
            )
        subscriptions = subscriptions.filter(
            Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(email__icontains=query)
            | name_matches
        )
    if status in dict(Subscription.STATUS_CHOICES):
        subscriptions = subscriptions.filter(status=status)
    if plan_id.isdigit():
        subscriptions = subscriptions.filter(plan_id=int(plan_id))

    page = Paginator(subscriptions, 25).get_page(request.GET.get("page"))
    counts = Subscription.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Subscription.PENDING)),
        active=Count("id", filter=Q(status=Subscription.ACTIVE)),
        rejected=Count("id", filter=Q(status=Subscription.REJECTED)),
        cancelled=Count("id", filter=Q(status=Subscription.CANCELLED)),
        expired=Count("id", filter=Q(status=Subscription.EXPIRED)),
    )
    return render(request, "dashboard/subscriptions.html", {
        "subscriptions": page.object_list,
        "page_obj": page,
        "counts": counts,
        "plans": SubscriptionPlan.objects.all(),
        "query": query,
        "status": status,
        "selected_plan": plan_id,
        "status_choices": Subscription.STATUS_CHOICES,
    })


@staff_required
def subscription_plan_management(request):
    return render(request, "dashboard/subscription_plans.html", {
        "plans": SubscriptionPlan.objects.all(),
    })


@staff_required
def subscription_plan_create(request):
    form = SubscriptionPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Subscription plan created.")
        return redirect("dashboard:subscription_plans")
    return render(request, "dashboard/subscription_plan_form.html", {
        "form": form,
        "heading": "Add subscription plan",
    })


@staff_required
def subscription_plan_edit(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    form = SubscriptionPlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Subscription plan updated.")
        return redirect("dashboard:subscription_plans")
    return render(request, "dashboard/subscription_plan_form.html", {
        "form": form,
        "heading": "Edit subscription plan",
        "plan": plan,
    })


@staff_required
def subscription_detail(request, pk):
    expire_due_subscriptions()
    subscription = get_object_or_404(
        Subscription.objects.select_related(
            "user",
            "plan",
            "approved_by",
            "rejected_by",
            "cancelled_by",
        ).prefetch_related("events__actor", "email_deliveries"),
        pk=pk,
    )
    return render(request, "dashboard/subscription_detail.html", {
        "subscription": subscription,
        "reason_form": SubscriptionReasonForm(),
        "expiry_form": SubscriptionExpiryForm(initial={
            "expires_on": (
                timezone.localtime(subscription.expires_at).date()
                if subscription.expires_at else None
            ),
        }),
    })


@staff_required
@require_POST
def subscription_action(request, pk, action):
    subscription = get_object_or_404(Subscription, pk=pk)
    if action not in {"approve", "reject", "cancel"}:
        raise Http404

    form = SubscriptionReasonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid reason.")
        return redirect("dashboard:subscription_detail", pk=pk)

    try:
        if action == "cancel":
            subscription = cancel_subscription(
                pk,
                request.user,
                reason=form.cleaned_data["reason"],
            )
            email_event = "user_cancelled"
        else:
            subscription = review_subscription(
                pk,
                request.user,
                approve=(action == "approve"),
                reason=form.cleaned_data["reason"],
            )
            email_event = (
                "user_approved" if action == "approve" else "user_rejected"
            )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("dashboard:subscription_detail", pk=pk)

    action_label = {
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
    }[action]
    if deliver_subscription_email(
        subscription.pk,
        email_event,
        request=request,
    ):
        messages.success(request, f"Subscription {action_label} successfully.")
    else:
        messages.warning(
            request,
            f"Subscription {action_label}, but the user email could not be sent. "
            "A retry is available below.",
        )
    return redirect("dashboard:subscription_detail", pk=pk)


@staff_required
@require_POST
def subscription_schedule_expiry(request, pk):
    form = SubscriptionExpiryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please choose a valid expiry date.")
        return redirect("dashboard:subscription_detail", pk=pk)
    try:
        schedule_subscription_expiry(
            pk,
            form.cleaned_data["expires_on"],
            request.user,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Subscription expiry date updated.")
    return redirect("dashboard:subscription_detail", pk=pk)


@staff_required
@require_POST
def subscription_email_retry(request, delivery_id):
    delivery = get_object_or_404(SubscriptionEmail, pk=delivery_id)
    try:
        sent = retry_subscription_email(delivery.pk, request=request)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(
            "dashboard:subscription_detail",
            pk=delivery.subscription_id,
        )

    if sent:
        messages.success(request, "Email retry succeeded.")
    else:
        messages.error(
            request,
            "Email retry failed. Check server email configuration and try again.",
        )
    return redirect(
        "dashboard:subscription_detail",
        pk=delivery.subscription_id,
    )
