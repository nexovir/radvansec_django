from datetime import timedelta

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import CVE, CVEExploit


# ---------------------------------------------------------------------------
# Custom filters
# ---------------------------------------------------------------------------
class HasPocFilter(admin.SimpleListFilter):
    """Filter CVEs by whether any PoC exists."""

    title = "has PoC"
    parameter_name = "has_poc"

    def lookups(self, request, model_admin):
        return (("yes", "Has PoC"), ("no", "No PoC"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(poc_count__gt=0)
        if self.value() == "no":
            return queryset.filter(poc_count=0)
        return queryset


class PocCountRangeFilter(admin.SimpleListFilter):
    """Filter CVEs by number of PoCs."""

    title = "PoC count"
    parameter_name = "poc_range"

    def lookups(self, request, model_admin):
        return (
            ("0", "0"),
            ("1", "1"),
            ("2-5", "2 - 5"),
            ("6-10", "6 - 10"),
            ("11+", "More than 10"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "0":
            return queryset.filter(poc_count=0)
        if value == "1":
            return queryset.filter(poc_count=1)
        if value == "2-5":
            return queryset.filter(poc_count__gte=2, poc_count__lte=5)
        if value == "6-10":
            return queryset.filter(poc_count__gte=6, poc_count__lte=10)
        if value == "11+":
            return queryset.filter(poc_count__gt=10)
        return queryset


class StarsRangeFilter(admin.SimpleListFilter):
    """Reusable stars-range filter (works on any integer stars-like field)."""

    title = "stars"
    parameter_name = "stars_range"
    field_name = "stars"

    def lookups(self, request, model_admin):
        return (
            ("0", "No stars"),
            ("1-10", "1 - 10"),
            ("11-100", "11 - 100"),
            ("101-1000", "101 - 1000"),
            ("1000+", "More than 1000"),
        )

    def queryset(self, request, queryset):
        f = self.field_name
        value = self.value()
        if value == "0":
            return queryset.filter(**{f: 0})
        if value == "1-10":
            return queryset.filter(**{f"{f}__gte": 1, f"{f}__lte": 10})
        if value == "11-100":
            return queryset.filter(**{f"{f}__gte": 11, f"{f}__lte": 100})
        if value == "101-1000":
            return queryset.filter(**{f"{f}__gte": 101, f"{f}__lte": 1000})
        if value == "1000+":
            return queryset.filter(**{f"{f}__gt": 1000})
        return queryset


class TopStarsRangeFilter(StarsRangeFilter):
    title = "top repo stars"
    parameter_name = "top_stars_range"
    field_name = "top_stars"


class HasTopRepoFilter(admin.SimpleListFilter):
    title = "top repo"
    parameter_name = "has_top_repo"

    def lookups(self, request, model_admin):
        return (("yes", "Has top repo"), ("no", "No top repo"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(top_repo_url="")
        if self.value() == "no":
            return queryset.filter(top_repo_url="")
        return queryset


class SyncedFilter(admin.SimpleListFilter):
    """Whether the CVE has been synced (file_sha stored)."""

    title = "sync status"
    parameter_name = "synced"

    def lookups(self, request, model_admin):
        return (("yes", "Synced"), ("no", "Pending sync"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(file_sha="")
        if self.value() == "no":
            return queryset.filter(file_sha="")
        return queryset


class PushedRecentlyFilter(admin.SimpleListFilter):
    title = "last pushed"
    parameter_name = "pushed_recently"

    def lookups(self, request, model_admin):
        return (
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
            ("365", "Last year"),
            ("old", "Older than a year"),
            ("none", "Unknown"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        now = timezone.now()
        if value in ("30", "90", "365"):
            return queryset.filter(pushed_at__gte=now - timedelta(days=int(value)))
        if value == "old":
            return queryset.filter(pushed_at__lt=now - timedelta(days=365))
        if value == "none":
            return queryset.filter(pushed_at__isnull=True)
        return queryset


class CVEYearListFilter(admin.SimpleListFilter):
    """Year filter listing only years that exist, newest first."""

    title = "year"
    parameter_name = "year"

    def lookups(self, request, model_admin):
        years = (
            CVE.objects.order_by("-year")
            .values_list("year", flat=True)
            .distinct()
        )
        return [(y, str(y)) for y in years]

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(year=self.value())
        return queryset


# ---------------------------------------------------------------------------
# Inline
# ---------------------------------------------------------------------------
class CVEExploitInline(admin.TabularInline):
    model = CVEExploit
    extra = 0
    fields = ("repo_full_name", "repo_link", "stars", "is_fork", "pushed_at")
    readonly_fields = fields
    can_delete = False
    ordering = ("-stars",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Repo URL")
    def repo_link(self, obj):
        if not obj.repo_url:
            return "-"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>',
            obj.repo_url,
        )


# ---------------------------------------------------------------------------
# CVE admin
# ---------------------------------------------------------------------------
@admin.register(CVE)
class CVEAdmin(admin.ModelAdmin):
    list_display = (
        "cve_id",
        "year",
        "poc_count",
        "top_stars",
        "top_repo_link",
        "is_synced",
        "created_at",
        "updated_at",
    )
    list_display_links = ("cve_id",)
    list_filter = (
        CVEYearListFilter,
        HasPocFilter,
        PocCountRangeFilter,
        TopStarsRangeFilter,
        HasTopRepoFilter,
        SyncedFilter,
        ("created_at", admin.DateFieldListFilter),
        ("updated_at", admin.DateFieldListFilter),
    )
    search_fields = ("cve_id", "top_repo_url", "file_sha")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    show_full_result_count = False
    save_on_top = True
    inlines = [CVEExploitInline]
    actions = ["force_refetch"]

    fieldsets = (
        ("General", {"fields": ("cve_id", "year", "file_sha")}),
        ("PoC stats", {"fields": ("poc_count", "top_repo_url", "top_stars")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Top repo", ordering="top_repo_url")
    def top_repo_link(self, obj):
        if not obj.top_repo_url:
            return "-"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>',
            obj.top_repo_url,
        )

    @admin.display(description="Synced", boolean=True, ordering="file_sha")
    def is_synced(self, obj):
        return bool(obj.file_sha)

    @admin.action(description="Force re-fetch on next sync")
    def force_refetch(self, request, queryset):
        updated = queryset.update(file_sha="")
        self.message_user(
            request, f"{updated} CVE(s) will be re-fetched on the next sync."
        )


# ---------------------------------------------------------------------------
# CVEExploit admin
# ---------------------------------------------------------------------------
@admin.register(CVEExploit)
class CVEExploitAdmin(admin.ModelAdmin):
    list_display = (
        "repo_full_name",
        "cve",
        "stars",
        "is_fork",
        "pushed_at",
        "repo_link",
        "created_at",
    )
    list_display_links = ("repo_full_name",)
    list_filter = (
        "is_fork",
        StarsRangeFilter,
        PushedRecentlyFilter,
        ("pushed_at", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
        ("cve__year", admin.AllValuesFieldListFilter),
    )
    search_fields = ("repo_full_name", "repo_url", "cve__cve_id", "description")
    raw_id_fields = ("cve",)
    readonly_fields = ("created_at",)
    list_select_related = ("cve",)
    ordering = ("-stars",)
    date_hierarchy = "pushed_at"
    list_per_page = 50
    show_full_result_count = False
    save_on_top = True

    @admin.display(description="Repo URL", ordering="repo_url")
    def repo_link(self, obj):
        if not obj.repo_url:
            return "-"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>',
            obj.repo_url,
        )