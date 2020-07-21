import datetime

from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View

from django_extensions.management.commands import show_urls

class ShowUrlsView(View):
    page_title = _("Show Urls")
    urlname = 'show_urls'
    file_name = 'AllMappedUrls.txt'

    def __init__(self, *args, **kwargs):
        self.command = show_urls.Command()
        super(ShowUrlsView, self).__init__(*args, **kwargs)
    
    def dispatch(self, request, *args, **kwargs):
        # Actually call show_urls command.
        all_views = self.command.handle(verbosity=1,
                                        settings=None,
                                        pythonpath=None,
                                        traceback=False,
                                        no_color=True,
                                        unsorted=False,
                                        language=None,
                                        decorator=[],
                                        format_style='dense',
                                        urlconf='ROOT_URLCONF')
        f = open(self.file_name, 'w')
        print(all_views, file=f)
        f.close()

        now = datetime.datetime.now()
        html = "<html><body>Showing URLs at %s.</body></html>" % now
        return HttpResponse(html)
