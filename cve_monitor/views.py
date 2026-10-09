from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import (
    Case, F, IntegerField, Max, Q, Sum, Value, When, prefetch_related_objects,
)
from django.shortcuts import render
from django.utils import timezone

from .models import CVE, CVEExploit

PERIODS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

SORTS = {
    "latest": F("latest_push").desc(nulls_last=True),
    "newest": F("discovered_at").desc(nulls_last=True),
    "stars": F("top_stars").desc(),
    "pocs": F("poc_count").desc(),
    "cvss": F("cvss_score").desc(nulls_last=True),
    "id": F("cve_id").desc(),
}


def _int(value, default=0):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _labels(cve, now):
    out = []
    if cve.discovered_at and cve.discovered_at >= now - timedelta(days=1):
        out.append(("new", "NEW"))
    if cve.severity in ("CRITICAL", "HIGH"):
        out.append((cve.severity.lower(), cve.severity))
    if cve.latest_push and cve.latest_push >= now - timedelta(days=7):
        out.append(("fresh", "FRESH PoC"))
    if cve.top_stars >= 100:
        out.append(("hot", "HOT"))
    if cve.poc_count >= 5:
        out.append(("multi", "MULTI PoC"))
    return out


def cve_list(request):
    now = timezone.now()
    day_ago = now - timedelta(days=1)
    g = request.GET

    q = g.get("q", "").strip()[:100]
    year = g.get("year", "")
    period = g.get("period", "")
    label = g.get("label", "")
    severity = g.get("severity", "").upper()
    min_stars = _int(g.get("min_stars"))
    min_pocs = _int(g.get("min_pocs"))

    # sort_param is what the user explicitly picked ("" = default view)
    sort_param = g.get("sort", "")
    sort = sort_param if sort_param in SORTS else "latest"

    has_filters = any([q, year, period, label, severity, min_stars, min_pocs])

    qs = CVE.objects.annotate(latest_push=Max("exploits__pushed_at"))

    if q:
        matching = CVEExploit.objects.filter(
            Q(repo_full_name__icontains=q) | Q(description__icontains=q)
        ).values("cve_id")
        qs = qs.filter(
            Q(cve_id__icontains=q) | Q(description__icontains=q) | Q(pk__in=matching)
        )
    if year.isdigit():
        qs = qs.filter(year=int(year))
    if period in PERIODS:
        qs = qs.filter(latest_push__gte=now - timedelta(days=PERIODS[period]))
    if severity in SEVERITIES:
        qs = qs.filter(severity=severity)
    if min_stars:
        qs = qs.filter(top_stars__gte=min_stars)
    if min_pocs:
        qs = qs.filter(poc_count__gte=min_pocs)

    if label == "new":
        qs = qs.filter(discovered_at__gte=day_ago)
    elif label == "fresh":
        qs = qs.filter(latest_push__gte=now - timedelta(days=7))
    elif label == "hot":
        qs = qs.filter(top_stars__gte=100)
    elif label == "multi":
        qs = qs.filter(poc_count__gte=5)

    # Plain "All" view (no filters, no explicit sort): NEW items first.
    if not has_filters and not sort_param:
        qs = qs.annotate(
            is_new=Case(
                When(discovered_at__gte=day_ago, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by("-is_new", SORTS[sort], "-id")
    else:
        qs = qs.order_by(SORTS[sort], "-id")

    page = Paginator(qs, 25).get_page(g.get("page"))
    items = list(page.object_list)

    # one query for all exploits of the CVEs on this page
    prefetch_related_objects(items, "exploits")
    for c in items:
        c.labels = _labels(c, now)
        c.repos = list(c.exploits.all())[:8]
        c.more = max(c.poc_count - len(c.repos), 0)

    params = g.copy()
    params.pop("page", None)

    stats = {
        "total": CVE.objects.count(),
        "pocs": CVE.objects.aggregate(s=Sum("poc_count"))["s"] or 0,
        "new24": CVE.objects.filter(discovered_at__gte=day_ago).count(),
        "fresh7": CVE.objects.filter(
            exploits__pushed_at__gte=now - timedelta(days=7)
        ).distinct().count(),
    }

    years = (
        CVE.objects.exclude(year=0)
        .values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )

    radar = list(
        CVE.objects.filter(discovered_at__gte=day_ago)
        .order_by("-discovered_at")
        .values_list("cve_id", "top_stars")[:14]
    )

    return render(request, "cve_monitor/cve_list.html", {
        "page": page,
        "items": items,
        "stats": stats,
        "years": years,
        "radar": radar,
        "qs": params.urlencode(),
        "f": {
            "q": q, "year": year, "period": period, "label": label,
            "sort": sort_param,          # empty = default (NEW first)
            "severity": severity,
            "min_stars": g.get("min_stars", ""),
            "min_pocs": g.get("min_pocs", ""),
        },
        "has_filters": has_filters,
    })