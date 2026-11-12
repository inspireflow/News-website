
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    RegistrationForm,
    SubscriptionRequestForm,
)
from .models import (
    Post,
    Category,
    Section,
    SiteSettings,
    Subscription,
    SubscriptionPlan,
)
from .subscription_services import (
    create_subscription_request,
    cancel_subscription,
    deliver_subscription_email,
    email_review_state,
    expire_due_subscriptions,
    review_subscription_from_email,
)


def common_context():
    return {
        "categories": Category.objects.filter(is_active=True),
        "site_settings": SiteSettings.objects.first(),
    }


def published_search_results(query):
    return Post.objects.filter(
        status="published",
        category__is_active=True,
    ).filter(
        Q(title__icontains=query)
        | Q(summary__icontains=query)
        | Q(category__name__icontains=query)
    ).select_related("category").defer("content")


def home(request):
    published_posts = Post.objects.filter(
        status="published",
        category__is_active=True,
    ).select_related("category", "section").defer("content")

    featured = published_posts.first()
    latest_page = Paginator(
        published_posts.exclude(pk=featured.pk) if featured else published_posts,
        12,
    ).get_page(request.GET.get("page"))

    sections = Section.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "posts",
            queryset=published_posts,
            to_attr="visible_posts",
        )
    )

    context = common_context()
    context.update({
        "featured": featured,
        "posts": latest_page.object_list,
        "page_obj": latest_page,
        "sections": sections,
    })

    return render(request, "home.html", context)


def article(request, slug):
    post = get_object_or_404(
        Post.objects.select_related("category", "section"),
        slug=slug,
        status="published",
        category__is_active=True,
    )

    latest = Post.objects.filter(
        status="published",
        category__is_active=True,
        category=post.category,
    ).exclude(pk=post.pk).defer("content")[:4]

    has_access = False
    latest_subscription = None
    if request.user.is_authenticated:
        expire_due_subscriptions(user_id=request.user.pk)
        now = timezone.now()
        has_access = Subscription.objects.filter(
            user=request.user,
            status=Subscription.ACTIVE,
            starts_at__lte=now,
            expires_at__gt=now,
        ).exists()
        latest_subscription = Subscription.objects.filter(
            user=request.user,
        ).select_related("plan").first()

    if not has_access:
        words = post.content.split()
        preview_limit = max(1, settings.PREMIUM_PREVIEW_WORDS)
        if len(words) <= preview_limit and len(words) > 1:
            preview_limit = max(1, len(words) - 1)
        post.content = " ".join(words[:preview_limit])
        if len(words) > preview_limit:
            post.content += "…"

    context = common_context()
    context.update({
        "post": post,
        "latest": latest,
        "has_premium_access": has_access,
        "latest_subscription": latest_subscription,
    })

    return render(request, "article.html", context)


def category_page(request, slug):
    category = get_object_or_404(
        Category,
        slug=slug,
        is_active=True,
    )

    posts = Post.objects.filter(
        category=category,
        status="published",
    ).defer("content")
    page = Paginator(posts, 12).get_page(request.GET.get("page"))

    context = common_context()
    context.update({
        "category": category,
        "posts": page.object_list,
        "page_obj": page,
    })

    return render(request, "category.html", context)


def about(request):
    return render(
        request,
        "about.html",
        common_context(),
    )


def search_suggestions(request):
    query = request.GET.get("q", "").strip()[:100]

    results = [
        {
            "title": post.title,
            "summary": post.summary,
            "category": post.category.name,
            "url": f"/article/{post.slug}/",
        }
        for post in published_search_results(query)[:8]
    ] if len(query) >= 2 else []

    return JsonResponse({
        "query": query,
        "results": results,
    })


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    posts = published_search_results(query) if query else Post.objects.none()

    page = Paginator(posts, 12).get_page(request.GET.get("page"))
    context = common_context()
    context.update({
        "query": query,
        "page_obj": page,
        "posts": page.object_list,
    })
    return render(request, "search.html", context)


class PublicLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = AuthenticationForm

    def get_success_url(self):
        return self.get_redirect_url() or reverse("subscription_status")


