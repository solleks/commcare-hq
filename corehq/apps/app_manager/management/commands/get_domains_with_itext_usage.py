from __future__ import print_function
from collections import namedtuple
import sys
from django.core.management.base import BaseCommand
from corehq.apps.app_manager.dbaccessors import get_apps_in_domain
from corehq.apps.domain.models import Domain

ItextFetchError = namedtuple('ItextFetchError', 'domain app form')


class Command(BaseCommand):
    help = ("Import an app from another Commcare instance")

    def add_arguments(self, parser):
        parser.add_argument(
            'itext_type',
            help='audio, expanded-audio, video, etc.',
        )

    def handle(self, itext_type, **options):
        domains = [row['key'] for row in Domain.get_all(include_docs=False)]
        domain_data = {}
        errors = []
        for domain in domains:
            sys.stdout.write(".")
            app_data = {}
            for app in get_apps_in_domain(domain, include_remote=False):
                form_data = {}
                for module in app.get_modules():
                    for form in module.get_forms():
                        try:
                            xform = form.wrapped_xform()
                        except Exception as e:
                            errors.append(ItextFetchError(domain, app.get_id, form.get_unique_id()))
                            continue
                        total_refs = len(xform.media_references(form=itext_type))
                        if total_refs > 0:
                            form_data[form.unique_id] = total_refs
                if len(form_data) > 0:
                    app_data[app.get_id] = {
                        'data': form_data,
                        'total_refs': sum(form_data.values()),
                        'total_forms': len(form_data),
                    }
            if len(app_data) > 0:
                domain_data[domain] = {
                    'app_data': app_data,
                    'total_apps': len(app_data),
                    'total_refs': sum([a['total_refs'] for a in app_data.values()]),
                    'total_forms': sum([a['total_forms'] for a in app_data.values()]),
                }
        print('\n\n')
        print('DOMAINS USING "{}"'.format(itext_type))
        print('domain name\t# apps\t# forms\t# references')
        for domain, data in domain_data.items():
            print('{}\t{}\t{}\t{}'.format(
                domain,
                data['total_apps'],
                data['total_forms'],
                data['total_refs']
            ))

        print('\n\nERRORS')
        for error in errors:
            print('Error getting form {} in app {} from domain {}'.format(
                error.form, error.app, error.domain
            ))

        print('\n\n')
