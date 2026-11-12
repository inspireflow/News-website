import logging
import hashlib
import secrets
import smtplib
from datetime import datetime, time, timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import BadHeaderError, InvalidMailer, send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import (
    Subscription,
    SubscriptionEmail,
    SubscriptionEvent,
)


logger = logging.getLogger(__name__)


def record_subscription_event(
    subscription,
    event,
    from_status="",
    to_status="",
    actor=None,
    reason="",
):
    return SubscriptionEvent.objects.create(
        subscription=subscription,
        event=event,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        reason=reason,
    )


def _send_expiry_email_on_commit(subscription_id):
    transaction.on_commit(
        lambda: deliver_subscription_email(subscription_id, "user_expired")
    )


def expire_due_subscriptions(user_id=None):
    now = timezone.now()
    due = Subscription.objects.filter(status=Subscription.ACTIVE).filter(
        Q(expires_at__lte=now) | Q(expires_at__isnull=True),
    )
    if user_id is not None:
        due = due.filter(user_id=user_id)

    for subscription_id in due.values_list("id", flat=True).iterator():
        with transaction.atomic():
            subscription = Subscription.objects.select_for_update().get(
                pk=subscription_id,
            )
            if (
                subscription.status != Subscription.ACTIVE
                or (
                    subscription.expires_at is not None
                    and subscription.expires_at > now
                )
            ):
                continue

            subscription.status = Subscription.EXPIRED
            subscription.save(update_fields=["status", "updated_at"])
            record_subscription_event(
                subscription,
                event="expired",
                from_status=Subscription.ACTIVE,
                to_status=Subscription.EXPIRED,
                reason="Subscription reached its expiry date.",
            )
            _send_expiry_email_on_commit(subscription.pk)


def create_subscription_request(
    user,
    plan,
    payment_reference="",
    full_name="",
    email="",
    payment_mode=Subscription.CASH_ON_DELIVERY,
):
    expire_due_subscriptions(user_id=user.pk)
    try:
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            existing = Subscription.objects.filter(
                user=user,
                status=Subscription.ACTIVE,
            ).order_by("-requested_at").first()
            if existing is not None:
                raise ValidationError(
                    "You already have an active subscription."
                )

            existing = Subscription.objects.filter(
                user=user,
                plan=plan,
                status=Subscription.PENDING,
            ).order_by("-requested_at").first()
            if existing is not None:
                return existing, False

            subscription = Subscription.objects.create(
                user=user,
                plan=plan,
                plan_name=plan.name,
                price=plan.price,
                currency=plan.currency,
                duration_days=plan.duration_days,
                full_name=full_name or user.get_full_name().strip(),
                email=email or user.email,
                payment_mode=payment_mode,
                payment_reference=payment_reference,
            )
            record_subscription_event(
                subscription,
                event="requested",
                to_status=Subscription.PENDING,
                actor=user,
            )
            return subscription, True
    except IntegrityError:
        pending = Subscription.objects.filter(
            user=user,
            plan=plan,
            status=Subscription.PENDING,
        ).first()
        if pending is not None:
            return pending, False
        pending = Subscription.objects.filter(
            user=user,
            status=Subscription.PENDING,
        ).first()
        if pending is not None:
            return pending, False
        if Subscription.objects.filter(
            user=user,
            status=Subscription.ACTIVE,
        ).exists():
            raise ValidationError(
                "You already have an active subscription."
            )
        raise


def review_subscription(subscription_id, actor, approve, reason=""):
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(
            pk=subscription_id,
        )
        get_user_model().objects.select_for_update().get(
            pk=subscription.user_id,
        )

        if (
            actor is not None
            and subscription.user_id == actor.pk
            and not actor.is_staff
        ):
            raise ValidationError("You cannot review your own subscription.")
        if subscription.status != Subscription.PENDING:
            raise ValidationError(
                "Only pending subscription requests can be reviewed."
            )

        now = timezone.now()
        if approve:
            expire_due_subscriptions(user_id=subscription.user_id)
            active = Subscription.objects.filter(
                user_id=subscription.user_id,
                status=Subscription.ACTIVE,
            ).exclude(pk=subscription.pk).exists()
            if active:
                raise ValidationError(
                    "The subscriber already has an active subscription."
                )

            subscription.status = Subscription.ACTIVE
            subscription.approved_at = now
            subscription.approved_by = actor
            subscription.starts_at = now
            subscription.expires_at = now + timedelta(
                days=subscription.duration_days,
            )
            event = "approved"
            to_status = Subscription.ACTIVE
        else:
            subscription.status = Subscription.REJECTED
            subscription.rejected_at = now
            subscription.rejected_by = actor
            subscription.rejection_reason = reason
            event = "rejected"
            to_status = Subscription.REJECTED

        if subscription.approval_token_hash:
            subscription.approval_token_used_at = now
        subscription.save()
        record_subscription_event(
            subscription,
            event=event,
            from_status=Subscription.PENDING,
            to_status=to_status,
            actor=actor,
            reason=reason,
        )
        return subscription


