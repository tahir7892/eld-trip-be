from django.contrib.admin.forms import AdminAuthenticationForm


class EmailOrUsernameAdminAuthenticationForm(AdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email or username"
        self.fields["username"].widget.attrs.setdefault(
            "placeholder", "Email or username"
        )
