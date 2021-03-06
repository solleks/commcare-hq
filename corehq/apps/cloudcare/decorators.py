from functools import wraps

from django.http import HttpResponse

from corehq.apps.domain.decorators import login_and_domain_required
from corehq.toggles import DISABLE_WEB_APPS
from corehq.apps.users.decorators import require_permission
from corehq.apps.users.models import Permissions


def require_cloudcare_access_ex():
    """
    Decorator for cloudcare users. Should require either access web apps
    permissions or they should be a mobile user.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _inner(request, domain, *args, **kwargs):
            if DISABLE_WEB_APPS.enabled_for_request(request):
                return HttpResponse('Service Temporarily Unavailable', content_type='text/plain', status=503)
            if hasattr(request, "couch_user"):
                if request.couch_user.is_web_user():
                    return require_permission(Permissions.access_web_apps)(view_func)(request, domain, *args, **kwargs)
                else:
                    assert request.couch_user.is_commcare_user(), \
                        "user was neither a web user or a commcare user!"
                    return login_and_domain_required(view_func)(request, domain, *args, **kwargs)
            return login_and_domain_required(view_func)(request, domain, *args, **kwargs)
        return _inner
    return decorator

require_cloudcare_access = require_cloudcare_access_ex()
