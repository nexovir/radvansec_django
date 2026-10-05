from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar = models.ImageField(upload_to="authors/", blank=True, null=True)
    bio = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


class Post(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(
        max_length=240, unique=True, blank=True,
        help_text="Leave blank to auto-generate from the title.",
    )
    authors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="blog_posts",
        blank=True,
    )
    poster = models.ImageField(
        upload_to="posters/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional poster image shown at the top of the post.",
    )
    summary = models.CharField(
        max_length=300,
        help_text="One or two sentences shown on the blog list and homepage.",
    )
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

    def author_names(self):
        return ", ".join(
            a.get_full_name() or a.get_username() for a in self.authors.all()
        )