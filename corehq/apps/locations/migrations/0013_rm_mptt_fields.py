# Generated by Django 1.11.13 on 2018-05-29 16:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0012_get_location_fixture_ids'),
    ]

    operations = [
        migrations.AlterIndexTogether(name='sqllocation', index_together=set([])),
        migrations.RemoveField(model_name='sqllocation', name='level'),
        migrations.RemoveField(model_name='sqllocation', name='lft'),
        migrations.RemoveField(model_name='sqllocation', name='rght'),
        migrations.RemoveField(model_name='sqllocation', name='tree_id'),
    ]
