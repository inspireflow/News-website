
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    Post,
    Category,
    Section,
    SiteSettings,
    SubscriptionPlan,
)


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = [
            "title",
            "category",
            "section",
            "summary",
            "content",
            "image",
            "author",
            "status",
            "is_premium",
        ]

        labels = {
            "image": "Article image",
        }

        help_texts = {
            "image": "Upload an image for this article or news story.",
        }

        widgets = {
            "image": forms.ClearableFileInput(attrs={
                "accept": "image/*",
            }),
            "title": forms.TextInput(attrs={
                "placeholder": "Enter news headline",
            }),
            "summary": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Short news summary",
            }),
            "content": forms.Textarea(attrs={
                "rows": 12,
                "placeholder": "Write the full news article",
            }),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "is_active"]


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["title", "order", "is_active"]


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            "site_name",
            "tagline",
            "logo",
            "footer_text",
            "contact_email",
            "subscription_payment_instructions",
        ]


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")


class SubscriptionRequestForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField(label="Email address")
    plan = forms.ModelChoiceField(queryset=SubscriptionPlan.objects.none())
    payment_mode = forms.ChoiceField(
        choices=[("cash_on_delivery", "Cash on Delivery")],
        initial="cash_on_delivery",
    )
    payment_reference = forms.CharField(max_length=120, required=False)

    def __init__(self, *args, plans=None, user=None, selected_plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = (
            plans if plans is not None else SubscriptionPlan.objects.none()
        )
        if selected_plan is not None:
            self.initial.setdefault("plan", selected_plan)
        if user is not None:
            self.initial.setdefault(
                "full_name",
                user.get_full_name().strip(),
            )
            self.initial.setdefault("email", user.email)


class SubscriptionExpiryForm(forms.Form):
    expires_on = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Expiry date",
    )

    def clean_expires_on(self):
        expires_on = self.cleaned_data["expires_on"]
        if expires_on < timezone.localdate():
            raise forms.ValidationError("Expiry date cannot be in the past.")
        return expires_on


class SubscriptionReasonForm(forms.Form):
    reason = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "name",
            "description",
            "price",
            "currency",
            "duration_days",
            "is_active",
            "display_order",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "currency": forms.TextInput(attrs={"maxlength": 3, "placeholder": "INR"}),
            "duration_days": forms.NumberInput(attrs={"min": "1"}),
        }

    def clean_currency(self):
        currency = self.cleaned_data["currency"].strip().upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise forms.ValidationError("Enter a three-letter currency code.")
        return currency
