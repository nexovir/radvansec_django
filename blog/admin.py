from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Post, Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at", "is_published", "read_minutes")
    list_filter = ("is_published",)
    search_fields = ("title", "summary", "body_html")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("authors",)
    date_hierarchy = "published_at"
    fieldsets = (
        (None, {"fields": ("title", "slug", "authors", "poster", "summary", "read_minutes")}),
        ("Content", {"fields": ("body_html",)}),
        ("Publishing", {"fields": ("is_published", "published_at")}),
    )