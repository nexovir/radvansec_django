from django.contrib import admin
from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at", "is_published", "read_minutes")
    list_filter = ("is_published",)
    search_fields = ("title", "summary", "body_html")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    fieldsets = (
        (None, {"fields": ("title", "slug", "author", "summary", "read_minutes")}),
        ("Content", {"fields": ("body_html",)}),
        ("Publishing", {"fields": ("is_published", "published_at")}),
    )
