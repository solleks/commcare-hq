# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-05-05
from __future__ import unicode_literals
from django.db import migrations, models
from corehq.sql_db.operations import RawSQLMigration
from custom.icds_reports.utils.migrations import get_view_migrations

migrator = RawSQLMigration(('custom', 'icds_reports', 'migrations', 'sql_templates', 'database_views'))


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0179_location_deprecation_columns'),
    ]

    operations = get_view_migrations() 
