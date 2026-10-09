from django.db import models


class CVE(models.Model):
    cve_id = models.CharField(max_length=32, unique=True)
    year = models.PositiveSmallIntegerField(default=0, db_index=True)
    file_sha = models.CharField(max_length=64, blank=True)

    poc_count = models.PositiveIntegerField(default=0)
    top_repo_url = models.URLField(max_length=512, blank=True)
    top_stars = models.IntegerField(default=0)

    description = models.TextField(blank=True)
    severity = models.CharField(max_length=16, blank=True, db_index=True)
    cvss_score = models.FloatField(null=True, blank=True)
    cwe = models.CharField(max_length=128, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    enriched_at = models.DateTimeField(null=True, blank=True, db_index=True)
    enrich_attempts = models.PositiveSmallIntegerField(default=0)

    discovered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CVE"
        verbose_name_plural = "CVEs"
        ordering = ("-created_at",)

    def __str__(self):
        return self.cve_id


class CVEExploit(models.Model):
    cve = models.ForeignKey(CVE, on_delete=models.CASCADE, related_name="exploits")
    repo_full_name = models.CharField(max_length=255)
    repo_url = models.URLField(max_length=512)
    description = models.TextField(blank=True)
    stars = models.IntegerField(default=0)
    is_fork = models.BooleanField(default=False)
    pushed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cve", "repo_full_name")
        ordering = ("-stars",)

    def __str__(self):
        return f"{self.cve.cve_id}:{self.repo_full_name}"