def register(request):
    if request.user.is_authenticated:
        return redirect("subscription_status")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        destination = request.POST.get("next", "")
        if url_has_allowed_host_and_scheme(
            destination,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(destination)
        return redirect("subscription_status")

    return render(request, "accounts/register.html", {
        "form": form,
        "next": request.GET.get("next", ""),
    })


@require_POST
def public_logout(request):
    logout(request)
    return redirect("home")


def subscription_plans(request):
    if request.user.is_authenticated:
        expire_due_subscriptions(user_id=request.user.pk)
    plans = SubscriptionPlan.objects.filter(is_active=True)
    plan_id = request.GET.get("plan", "")
    selected_plan = (
        plans.filter(pk=plan_id).first()
        if plan_id.isdigit()
        else None
    )
    return render(request, "subscriptions/plans.html", {
        "plans": plans,
        "form": SubscriptionRequestForm(
            plans=plans,
            user=request.user if request.user.is_authenticated else None,
            selected_plan=selected_plan,
        ),
        "site_settings": SiteSettings.objects.first(),
        "current_subscription": (
            Subscription.objects.filter(
                user=request.user,
                status__in=[Subscription.PENDING, Subscription.ACTIVE],
            ).select_related("plan").first()
            if request.user.is_authenticated else None
        ),
    })


@login_required(login_url="account_login")
@require_POST
def subscription_request(request, plan_id=None):
    plans = SubscriptionPlan.objects.filter(is_active=True)
    form_data = request.POST.copy()
    if plan_id is not None:
        form_data.setdefault("plan", str(plan_id))
    form = SubscriptionRequestForm(
        form_data,
        plans=plans,
        user=request.user,
    )
    if not form.is_valid():
        messages.error(request, "Please check the subscription request form.")
        return render(request, "subscriptions/plans.html", {
            "plans": plans,
            "form": form,
            "site_settings": SiteSettings.objects.first(),
            "current_subscription": Subscription.objects.filter(
                user=request.user,
                status__in=[Subscription.PENDING, Subscription.ACTIVE],
            ).select_related("plan").first(),
        })

    try:
        subscription, created = create_subscription_request(
            request.user,
            form.cleaned_data["plan"],
            payment_reference=form.cleaned_data["payment_reference"],
            full_name=form.cleaned_data["full_name"],
            email=form.cleaned_data["email"],
            payment_mode=form.cleaned_data["payment_mode"],
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("subscription_status")

    if created:
        sent = deliver_subscription_email(
            subscription.pk,
            "admin_requested",
            request=request,
        )
        if sent:
            messages.success(
                request,
                "Your request is pending administrator approval.",
            )
        else:
            messages.warning(
                request,
                "Your request was saved, but the administrator notification "
                "could not be sent. The dashboard will show the failed email.",
            )
    else:
        messages.info(
            request,
            "You already have a pending request. It is shown below.",
        )
    return redirect("subscription_status")


@require_http_methods(["GET", "POST"])
def subscription_email_review(request, pk, action, token):
    if action not in {"approve", "reject"}:
        raise Http404
    subscription = get_object_or_404(
        Subscription.objects.select_related("plan", "user"),
        pk=pk,
    )
    review_state = email_review_state(subscription, token)
    result_message = ""
    if request.method == "POST":
        if review_state != "pending":
            result_message = {
                "processed": "This request has already been processed.",
                "expired": "This review link has expired.",
                "invalid": "This review link is invalid.",
            }[review_state]
        else:
            try:
                subscription = review_subscription_from_email(
                    pk,
                    token,
                    approve=(action == "approve"),
                )
            except ValidationError as error:
                subscription.refresh_from_db()
                review_state = email_review_state(subscription, token)
                result_message = " ".join(error.messages)
            else:
                deliver_subscription_email(
                    subscription.pk,
                    "user_approved" if action == "approve" else "user_rejected",
                    request=request,
                )
                result_message = (
                    "Subscription approved successfully."
                    if action == "approve"
                    else "Subscription rejected successfully."
                )
                review_state = "complete"

    return render(request, "subscriptions/email_review.html", {
        "subscription": subscription,
        "action": action,
        "review_state": review_state,
        "result_message": result_message,
        "site_settings": SiteSettings.objects.first(),
    })


@login_required(login_url="account_login")
def subscription_status(request):
    expire_due_subscriptions(user_id=request.user.pk)
    subscriptions = Subscription.objects.filter(
        user=request.user,
    ).select_related("plan").prefetch_related("events")
    return render(request, "subscriptions/status.html", {
        "subscriptions": subscriptions,
        "current_subscription": subscriptions.filter(
            status__in=[Subscription.PENDING, Subscription.ACTIVE],
        ).first(),
        "site_settings": SiteSettings.objects.first(),
    })


@login_required(login_url="account_login")
@require_POST
def subscription_cancel(request, pk):
    subscription = get_object_or_404(
        Subscription,
        pk=pk,
        user=request.user,
    )
    try:
        cancel_subscription(
            subscription.pk,
            request.user,
            reason="Cancelled by subscriber.",
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Your subscription has been cancelled.")
    return redirect("subscription_status")