def cancel_subscription(subscription_id, actor, reason=""):
    already_expired = False
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(
            pk=subscription_id,
        )
        get_user_model().objects.select_for_update().get(
            pk=subscription.user_id,
        )
        if subscription.status != Subscription.ACTIVE:
            raise ValidationError(
                "Only active subscriptions can be cancelled."
            )

        now = timezone.now()
        if subscription.expires_at is None or subscription.expires_at <= now:
            subscription.status = Subscription.EXPIRED
            subscription.save(update_fields=["status", "updated_at"])
            record_subscription_event(
                subscription,
                event="expired",
                from_status=Subscription.ACTIVE,
                to_status=Subscription.EXPIRED,
                reason="Subscription reached its expiry date.",
            )
            _send_expiry_email_on_commit(subscription.pk)
            already_expired = True
        else:
            subscription.status = Subscription.CANCELLED
            subscription.cancelled_at = now
            subscription.cancelled_by = actor
            subscription.cancellation_reason = reason
            subscription.save()
            record_subscription_event(
                subscription,
                event="cancelled",
                from_status=Subscription.ACTIVE,
                to_status=Subscription.CANCELLED,
                actor=actor,
                reason=reason,
            )

    if already_expired:
        raise ValidationError("This subscription has already expired.")
    return subscription


def issue_admin_review_token(subscription_id):
    subscription = Subscription.objects.get(pk=subscription_id)
    if subscription.status != Subscription.PENDING:
        raise ValidationError("Only pending requests can be emailed for review.")
    token = secrets.token_urlsafe(32)
    subscription.approval_token_hash = hashlib.sha256(
        token.encode("utf-8"),
    ).hexdigest()
    subscription.approval_token_expires_at = timezone.now() + timedelta(days=7)
    subscription.approval_token_used_at = None
    subscription.save(update_fields=[
        "approval_token_hash",
        "approval_token_expires_at",
        "approval_token_used_at",
        "updated_at",
    ])
    return token


