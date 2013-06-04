from corehq.apps.sms.mixin import SMSBackend
from dimagi.utils.couch.database import get_safe_write_kwargs
from couchdbkit.ext.django.schema import *

# TODO: What uses this? There already is a test backend

class TestBackend(SMSBackend):
    to_console = BooleanProperty(default=False)

    @classmethod
    def get_api_id(cls):
        return "TEST"

    def send(self, msg, *args, **kwargs):
        """
        The test backend does very little.
        """
        if self.to_console:
            print msg

def bootstrap(id=None, to_console=True):
    """
    Create an instance of the test backend in the database
    """
    backend = TestBackend(
        description='test backend',
        to_console=to_console,
    )
    if id:
        backend._id = id
    backend.save(**get_safe_write_kwargs())
    return backend

