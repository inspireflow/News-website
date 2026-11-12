
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify


def unique_slug(instance, value, model):
    base = slugify(value) or "news"
    slug = base
    number = 2

    while model.objects.filter(slug=slug).exclude(
        pk=instance.pk
    ).exists():
        slug = f"{base}-{number}"
        number += 1

    return slug


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name, Category)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Section(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title, Section)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Post(models.Model):
    DRAFT = "draft"
    PUBLISHED = "published"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (PUBLISHED, "Published"),
    ]

    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=280, unique=True, blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="posts",
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )

    summary = models.CharField(max_length=400)
    content = models.TextField()
    image = models.ImageField(
        upload_to="news/",
        blank=True,
        null=True,
    )
    is_premium = models.BooleanField(
        default=False,
        help_text="Require an active subscription to read the full article.",
    )

    author = models.CharField(max_length=100, default="News Desk")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title, Post)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=120, default="NewsPortal")
    tagline = models.CharField(
        max_length=250,
        default="Your daily source for the latest news",
        blank=True,
    )
    logo = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
    )
    footer_text = models.CharField(
        max_length=250,
        default="All rights reserved.",
    )
    contact_email = models.EmailField(blank=True)
    subscription_payment_instructions = models.TextField(
        blank=True,
        help_text="Instructions shown to users after they request a subscription.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.site_name


class PageView(models.Model):
    path = models.CharField(max_length=500, db_index=True)
    post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-viewed_at"]

    def __str__(self):
        return f"{self.path} - {self.viewed_at}"


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3)
    duration_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "price", "id"]

    def __str__(self):
        return self.name


class Subscription(models.Model):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CASH_ON_DELIVERY = "cash_on_delivery"
    PAYMENT_MODE_CHOICES = [
        (CASH_ON_DELIVERY, "Cash on Delivery"),
    ]

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACTIVE, "Active"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
        (EXPIRED, "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    plan_name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True)
    duration_days = models.PositiveIntegerField()
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    payment_mode = models.CharField(
        max_length=30,
        default=CASH_ON_DELIVERY,
        choices=PAYMENT_MODE_CHOICES,
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=PENDING,
        db_index=True,
    )
    payment_reference = models.CharField(max_length=120, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_subscriptions",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_subscriptions",
    )
    rejection_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_subscriptions",
    )
    cancellation_reason = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    approval_token_hash = models.CharField(max_length=64, blank=True)
    approval_token_expires_at = models.DateTimeField(null=True, blank=True)
    approval_token_used_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "plan"],
                condition=Q(status="pending"),
                name="newsweb_one_pending_plan_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active"),
                name="newsweb_one_active_subscription_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["user", "requested_at"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.plan_name} ({self.get_status_display()})"

    @property
    def days_remaining_text(self):
        if self.status == self.EXPIRED:
            return "Expired"
        if self.status != self.ACTIVE:
            return "—"
        if self.expires_at is None or self.expires_at <= timezone.now():
            return "Expired"
        days = (
            timezone.localtime(self.expires_at).date()
            - timezone.localdate()
        ).days
        return f"{days} day{'s' if days != 1 else ''} left"


class SubscriptionEvent(models.Model):
    EVENT_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
        ("expiry_scheduled", "Expiry scheduled"),
    ]

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    from_status = models.CharField(max_length=10, blank=True)
    to_status = models.CharField(max_length=10, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_events",
    )
    reason = models.TextField(blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["occurred_at", "id"]

    def __str__(self):
        return f"{self.subscription_id}: {self.event}"


class SubscriptionEmail(models.Model):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"

    DELIVERY_STATUS_CHOICES = [
        (PENDING, "Pending"),
        (SENDING, "Sending"),
        (SENT, "Sent"),
        (FAILED, "Failed"),
    ]

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="email_deliveries",
    )
    event = models.CharField(max_length=30)
    recipient = models.EmailField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=DELIVERY_STATUS_CHOICES,
        default=PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "event"],
                name="newsweb_unique_subscription_email_event",
            ),
        ]

    def __str__(self):
        return f"{self.event} for subscription {self.subscription_id}"
