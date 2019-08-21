# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

import datetime

from django.utils.functional import cached_property

from corehq.apps.hqwebapp.decorators import use_nvd3
from corehq.apps.locations.models import SQLLocation
from corehq.apps.reports.graph_models import MultiBarChart, Axis
from corehq.apps.reports.standard import ProjectReportParametersMixin, CustomProjectReport, DatespanMixin
from custom.intrahealth.filters import DateRangeFilter, ProgramsAndProductsFilter, YeksiNaaLocationFilter
from custom.intrahealth.sqldata import ExpirationRatePerProductData2
from dimagi.utils.dates import force_to_date


class TauxDePeremptionReport(CustomProjectReport, DatespanMixin, ProjectReportParametersMixin):
    slug = 'taux_de_peremption_report'
    comment = 'valeur péremption sur valeur totale'
    name = 'Taux de Péremption'
    default_rows = 10

    report_template_path = 'yeksi_naa/tabular_report.html'

    @use_nvd3
    def decorator_dispatcher(self, request, *args, **kwargs):
        super(TauxDePeremptionReport, self).decorator_dispatcher(request, *args, **kwargs)

    @property
    def fields(self):
        return [DateRangeFilter, ProgramsAndProductsFilter, YeksiNaaLocationFilter]

    @cached_property
    def rendered_report_title(self):
        return self.name

    @property
    def report_context(self):
        context = {
            'report': self.get_report_context(),
            'title': self.name,
            'charts': self.charts if not self.needs_filters else None
        }

        return context

    @property
    def selected_location(self):
        try:
            return SQLLocation.objects.get(location_id=self.request.GET.get('location_id'))
        except SQLLocation.DoesNotExist:
            return None

    @property
    def selected_location_type(self):
        if self.selected_location:
            location_type = self.selected_location.location_type.code
            if location_type == 'region':
                return 'Region'
            elif location_type == 'district':
                return 'District'
            elif location_type == 'pps':
                return 'PPS'
        else:
            pass

    @property
    def headers(self):
        return ExpirationRatePerProductData2(config=self.config).headers

    def get_report_context(self):
        if self.needs_filters:
            headers = []
            rows = []
        else:
            rows = self.calculate_rows()
            headers = self.headers

        context = dict(
            report_table=dict(
                title=self.name,
                slug=self.slug,
                comment=self.comment,
                headers=headers,
                rows=rows,
                default_rows=self.default_rows,
            )
        )

        return context

    def calculate_rows(self):
        rows = ExpirationRatePerProductData2(config=self.config).rows
        return rows

    @property
    def charts(self):
        chart = MultiBarChart(None, Axis('Location'), Axis('Percent', format='.2f'))
        chart.forceY = [0, 100]

        chart.height = 400
        chart.marginBottom = 100

        def get_data_for_graph():
            com = []
            rows = self.calculate_rows()
            for row in rows:
                #-1 removes % symbol for cast to float
                y = row[-1]['html'][:-1]
                try:
                    y = float(y)
                except ValueError:
                    y = 0
                com.append({"x": row[0]['html'], "y": y})

            return [
                {
                    "key": "'Méthode de calcul: nbre de PPS avec le produit disponsible sur le nbre total de PPS visités de la période'",
                    'values': com
                },
            ]

        chart.data = get_data_for_graph()
        return [chart]

    @property
    def config(self):
        config = dict(
            domain=self.domain,
        )
        if self.request.GET.get('startdate'):
            startdate = force_to_date(self.request.GET.get('startdate'))
        else:
            startdate = datetime.datetime.now()
        if self.request.GET.get('enddate'):
            enddate = force_to_date(self.request.GET.get('enddate'))
        else:
            enddate = datetime.datetime.now()
        config['startdate'] = startdate
        config['enddate'] = enddate
        config['product_program'] = self.request.GET.get('product_program')
        config['products'] = self.request.GET.get('products')
        config['product_product'] = self.request.GET.get('product_product')
        config['selected_location'] = self.request.GET.get('location_id')

        if self.selected_location_type == "PPS":
            config['pps_id'] = self.request.GET.get('location_id')
        elif self.selected_location_type == "District":
            config['district_id'] = self.request.GET.get('location_id')
        elif self.selected_location_type == "Region":
            config['region_id'] = self.request.GET.get('location_id')

        return config
