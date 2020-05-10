import uuid

from django.db import models

from dimagi.ext.couchdbkit import DateTimeProperty, Document, StringProperty
from dimagi.utils.parsing import json_format_datetime

from .utils import generate_aes_key


class SQLMobileAuthKeyRecord(models.Model):
    domain = models.CharField(max_length=126, null=False, db_index=True)
    user_id = models.CharField(max_length=255, null=False, db_index=True)

    valid = models.DateTimeField(null=False)    # initialized with 30 days before the date created
    expires = models.DateTimeField(null=False)  # just bumped up by multiple of 30 days when expired
    type = models.CharField(null=False, max_length=32, choices=[('AES256', 'AES256')], default='AES256')
    key = models.CharField(null=False, max_length=127)

    class Meta:
        db_table = "mobile_auth_mobileauthkeyrecord"
