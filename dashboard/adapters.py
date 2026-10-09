from allauth.account.utils import filter_users_by_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # If this social account is already linked, nothing to do.
        if sociallogin.is_existing:
            return

        email = sociallogin.account.extra_data.get("email") or sociallogin.user.email
        if not email:
            return

        # Only auto-connect if the provider has verified the email (Google does).
        verified = sociallogin.account.extra_data.get("email_verified", False)
        if not verified:
            return

        users = filter_users_by_email(email)
        if not users:
            return  # no existing account with this email, let normal signup happen

        # Connect this social login to the existing user and log them in.
        user = users[0]
        sociallogin.connect(request, user)