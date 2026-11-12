
from django.db import DatabaseError
from django.utils import timezone

from .models import PageView, Post


class PageViewMiddleware:
    EXCLUDED_PREFIXES = (
        "/dashboard/",
        "/admin/",
        "/static/",
        "/media/",
        "/search-suggestions/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.method == "GET"
            and response.status_code == 200
            and not request.path.startswith(self.EXCLUDED_PREFIXES)
            and not request.path.startswith("/favicon")
            and not request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            try:
                post = None
                slug = getattr(
                    getattr(request, "resolver_match", None),
                    "kwargs",
                    {},
                ).get("slug")

                if slug:
                    post = Post.objects.filter(
                        slug=slug,
                        status="published",
                    ).first()

                PageView.objects.create(
                    path=request.path[:500],
                    post=post,
                    viewed_at=timezone.now(),
                )
            except DatabaseError:
                # Avoid breaking the public website if analytics
                # storage is temporarily unavailable.
                pass

        return response
