import importlib

from django.apps import AppConfig, apps
from django.core.checks import Critical, Warning, register
from django.db.utils import OperationalError, ProgrammingError
from django.test import RequestFactory


class OAuthSsoConfig(AppConfig):
    name = 'corehq.apps.oauth_sso'
    verbose_name = "OAuth2 SSO"

@register()
def microsoft_auth_validator(app_configs, **kwargs):
    from django.contrib.sites.models import Site
    from .conf import config

    errors = []

    if apps.is_installed("microsoft_auth") and not apps.is_installed(
        "django.contrib.sites"
    ):

        errors.append(
            Critical(
                "`django.contrib.sites` is not installed",
                hint=(
                    "`microsoft_auth` requires `django.contrib.sites` "
                    "to be installed and configured"
                ),
                id="microsoft_auth.E001",
            )
        )

    try:
        if not hasattr(config, "SITE_ID"):
            request = RequestFactory().get("/", HTTP_HOST="example.com")
            current_site = Site.objects.get_current(request)
        else:
            current_site = Site.objects.get_current()
    except Site.DoesNotExist:
        pass
    except (OperationalError, ProgrammingError):
        errors.append(
            Warning(
                "`django.contrib.sites` migrations not ran",
                id="microsoft_auth.W001",
            )
        )
    else:
        if current_site.domain == "example.com":
            errors.append(
                Warning(
                    (
                        "`example.com` is still a valid site, Microsoft "
                        "auth might not work"
                    ),
                    hint=(
                        "Microsoft auth uses OAuth, which requires "
                        "a real redirect URI to come back to"
                    ),
                    id="microsoft_auth.W002",
                )
            )

    return errors
