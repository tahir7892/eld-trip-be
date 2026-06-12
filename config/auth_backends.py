from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Allow admin login with either username or email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        login = username or kwargs.get(User.USERNAME_FIELD)
        if not login or not password:
            return None

        if "@" in login:
            user = User.objects.filter(email__iexact=login).first()
        else:
            user = User.objects.filter(username__iexact=login).first()

        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