def email_review_state(subscription, token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not subscription.approval_token_hash or not secrets.compare_digest(
        subscription.approval_token_hash,
        token_hash,
    ):
        return "invalid"
    if (
        subscription.status != Subscription.PENDING
        or subscription.approval_token_used_at is not None
    ):
        return "processed"
    if (
        subscription.approval_token_expires_at is None
        or subscription.approval_token_expires_at <= timezone.now()
    ):
        return "expired"
    return "pending"


def review_subscription_from_email(subscription_id, token, approve):
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(
            pk=subscription_id,
        )
        state = email_review_state(subscription, token)
        if state != "pending":
            raise ValidationError({
                "processed": "This subscription request has already been processed.",
                "expired": "This review link has expired.",
                "invalid": "This review link is invalid.",
            }[state])
        return review_subscription(
            subscription_id,
            actor=None,
            approve=approve,
        )


def schedule_subscription_expiry(subscription_id, expires_on, actor):
    if expires_on < timezone.localdate():
        raise ValidationError("Expiry date cannot be in the past.")
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(
            pk=subscription_id,
        )
        if subscription.status != Subscription.ACTIVE:
            raise ValidationError("Only active subscriptions can be scheduled.")
        previous_expiry = subscription.expires_at
        subscription.expires_at = timezone.make_aware(
            datetime.combine(expires_on, time.max),
        )
        subscription.save(update_fields=["expires_at", "updated_at"])
        record_subscription_event(
            subscription,
            event="expiry_scheduled",
            from_status=Subscription.ACTIVE,
            to_status=Subscription.ACTIVE,
            actor=actor,
            reason=(
                f"Expiry changed from {previous_expiry} to "
                f"{subscription.expires_at}."
            ),
        )
        return subscription


def _absolute_url(path, request=None):
    site_url = (
        getattr(settings, "BASE_URL", "")
        or getattr(settings, "SITE_URL", "")
    ).strip()
    if site_url:
        return urljoin(f"{site_url.rstrip('/')}/", path.lstrip("/"))
    return request.build_absolute_uri(path) if request is not None else path


def _email_content(subscription, event, request=None, review_token=""):
    user = subscription.user
    recipient = ""
    if event == "admin_requested":
        recipient = (
            getattr(settings, "ADMIN_EMAIL", "").strip()
            or getattr(settings, "SUBSCRIPTION_ADMIN_EMAIL", "").strip()
        )
        links = "\n".join(
            f"{action.title()}: {_absolute_url(reverse('subscription_email_review', args=[subscription.pk, action, review_token]), request)}"
            for action in ("approve", "reject")
        )
        details_url = _absolute_url(
            reverse("dashboard:subscription_detail", args=[subscription.pk]),
            request,
        )
        subject = f"Subscription request #{subscription.pk}"
        status = "Pending administrator review"
        greeting = "A new subscription request was submitted."
    else:
        recipient = (subscription.email or user.email).strip()
        path = reverse("subscription_status")
        content = {
            "user_approved": (
                "Your subscription request was approved.",
                "Approved",
            ),
            "user_rejected": (
                "Your subscription request was rejected.",
                "Rejected",
            ),
            "user_cancelled": (
                "Your subscription was cancelled by an administrator.",
                "Cancelled",
            ),
            "user_expired": (
                "Your subscription has expired.",
                "Expired",
            ),
        }
        greeting, status = content[event]
        subject = f"Subscription update: {status}"

    if event == "admin_requested":
        username = (
            subscription.full_name
            or user.get_full_name().strip()
            or user.get_username()
        )
        text = (
            f"{greeting}\n\n"
            f"Name: {username}\n"
            f"Email: {subscription.email or user.email}\n"
            f"Plan: {subscription.plan_name}\n"
            f"Price: {subscription.price} {subscription.currency}\n"
            f"Duration: {subscription.duration_days} days\n"
            f"Payment mode: {subscription.get_payment_mode_display()}\n"
            f"Request date: {timezone.localtime(subscription.requested_at)}\n"
            f"Request ID: {subscription.pk}\n"
            f"Status: {status}\n\n"
            f"Dashboard details: {details_url}\n"
            f"{links}\n"
        )
    else:
        request_url = _absolute_url(path, request)
        username = user.get_full_name().strip() or user.get_username()
        text = (
            f"{greeting}\n\n"
            f"Subscriber: {username}\n"
            f"Email: {subscription.email or user.email}\n"
            f"Plan: {subscription.plan_name}\n"
            f"Request ID: {subscription.pk}\n"
            f"Requested: {timezone.localtime(subscription.requested_at)}\n"
            f"Status: {status}\n"
            f"Details: {request_url}\n"
        )
    return subject, text, recipient


def deliver_subscription_email(
    subscription_id,
    event,
    request=None,
    review_token="",
):
    subscription = Subscription.objects.select_related("user").get(
        pk=subscription_id,
    )
    delivery, created = SubscriptionEmail.objects.get_or_create(
        subscription=subscription,
        event=event,
    )
    if not created and delivery.status != SubscriptionEmail.PENDING:
        return delivery.status == SubscriptionEmail.SENT

    if event == "admin_requested" and not review_token:
        review_token = issue_admin_review_token(subscription_id)
    subject, body, recipient = _email_content(
        subscription,
        event,
        request,
        review_token,
    )
    delivery.recipient = recipient
    delivery.status = SubscriptionEmail.SENDING
    delivery.attempts += 1
    delivery.last_error = ""
    delivery.save()

    try:
        if not recipient:
            raise ValueError("No recipient email is configured.")
        sent = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        if sent != 1:
            raise OSError("The email backend did not confirm delivery.")
    except (
        BadHeaderError,
        ImproperlyConfigured,
        InvalidMailer,
        ImportError,
        OSError,
        smtplib.SMTPException,
        TypeError,
        ValueError,
        ConnectionError,
    ) as error:
        delivery.status = SubscriptionEmail.FAILED
        delivery.last_error = "Email delivery failed. Check server email configuration."
        delivery.save(update_fields=[
            "status",
            "last_error",
            "updated_at",
        ])
        logger.warning(
            "Subscription email delivery failed for delivery id %s (%s).",
            delivery.pk,
            type(error).__name__,
        )
        return False

    delivery.status = SubscriptionEmail.SENT
    delivery.sent_at = timezone.now()
    delivery.save(update_fields=[
        "status",
        "sent_at",
        "last_error",
        "updated_at",
    ])
    return True


def retry_subscription_email(delivery_id, request=None):
    delivery = SubscriptionEmail.objects.get(pk=delivery_id)
    if delivery.status != SubscriptionEmail.FAILED:
        raise ValidationError("Only failed email deliveries can be retried.")
    delivery.status = SubscriptionEmail.PENDING
    delivery.save(update_fields=["status", "updated_at"])
    return deliver_subscription_email(
        delivery.subscription_id,
        delivery.event,
        request=request,
    )
