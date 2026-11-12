from datetime import timedelta
from decimal import Decimal
from io import BytesIO
import tempfile
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

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
from .subscription_services import (
    create_subscription_request,
    deliver_subscription_email,
    retry_subscription_email,
    review_subscription,
)


class PostImageUploadTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_settings = override_settings(
            MEDIA_ROOT=self.media_directory.name,
        )
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)

        user = get_user_model().objects.create_user(
            username="editor",
            password="test-password",
            is_staff=True,
        )
        self.client.force_login(user)
        self.category = Category.objects.create(name="Local News")

    def image_upload(self, name):
        image = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image, format="PNG")
        return SimpleUploadedFile(
            name,
            image.getvalue(),
            content_type="image/png",
        )

    def post_data(self, title):
        return {
            "title": title,
            "category": self.category.pk,
            "summary": "A short news summary.",
            "content": "The full article text.",
            "author": "News Desk",
            "status": Post.DRAFT,
        }

    def test_add_and_edit_news_support_image_uploads(self):
        add_response = self.client.get(reverse("dashboard:post_create"))

        self.assertEqual(add_response.status_code, 200)
        self.assertContains(add_response, 'type="file"')
        self.assertContains(add_response, "Article image")
        self.assertContains(add_response, 'name="csrfmiddlewaretoken"')
        self.assertContains(add_response, "dashboard-menu-toggle")
        self.assertContains(add_response, "js/dashboard.js")

        create_response = self.client.post(
            reverse("dashboard:post_create"),
            {
                **self.post_data("First story"),
                "image": self.image_upload("first.png"),
            },
        )

        post = Post.objects.get(title="First story")
        self.assertRedirects(
            create_response,
            reverse("dashboard:posts"),
        )
        self.assertTrue(post.image.name.startswith("news/"))
        self.assertTrue(post.image.storage.exists(post.image.name))

        edit_form_response = self.client.get(
            reverse("dashboard:post_edit", args=[post.pk]),
        )
        self.assertContains(edit_form_response, "Current article image")

        edit_response = self.client.post(
            reverse("dashboard:post_edit", args=[post.pk]),
            {
                **self.post_data("First story"),
                "image": self.image_upload("replacement.png"),
            },
        )

        post.refresh_from_db()
        self.assertRedirects(edit_response, reverse("dashboard:posts"))
        self.assertTrue(post.image.name.endswith("replacement.png"))
        self.assertTrue(post.image.storage.exists(post.image.name))

        posts_response = self.client.get(
            reverse("dashboard:posts"),
            {"status": Post.DRAFT},
        )
        self.assertEqual(posts_response.status_code, 200)
        self.assertContains(posts_response, "First story")
        self.assertNotContains(
            self.client.get(
                reverse("dashboard:posts"),
                {"status": Post.PUBLISHED},
            ),
            "First story",
        )

    def test_published_post_with_uploaded_image_is_available_publicly(self):
        response = self.client.post(
            reverse("dashboard:post_create"),
            {
                **self.post_data("Published image story"),
                "status": Post.PUBLISHED,
                "image": self.image_upload("published.png"),
            },
            follow=True,
        )

        post = Post.objects.get(title="Published image story")
        self.assertEqual(response.redirect_chain[-1][0], reverse("dashboard:posts"))
        self.assertContains(response, "News post created successfully.")
        self.assertContains(response, post.title)
        self.assertTrue(post.image.storage.exists(post.image.name))

        article_response = self.client.get(reverse("article", args=[post.slug]))
        self.assertEqual(article_response.status_code, 200)
        self.assertContains(article_response, post.image.url)
        self.assertContains(article_response, post.title)

    def test_empty_post_submission_is_bound_and_shows_required_errors(self):
        response = self.client.post(reverse("dashboard:post_create"), {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(Post.objects.exists())

    def test_invalid_submission_preserves_values_and_does_not_save(self):
        response = self.client.post(
            reverse("dashboard:post_create"),
            {
                "title": "Unfinished article",
                "summary": "A summary waiting for category.",
                "content": "Draft article content.",
                "author": "News Desk",
                "status": Post.DRAFT,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Unfinished article"')
        self.assertContains(response, "A summary waiting for category.")
        self.assertContains(response, "This field is required.")
        self.assertFalse(Post.objects.exists())

    def test_dashboard_management_pages_render_for_staff(self):
        section = Section.objects.create(title="Front Page")
        post = Post.objects.create(
            title="Dashboard test article",
            category=self.category,
            summary="Dashboard test summary.",
            content="Dashboard test content.",
        )
        urls = [
            reverse("dashboard:overview"),
            reverse("dashboard:analytics"),
            reverse("dashboard:posts"),
            reverse("dashboard:post_create"),
            reverse("dashboard:post_delete", args=[post.pk]),
            reverse("dashboard:categories"),
            reverse("dashboard:category_create"),
            reverse("dashboard:category_edit", args=[self.category.pk]),
            reverse("dashboard:category_delete", args=[self.category.pk]),
            reverse("dashboard:sections"),
            reverse("dashboard:section_create"),
            reverse("dashboard:section_edit", args=[section.pk]),
            reverse("dashboard:section_delete", args=[section.pk]),
            reverse("dashboard:settings"),
            reverse("dashboard:subscriptions"),
            reverse("dashboard:subscription_plans"),
            reverse("dashboard:subscription_plan_create"),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class DashboardAnalyticsTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="analytics-editor",
            is_staff=True,
        )
        self.client.force_login(user)
        self.category = Category.objects.create(name="Data News")
        self.post = Post.objects.create(
            title="Measured article",
            category=self.category,
            summary="A tracked story.",
            content="Article content.",
            author="News Desk",
            status=Post.PUBLISHED,
        )

    def test_analytics_uses_saved_content_and_page_views(self):
        for _ in range(3):
            PageView.objects.create(
                path=f"/article/{self.post.slug}/",
                post=self.post,
            )

        response = self.client.get(reverse("dashboard:analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "analytics-views")
        self.assertContains(response, "Traffic source split")
        chart_data = response.context["chart_data"]
        self.assertEqual(chart_data["categories"]["labels"], [self.category.name])
        self.assertEqual(chart_data["categories"]["articles"], [1])
        self.assertEqual(chart_data["categories"]["views"], [3])
        self.assertEqual(chart_data["authors"]["labels"], ["News Desk"])
        self.assertEqual(chart_data["popular"]["values"], [3])
        self.assertEqual(chart_data["goals"]["articles"]["value"], 1)
        self.assertEqual(chart_data["traffic_sources_sample"]["values"], [42, 31, 18, 9])

    def test_analytics_remains_staff_only(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:analytics"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:login"), response.url)


class PublicSearchTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Local News")
        self.post = Post.objects.create(
            title="Searchable public headline",
            category=self.category,
            summary="A public summary for search.",
            content="The full article text.",
            status=Post.PUBLISHED,
        )

    def test_search_page_and_suggestions_return_published_stories(self):
        page_response = self.client.get(
            reverse("search"),
            {"q": "searchable"},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, self.post.title)

        suggestions_response = self.client.get(
            reverse("search_suggestions"),
            {"q": "searchable"},
        )
        self.assertEqual(suggestions_response.status_code, 200)
        self.assertEqual(
            suggestions_response.json()["results"][0]["title"],
            self.post.title,
        )

    def test_search_does_not_include_drafts(self):
        Post.objects.create(
            title="Searchable draft headline",
            category=self.category,
            summary="A draft summary.",
            content="Draft text.",
            status=Post.DRAFT,
        )

        response = self.client.get(reverse("search"), {"q": "searchable"})

        self.assertContains(response, self.post.title)
        self.assertNotContains(response, "Searchable draft headline")

    def test_home_category_and_article_pages_render(self):
        draft_section = Section.objects.create(title="Draft-only section")
        Post.objects.create(
            title="Unpublished home test",
            category=self.category,
            section=draft_section,
            summary="Draft summary.",
            content="Draft content.",
            status=Post.DRAFT,
        )
        home_response = self.client.get(reverse("home"))
        category_response = self.client.get(
            reverse("category", args=[self.category.slug]),
        )
        article_response = self.client.get(
            reverse("article", args=[self.post.slug]),
        )

        self.assertEqual(home_response.status_code, 200)
        self.assertNotContains(home_response, draft_section.title)
        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(article_response.status_code, 200)


class PremiumSubscriptionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.subscriber = user_model.objects.create_user(
            username="subscriber",
            email="reader@example.com",
            first_name="Jane",
            last_name="Doe",
            password="a-secure-test-password",
        )
        self.staff = user_model.objects.create_user(
            username="subscription-admin",
            email="admin@example.com",
            password="a-secure-test-password",
            is_staff=True,
        )
        self.category = Category.objects.create(name="Premium News")
        self.plan = SubscriptionPlan.objects.create(
            name="Test Premium",
            description="A test plan.",
            price="12.50",
            currency="USD",
            duration_days=30,
        )
        self.full_content = "one two three four five hidden-premium-paragraph"
        self.post = Post.objects.create(
            title="Premium story",
            category=self.category,
            summary="A preview summary.",
            content=self.full_content,
            status=Post.PUBLISHED,
            is_premium=True,
        )

    def request_data(self, plan=None, **values):
        return {
            "full_name": "Jane Doe",
            "email": "reader@example.com",
            "plan": str((plan or self.plan).pk),
            "payment_mode": "cash_on_delivery",
            **values,
        }

    @override_settings(PREMIUM_PREVIEW_WORDS=4)
    def test_anonymous_and_non_subscriber_receive_only_preview(self):
        self.post.is_premium = False
        self.post.save(update_fields=["is_premium"])
        response = self.client.get(reverse("article", args=[self.post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unlock the Full Story")
        self.assertContains(response, "Subscribe Now")
        self.assertContains(response, "one two three four…")
        self.assertNotContains(response, "hidden-premium-paragraph")
        self.assertEqual(response.context["post"].content, "one two three four…")

        self.client.force_login(self.subscriber)
        response = self.client.get(reverse("article", args=[self.post.slug]))
        self.assertContains(response, "Unlock the Full Story")
        self.assertNotContains(response, "hidden-premium-paragraph")

    def test_all_articles_require_an_active_subscription_for_full_content(self):
        self.post.is_premium = False
        self.post.save(update_fields=["is_premium"])
        response = self.client.get(reverse("article", args=[self.post.slug]))
        self.assertContains(response, "Unlock the Full Story")
        self.assertNotContains(response, "hidden-premium-paragraph")

        now = timezone.now()
        Subscription.objects.create(
            user=self.subscriber,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
            status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=10),
            approved_at=now,
            approved_by=self.staff,
        )
        self.client.force_login(self.subscriber)
        response = self.client.get(reverse("article", args=[self.post.slug]))
        self.assertContains(response, "hidden-premium-paragraph")
        self.assertNotContains(response, "Unlock the Full Story")

    def test_public_listing_pages_and_suggestions_do_not_expose_premium_body(self):
        responses = [
            self.client.get(reverse("home")),
            self.client.get(
                reverse("category", args=[self.category.slug]),
            ),
            self.client.get(reverse("search"), {"q": "Premium story"}),
        ]
        for response in responses:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertNotContains(response, "hidden-premium-paragraph")

        suggestion = self.client.get(
            reverse("search_suggestions"),
            {"q": "Premium"},
        ).json()
        self.assertNotIn(
            "hidden-premium-paragraph",
            str(suggestion),
        )

        home_featured = responses[0].context["featured"]
        self.assertIn("content", home_featured.get_deferred_fields())

    def test_new_user_can_register_for_subscription_access(self):
        response = self.client.post(
            reverse("account_register"),
            {
                "username": "new-premium-reader",
                "email": "new-reader@example.com",
                "password1": "r4#Kp9!sZ2@vX7m",
                "password2": "r4#Kp9!sZ2@vX7m",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            get_user_model().objects.filter(
                username="new-premium-reader",
                email="new-reader@example.com",
            ).exists()
        )
        self.assertContains(response, "My subscriptions")

    def test_pending_rejected_cancelled_and_expired_subscriptions_do_not_unlock(self):
        statuses = [
            Subscription.PENDING,
            Subscription.REJECTED,
            Subscription.CANCELLED,
            Subscription.ACTIVE,
        ]
        for status in statuses:
            with self.subTest(status=status):
                Subscription.objects.all().delete()
                now = timezone.now()
                Subscription.objects.create(
                    user=self.subscriber,
                    plan=self.plan,
                    plan_name=self.plan.name,
                    price=self.plan.price,
                    currency=self.plan.currency,
                    duration_days=self.plan.duration_days,
                    status=status,
                    starts_at=                    now - timedelta(days=3),
                    expires_at=(
                        now - timedelta(days=1)
                        if status == Subscription.ACTIVE
                        else None
                    ),
                )
                self.client.force_login(self.subscriber)
                response = self.client.get(
                    reverse("article", args=[self.post.slug]),
                )
                self.assertNotContains(response, "hidden-premium-paragraph")
                self.assertContains(response, "Unlock the Full Story")

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        SUBSCRIPTION_ADMIN_EMAIL="admin@example.com",
        SITE_URL="https://news.example",
    )
    def test_subscription_request_requires_login_and_starts_pending(self):
        request_url = reverse(
            "subscription_request",
            args=[self.plan.pk],
        )
        response = self.client.post(request_url, {})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)
        self.assertFalse(Subscription.objects.exists())

        self.client.force_login(self.subscriber)
        response = self.client.post(
            request_url,
            self.request_data(payment_reference="REF-123"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        subscription = Subscription.objects.get(user=self.subscriber)
        self.assertEqual(subscription.status, Subscription.PENDING)
        self.assertEqual(subscription.payment_reference, "REF-123")
        self.assertEqual(subscription.full_name, "Jane Doe")
        self.assertEqual(subscription.email, "reader@example.com")
        self.assertEqual(subscription.payment_mode, "cash_on_delivery")
        self.assertIsNone(subscription.starts_at)
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=subscription,
                event="requested",
                to_status=Subscription.PENDING,
            ).exists()
        )
        self.assertContains(response, "Pending")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reader@example.com", mail.outbox[0].body)

    def test_subscription_pages_render_with_configured_plan_and_instructions(self):
        SiteSettings.objects.create(
            site_name="News",
            subscription_payment_instructions="Use the configured payment method.",
        )
        plans_response = self.client.get(reverse("subscription_plans"))
        login_response = self.client.get(reverse("account_login"))
        signup_response = self.client.get(reverse("account_register"))

        self.assertEqual(plans_response.status_code, 200)
        self.assertContains(plans_response, self.plan.name)
        self.assertContains(plans_response, self.plan.currency)
        self.assertContains(plans_response, "Use the configured payment method.")
        self.assertContains(plans_response, "Sign in to request")
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(signup_response.status_code, 200)

    def test_active_subscription_prevents_a_second_request(self):
        now = timezone.now()
        Subscription.objects.create(
            user=self.subscriber,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
            status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=10),
            approved_at=now,
            approved_by=self.staff,
        )
        self.client.force_login(self.subscriber)
        response = self.client.post(
            reverse("subscription_request", args=[self.plan.pk]),
            self.request_data(),
            follow=True,
        )
        self.assertEqual(
            Subscription.objects.filter(user=self.subscriber).count(),
            1,
        )
        self.assertContains(response, "already have an active subscription")

    def test_subscription_request_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.subscriber)
        response = client.post(
            reverse("subscription_request", args=[self.plan.pk]),
            {
                "full_name": "Jane Doe",
                "email": "reader@example.com",
                "plan": str(self.plan.pk),
                "payment_mode": "cash_on_delivery",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Subscription.objects.exists())

    def test_approval_cannot_be_repeated(self):
        subscription, _ = create_subscription_request(
            self.subscriber,
            self.plan,
        )
        review_subscription(subscription.pk, self.staff, approve=True)
        with self.assertRaises(ValidationError):
            review_subscription(subscription.pk, self.staff, approve=True)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.ACTIVE)
        self.assertEqual(
            SubscriptionEvent.objects.filter(
                subscription=subscription,
                event="approved",
            ).count(),
            1,
        )

    def test_staff_can_configure_plans_inside_existing_dashboard(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(
                reverse("dashboard:subscription_plans"),
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse("dashboard:subscription_plan_create"),
            {
                "name": "Monthly Premium",
                "description": "Monthly membership.",
                "price": "499.00",
                "currency": "inr",
                "duration_days": "30",
                "is_active": "on",
                "display_order": "1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        plan = SubscriptionPlan.objects.get(name="Monthly Premium")
        self.assertEqual(plan.price, Decimal("499.00"))
        self.assertEqual(plan.currency, "INR")

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        SUBSCRIPTION_ADMIN_EMAIL="",
    )
    def test_failed_email_is_visible_and_can_be_retried(self):
        subscription, created = create_subscription_request(
            self.subscriber,
            self.plan,
        )
        self.assertTrue(created)
        self.assertFalse(
            deliver_subscription_email(subscription.pk, "admin_requested")
        )
        delivery = SubscriptionEmail.objects.get(
            subscription=subscription,
            event="admin_requested",
        )
        self.assertEqual(delivery.status, SubscriptionEmail.FAILED)
        self.assertTrue(delivery.last_error)

        with self.settings(SUBSCRIPTION_ADMIN_EMAIL="admin@example.com"):
            self.assertTrue(retry_subscription_email(delivery.pk))

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, SubscriptionEmail.SENT)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(delivery.recipient, "admin@example.com")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        SUBSCRIPTION_ADMIN_EMAIL="admin@example.com",
    )
    def test_staff_rejection_and_cancellation_are_post_only_and_audited(self):
        pending = Subscription.objects.create(
            user=self.subscriber,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
        )
        self.client.force_login(self.staff)
        reject_url = reverse(
            "dashboard:subscription_action",
            args=[pending.pk, "reject"],
        )
        self.assertEqual(self.client.post(reject_url, {"reason": "Unverified"}).status_code, 302)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Subscription.REJECTED)
        self.assertEqual(pending.rejected_by, self.staff)
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=pending,
                event="rejected",
                actor=self.staff,
                reason="Unverified",
            ).exists()
        )

        active_user = get_user_model().objects.create_user(
            username="active-reader",
            email="active@example.com",
        )
        now = timezone.now()
        active = Subscription.objects.create(
            user=active_user,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
            status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=10),
        )
        cancel_url = reverse(
            "dashboard:subscription_action",
            args=[active.pk, "cancel"],
        )
        response = self.client.post(
            cancel_url,
            {"reason": "Account requested cancellation."},
            follow=True,
        )
        active.refresh_from_db()
        self.assertEqual(active.status, Subscription.CANCELLED)
        self.assertEqual(active.cancelled_by, self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        SUBSCRIPTION_ADMIN_EMAIL="admin@example.com",
        SITE_URL="https://news.example",
    )
    def test_duplicate_pending_request_does_not_create_duplicate_or_email(self):
        self.client.force_login(self.subscriber)
        url = reverse("subscription_request", args=[self.plan.pk])
        self.client.post(url, self.request_data(payment_reference="REF-1"))
        self.client.post(url, self.request_data(payment_reference="REF-2"))

        self.assertEqual(Subscription.objects.filter(user=self.subscriber).count(), 1)
        self.assertEqual(SubscriptionEmail.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Request ID:", mail.outbox[0].body)
        self.assertIn("https://news.example/dashboard/subscriptions/", mail.outbox[0].body)

    def test_only_staff_can_manage_subscriptions_and_users_see_only_their_history(self):
        other_user = get_user_model().objects.create_user(
            username="other-reader",
            email="other@example.com",
            password="a-secure-test-password",
        )
        other_request, _ = create_subscription_request(
            other_user,
            self.plan,
        )
        self.client.force_login(self.subscriber)

        dashboard_response = self.client.get(
            reverse("dashboard:subscriptions"),
        )
        self.assertEqual(dashboard_response.status_code, 302)
        status_response = self.client.get(reverse("subscription_status"))
        self.assertEqual(status_response.status_code, 200)
        self.assertNotContains(status_response, "other@example.com")
        self.assertNotContains(status_response, f"Request #{other_request.pk}")

        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("dashboard:subscriptions")).status_code,
            200,
        )
        create_subscription_request(self.subscriber, self.plan)
        filtered = self.client.get(
            reverse("dashboard:subscriptions"),
            {"q": "Jane Doe"},
        )
        self.assertContains(filtered, "reader@example.com")
        self.assertNotContains(filtered, "other@example.com")

    def test_approval_and_cancellation_are_audited_and_expiry_is_enforced(self):
        subscription, created = create_subscription_request(
            self.subscriber,
            self.plan,
        )
        self.assertTrue(created)
        approved = review_subscription(
            subscription.pk,
            self.staff,
            approve=True,
            reason="Payment reference checked.",
        )
        self.assertEqual(approved.status, Subscription.ACTIVE)
        self.assertEqual(approved.approved_by, self.staff)
        self.assertGreater(approved.expires_at, approved.starts_at)
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=approved,
                event="approved",
                actor=self.staff,
            ).exists()
        )

        self.client.force_login(self.subscriber)
        self.assertContains(
            self.client.get(reverse("article", args=[self.post.slug])),
            "hidden-premium-paragraph",
        )

        approved.expires_at = timezone.now() - timedelta(seconds=1)
        approved.save(update_fields=["expires_at"])
        expired_response = self.client.get(
            reverse("article", args=[self.post.slug]),
        )
        approved.refresh_from_db()
        self.assertEqual(approved.status, Subscription.EXPIRED)
        self.assertNotContains(expired_response, "hidden-premium-paragraph")

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        ADMIN_EMAIL="admin@example.com",
        BASE_URL="https://news.example",
    )
    def test_admin_can_approve_only_with_post_and_receive_email(self):
        subscription, _ = create_subscription_request(
            self.subscriber,
            self.plan,
        )
        self.client.force_login(self.staff)
        detail_url = reverse(
            "dashboard:subscription_detail",
            args=[subscription.pk],
        )
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertTrue(
            deliver_subscription_email(subscription.pk, "admin_requested"),
        )
        approve_url = next(
            line.removeprefix("Approve: ")
            for line in mail.outbox[0].body.splitlines()
            if line.startswith("Approve: ")
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "dashboard:subscription_action",
                    args=[subscription.pk, "approve"],
                )
            ).status_code,
            405,
        )
        response = self.client.post(
            reverse(
                "dashboard:subscription_action",
                args=[subscription.pk, "approve"],
            ),
            {"reason": "Verified."},
            follow=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.ACTIVE)
        self.assertEqual(subscription.approved_by, self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active")
        self.assertContains(
            self.client.get(urlsplit(approve_url).path),
            "already been processed",
        )

    def test_staff_can_review_own_demo_request(self):
        subscription, _ = create_subscription_request(
            self.staff,
            self.plan,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "dashboard:subscription_action",
                args=[subscription.pk, "approve"],
            ),
            follow=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(subscription.status, Subscription.ACTIVE)
        self.assertEqual(
            subscription.expires_at - subscription.starts_at,
            timedelta(days=self.plan.duration_days),
        )
        self.assertContains(response, "Active")
        self.assertContains(
            self.client.get(reverse("article", args=[self.post.slug])),
            "hidden-premium-paragraph",
        )

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        SUBSCRIPTION_ADMIN_EMAIL="admin@example.com",
        SITE_URL="https://news.example",
    )
    def test_plan_requests_are_plan_specific_and_dashboard_approval_unlocks_article(self):
        second_plan = SubscriptionPlan.objects.create(
            name="Second Premium",
            description="Another demo plan.",
            price="20.00",
            currency="USD",
            duration_days=45,
        )
        self.client.force_login(self.subscriber)
        first_request_url = reverse(
            "subscription_request",
            args=[self.plan.pk],
        )
        second_request_url = reverse(
            "subscription_request",
            args=[second_plan.pk],
        )

        self.client.post(first_request_url, self.request_data())
        self.client.post(second_request_url, self.request_data(plan=second_plan))
        self.client.post(first_request_url, self.request_data())

        self.assertEqual(
            Subscription.objects.filter(
                user=self.subscriber,
                status=Subscription.PENDING,
            ).count(),
            2,
        )

        second_request = Subscription.objects.get(
            user=self.subscriber,
            plan=second_plan,
        )
        self.client.force_login(self.staff)
        approval_response = self.client.post(
            reverse(
                "dashboard:subscription_action",
                args=[second_request.pk, "approve"],
            ),
            {"reason": "Demo approval."},
            follow=True,
        )
        second_request.refresh_from_db()
        self.assertEqual(approval_response.status_code, 200)
        self.assertEqual(second_request.status, Subscription.ACTIVE)
        self.assertIsNotNone(second_request.starts_at)
        self.assertIsNotNone(second_request.expires_at)

        self.client.force_login(self.subscriber)
        article_response = self.client.get(
            reverse("article", args=[self.post.slug]),
        )
        self.assertContains(article_response, "hidden-premium-paragraph")

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        },
        DEFAULT_FROM_EMAIL="news@example.com",
        ADMIN_EMAIL="admin@example.com",
        BASE_URL="https://news.example",
    )
    def test_request_form_and_email_review_links_are_single_use_and_post_only(self):
        self.client.force_login(self.subscriber)
        plans_response = self.client.get(
            reverse("subscription_plans"),
            {"plan": self.plan.pk},
        )
        self.assertContains(plans_response, 'name="full_name"')
        self.assertContains(plans_response, 'name="email"')
        self.assertContains(plans_response, 'name="plan"')
        self.assertContains(plans_response, "Cash on Delivery")
        self.assertNotContains(plans_response, 'name="mobile"')

        response = self.client.post(
            reverse("subscription_request_form"),
            self.request_data(),
            follow=True,
        )
        subscription = Subscription.objects.get(user=self.subscriber)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(subscription.status, Subscription.PENDING)
        self.assertEqual(subscription.full_name, "Jane Doe")
        self.assertEqual(subscription.email, "reader@example.com")
        self.assertEqual(subscription.payment_mode, "cash_on_delivery")
        self.assertEqual(len(mail.outbox), 1)
        for detail in (
            "Jane Doe",
            "reader@example.com",
            "Test Premium",
            "12.50",
            "30 days",
            "Cash on Delivery",
        ):
            self.assertIn(detail, mail.outbox[0].body)

        approve_url = next(
            line.removeprefix("Approve: ")
            for line in mail.outbox[0].body.splitlines()
            if line.startswith("Approve: ")
        )
        path = urlsplit(approve_url).path
        confirmation = self.client.get(path)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "Confirm approve")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.PENDING)

        confirmation = self.client.post(path)
        subscription.refresh_from_db()
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(subscription.status, Subscription.ACTIVE)
        self.assertEqual(
            subscription.expires_at - subscription.starts_at,
            timedelta(days=self.plan.duration_days),
        )
        self.client.force_login(self.subscriber)
        self.assertContains(
            self.client.get(reverse("article", args=[self.post.slug])),
            "hidden-premium-paragraph",
        )

        repeated = self.client.get(path)
        self.assertContains(repeated, "already been processed")

    def test_email_rejection_and_subscription_owner_cancellation_block_access(self):
        other_user = get_user_model().objects.create_user(
            username="reject-reader",
            email="reject@example.com",
        )
        pending, _ = create_subscription_request(
            other_user,
            self.plan,
            full_name="Reject Reader",
            email="reject@example.com",
        )
        with self.settings(
            MAILERS={
                "default": {
                    "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
                },
            },
            DEFAULT_FROM_EMAIL="news@example.com",
            ADMIN_EMAIL="admin@example.com",
            BASE_URL="https://news.example",
        ):
            deliver_subscription_email(pending.pk, "admin_requested")
        reject_url = next(
            line.removeprefix("Reject: ")
            for line in mail.outbox[0].body.splitlines()
            if line.startswith("Reject: ")
        )
        reject_path = urlsplit(reject_url).path
        self.client.get(reject_path)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Subscription.PENDING)
        self.client.post(reject_path)
        pending.refresh_from_db()
        self.assertEqual(pending.status, Subscription.REJECTED)

        active = Subscription.objects.create(
            user=self.subscriber,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
            status=Subscription.ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=20),
        )
        self.client.force_login(self.subscriber)
        response = self.client.post(
            reverse("subscription_cancel", args=[active.pk]),
            follow=True,
        )
        active.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(active.status, Subscription.CANCELLED)
        self.assertNotContains(
            self.client.get(reverse("article", args=[self.post.slug])),
            "hidden-premium-paragraph",
        )

    def test_staff_can_schedule_expiry_and_user_cannot_schedule_expiry(self):
        active = Subscription.objects.create(
            user=self.subscriber,
            plan=self.plan,
            plan_name=self.plan.name,
            price=self.plan.price,
            currency=self.plan.currency,
            duration_days=self.plan.duration_days,
            status=Subscription.ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=20),
        )
        expiry_date = timezone.localdate() + timedelta(days=2)
        schedule_url = reverse(
            "dashboard:subscription_schedule_expiry",
            args=[active.pk],
        )
        self.client.force_login(self.subscriber)
        self.assertEqual(
            self.client.post(
                schedule_url,
                {"expires_on": expiry_date.isoformat()},
            ).status_code,
            302,
        )
        active.refresh_from_db()
        self.assertNotEqual(
            timezone.localtime(active.expires_at).date(),
            expiry_date,
        )

        self.client.force_login(self.staff)
        response = self.client.post(
            schedule_url,
            {"expires_on": expiry_date.isoformat()},
            follow=True,
        )
        active.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            timezone.localtime(active.expires_at).date(),
            expiry_date,
        )
        self.assertContains(response, expiry_date.strftime("%d %b %Y"))
        self.assertContains(
            self.client.get(reverse("dashboard:subscriptions")),
            "Days remaining",
        )

        active.expires_at = timezone.now() - timedelta(seconds=1)
        active.save(update_fields=["expires_at"])
        self.client.force_login(self.subscriber)
        self.assertNotContains(
            self.client.get(reverse("article", args=[self.post.slug])),
            "hidden-premium-paragraph",
        )
        active.refresh_from_db()
        self.assertEqual(active.status, Subscription.EXPIRED)
