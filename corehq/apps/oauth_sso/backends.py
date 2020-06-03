import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .client import MicrosoftClient
from .models import MicrosoftAccount, AzureADConfiguration

logger = logging.getLogger("django")
User = get_user_model()


class MicrosoftAuthenticationBackend(ModelBackend):
    """ Authentication backend to authenticate a user against their Microsoft
        Uses Microsoft's Graph OAuth to authentiate. """

    config = None
    microsoft = None

    def __init__(self, user=None):
        from .conf import config

        self.config = config

    def authenticate(self, request, code=None):
        """
            Authenticates the user against the Django backend
                using a Microsoft auth code from
            https://login.microsoftonline.com/common/oauth2/v2.0/authorize or
            https://login.live.com/oauth20_authorize.srf

            For more details:
            https://developer.microsoft.com/en-us/graph/docs/get-started/rest
        """
        state = request.GET['state']
        if state is None:
            print('No state found in request', request.GET.dict())
            return None

        project_name = state.split('$')[0]
        azure_ad_config = None
        try:
            azure_ad_config = AzureADConfiguration.objects.get(
                project=project_name)
        except AzureADConfiguration.DoesNotExist:
            print('No Azure AD config found for project:', project_name)
            return None
        
        self.client = MicrosoftClient(azure_ad_config, state=state,
                                      request=request)

        user = None
        if code is not None:
            # fetch OAuth token
            token = self.client.fetch_token(code=code)

            # validate permission scopes
            if "access_token" in token and self.client.valid_scopes(
                    token["scope"]
            ):
                user = self._authenticate_user()

        return user

    def _authenticate_user(self):
        return self._authenticate_microsoft_user()

    def _authenticate_microsoft_user(self):
        claims = self.client.get_claims()

        if claims is not None:
            return self._get_user_from_microsoft(claims)

        return None

    def _get_user_from_microsoft(self, data):
        """ Retrieves existing Django user """
        user = None
        microsoft_user = self._get_microsoft_user(data)
        print('microsoft_user:', microsoft_user)

        if microsoft_user is not None:
            user = self._verify_microsoft_user(microsoft_user, data)

        return user

    def _get_microsoft_user(self, data):
        microsoft_user = None

        try:
            microsoft_user = MicrosoftAccount.objects.get(
                microsoft_id=data["sub"]
            )
        except MicrosoftAccount.DoesNotExist:
            if self.config.MICROSOFT_AUTH_AUTO_CREATE:
                # create new Microsoft Account
                microsoft_user = MicrosoftAccount(microsoft_id=data["sub"])
                microsoft_user.save()

        return microsoft_user

    def _verify_microsoft_user(self, microsoft_user, data):
        user = microsoft_user.user

        if user is None:
            fullname = data.get("name")
            first_name, last_name = "", ""
            if fullname is not None:
                first_name, last_name = data["name"].split(" ", 1)

            try:
                print('Find user from data:', data)
                # create new Django user from provided data
                user = User.objects.get(email=data["email"])

                if user.first_name == "" and user.last_name == "":
                    user.first_name = first_name
                    user.last_name = last_name
                    user.save()
            except User.DoesNotExist:
                user = User(
                    username=data["preferred_username"][:150],
                    first_name=first_name,
                    last_name=last_name,
                    email=data["email"],
                )
                user.save()

            existing_account = self._get_existing_microsoft_account(user)
            if existing_account is not None:
                if self.config.MICROSOFT_AUTH_AUTO_REPLACE_ACCOUNTS:
                    existing_account.user = None
                    existing_account.save()
                else:
                    logger.warning(
                        (
                            "User {} already has linked Microsoft "
                            "account and MICROSOFT_AUTH_AUTO_REPLACE_ACCOUNTS "
                            "is False"
                        ).format(user.email)
                    )
                    return None

            microsoft_user.user = user
            microsoft_user.save()

        return user

    def _get_existing_microsoft_account(self, user):
        try:
            return MicrosoftAccount.objects.get(user=user)
        except MicrosoftAccount.DoesNotExist:
            return None
