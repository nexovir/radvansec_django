from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Post(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True, blank=True,
                             help_text="Leave blank to auto-generate from the title.")
    author = models.CharField(max_length=120, default="RadvanSec")
    summary = models.CharField(max_length=300,
                                help_text="One or two sentences shown on the blog list and homepage.")
    read_minutes = models.PositiveSmallIntegerField(default=5)
    body_html = models.TextField(
        help_text="Full post content as HTML (h2, p, pre/code, ul/li, div.callout, etc.). "
                   "Only paste content you trust, it is rendered unescaped."
    )
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:240]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:detail", args=[self.slug])
