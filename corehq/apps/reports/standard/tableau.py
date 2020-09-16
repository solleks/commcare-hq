import sys

from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from corehq.apps.locations.permissions import location_safe
from corehq.apps.reports.standard import (
    ProjectReport,
)

from corehq.apps.reports.models import TableauVisualization


class TableauReport(ProjectReport):
    """
    Base class for all Tableau reports
    """
    base_template = 'reports/tableau_template.html'
    emailable = False
    exportable = False
    exportable_all = False
    ajax_pagination = False
    fields = []
    primary_sort_prop = None

    @property
    def template_context(self):
        context = super().template_context
        context.update({"server": self.visualization.server.server_name,
                        "target_site": self.visualization.server.target_site,
                        "view_url": self.visualization.view_url})
        return context


# Making a class per visualization (and on each page load) is overkill, but
# a class is expected for items in the left nav bar, so we do that for
# expedience.
def get_reports(domain):
    vis_num = 1
    result = []
    for v in TableauVisualization.objects.all().filter(project=domain):
        result.append(_make_visualization_class(vis_num, v))
        vis_num += 1
    return tuple(result)
    # return (ExampleReport,)

def _make_visualization_class(num, vis):
    # See _make_report_class in corehq/reports.py
    type_name = 'TableauVisualization{}'.format(num)

    view_sheet = '/'.join(vis.view_url.split('?')[0].split('/')[-2:])

    new_class = type(type_name, (TableauReport,), {
        'name': view_sheet,
        'slug': 'tableau_visualization_{}'.format(num),
        'visualization': vis,
    })
    # Make the class a module attribute
    setattr(sys.modules[__name__], type_name, new_class)
    return location_safe(new_class)
