
from django.contrib import admin
from .models import (
    Category,
    PageView,
    Post,
    Section,
    SiteSettings,
    Subscription,
    SubscriptionEmail,
    SubscriptionEvent,
    SubscriptionPlan,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("title",)
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "section",
        "author",
        "status",
        "is_premium",
        "created_at",
    )

    list_filter = ("status", "is_premium", "category", "section", "created_at")
    search_fields = ("title", "summary", "content", "author")
    list_editable = ("status",)
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "created_at"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "contact_email", "updated_at")


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ("path", "post", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("path",)
    readonly_fields = ("path", "post", "viewed_at")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "currency",
        "duration_days",
        "is_active",
        "display_order",
    )
    list_editable = ("is_active", "display_order")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "description")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan_name",
        "status",
        "requested_at",
        "starts_at",
        "expires_at",
    )
    list_filter = ("status", "plan", "requested_at")
    search_fields = ("user__username", "user__email", "plan_name")
    readonly_fields = (
        "user",
        "plan",
        "plan_name",
        "price",
        "currency",
        "duration_days",
        "status",
        "payment_reference",
        "requested_at",
        "approved_at",
        "approved_by",
        "rejected_at",
        "rejected_by",
        "rejection_reason",
        "cancelled_at",
        "cancelled_by",
        "cancellation_reason",
        "starts_at",
        "expires_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(admin.ModelAdmin):
    list_display = (
        "subscription",
        "event",
        "from_status",
        "to_status",
        "actor",
        "occurred_at",
    )
    list_filter = ("event", "occurred_at")
    search_fields = ("subscription__user__username", "subscription__user__email")
    readonly_fields = (
        "subscription",
        "event",
        "from_status",
        "to_status",
        "actor",
        "reason",
        "occurred_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionEmail)
class SubscriptionEmailAdmin(admin.ModelAdmin):
    list_display = (
        "subscription",
        "event",
        "recipient",
        "status",
        "attempts",
        "sent_at",
    )
    list_filter = ("status", "event")
    search_fields = ("recipient", "subscription__user__username")
    readonly_fields = (
        "subscription",
        "event",
        "recipient",
        "status",
        "attempts",
        "last_error",
        "sent_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.site_header = "News Website Dashboard"
admin.site.site_title = "News Admin"
admin.site.index_title = "Manage Website Content"