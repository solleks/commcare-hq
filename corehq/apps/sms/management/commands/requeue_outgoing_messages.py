from django.core.management.base import BaseCommand

from corehq.apps.sms.models import OUTGOING, SMS
from corehq.util.argparse_types import utc_timestamp


class Command(BaseCommand):
    help = ""

    def add_arguments(self, parser):
        parser.add_argument('domain')
        parser.add_argument('start_timestamp', type=utc_timestamp)
        parser.add_argument('end_timestamp', type=utc_timestamp)

    def handle(self, domain, start_timestamp, end_timestamp, **options):
        result = SMS.objects.filter(
            domain=domain,
            direction=OUTGOING,
            processed=False,
            date__gte=start_timestamp,
            date__lt=end_timestamp,
        )

        print(
            "Requeuing unprocessed outgoing messages for domain %s attempted between %s and %s..." %
            (domain, start_timestamp, end_timestamp)
        )

        count = result.count()
        if count == 0:
            print("No messages available to requeue.")
            return

        if input("%s unprocessed outgoing messages found. Requeue them? y/n: " % count).strip().lower() != 'y':
            print("Aborted.")
            return

        for sms in result:
            sms.requeue()

        print("Messages requeued.")
