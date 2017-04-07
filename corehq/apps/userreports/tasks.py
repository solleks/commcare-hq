from __future__ import absolute_import
from collections import defaultdict
from datetime import datetime
import hashlib

from celery.task import task, periodic_task
from couchdbkit import ResourceConflict
from django.conf import settings
from django.utils.translation import ugettext as _

from corehq import toggles
from corehq.apps.userreports.const import (
    UCR_ES_BACKEND, UCR_SQL_BACKEND, UCR_CELERY_QUEUE, UCR_INDICATOR_CELERY_QUEUE,
    ASYNC_INDICATOR_QUEUE_TIME,
)
from corehq.apps.userreports.document_stores import get_document_store
from corehq.apps.userreports.rebuild import DataSourceResumeHelper
from corehq.apps.userreports.specs import EvaluationContext
from corehq.apps.userreports.models import (
    AsyncIndicator,
    DataSourceConfiguration,
    StaticDataSourceConfiguration,
    id_is_static,
    ReportConfiguration,
)
from corehq.apps.userreports.reports.factory import ReportFactory
from corehq.apps.userreports.util import get_indicator_adapter, get_async_indicator_modify_lock_key
from corehq.util.context_managers import notify_someone
from corehq.util.couch import get_document_or_not_found
from corehq.util.datadog.gauges import datadog_gauge
from corehq.util.quickcache import quickcache
from dimagi.utils.couch import CriticalSection, release_lock
from dimagi.utils.couch.cache.cache_core import get_redis_client
from dimagi.utils.couch.pagination import DatatablesParams
from pillowtop.dao.couch import ID_CHUNK_SIZE


def _get_config_by_id(indicator_config_id):
    if id_is_static(indicator_config_id):
        return StaticDataSourceConfiguration.by_id(indicator_config_id)
    else:
        return DataSourceConfiguration.get(indicator_config_id)


def _build_indicators(config, document_store, relevant_ids, resume_helper):
    adapter = get_indicator_adapter(config, raise_errors=True, can_handle_laboratory=True)

    last_id = None
    for doc in document_store.iter_documents(relevant_ids):
        # save is a noop if the filter doesn't match
        adapter.best_effort_save(doc)
        last_id = doc.get('_id')
        resume_helper.remove_id(last_id)

    if last_id:
        resume_helper.add_id(last_id)


@task(queue=UCR_CELERY_QUEUE, ignore_result=True)
def rebuild_indicators(indicator_config_id, initiated_by=None):
    config = _get_config_by_id(indicator_config_id)
    success = _('Your UCR table {} has finished rebuilding').format(config.table_id)
    failure = _('There was an error rebuilding Your UCR table {}.').format(config.table_id)
    send = toggles.SEND_UCR_REBUILD_INFO.enabled(initiated_by)
    with notify_someone(initiated_by, success_message=success, error_message=failure, send=send):
        adapter = get_indicator_adapter(config, can_handle_laboratory=True)
        if not id_is_static(indicator_config_id):
            # Save the start time now in case anything goes wrong. This way we'll be
            # able to see if the rebuild started a long time ago without finishing.
            config.meta.build.initiated = datetime.utcnow()
            config.meta.build.finished = False
            config.save()

        adapter.rebuild_table()
        iteratively_build_table(config)


@task(queue=UCR_CELERY_QUEUE, ignore_result=True)
def rebuild_indicators_in_place(indicator_config_id, initiated_by=None):
    config = _get_config_by_id(indicator_config_id)
    success = _('Your UCR table {} has finished rebuilding').format(config.table_id)
    failure = _('There was an error rebuilding Your UCR table {}.').format(config.table_id)
    send = toggles.SEND_UCR_REBUILD_INFO.enabled(initiated_by)
    with notify_someone(initiated_by, success_message=success, error_message=failure, send=send):
        adapter = get_indicator_adapter(config, can_handle_laboratory=True)
        if not id_is_static(indicator_config_id):
            config.meta.build.initiated_in_place = datetime.utcnow()
            config.meta.build.finished_in_place = False
            config.save()

        adapter.build_table()
        iteratively_build_table(config, in_place=True)


@task(queue=UCR_CELERY_QUEUE, ignore_result=True, acks_late=True)
def resume_building_indicators(indicator_config_id, initiated_by=None):
    config = _get_config_by_id(indicator_config_id)
    success = _('Your UCR table {} has finished rebuilding').format(config.table_id)
    failure = _('There was an error rebuilding Your UCR table {}.').format(config.table_id)
    send = toggles.SEND_UCR_REBUILD_INFO.enabled(initiated_by)
    with notify_someone(initiated_by, success_message=success, error_message=failure, send=send):
        resume_helper = DataSourceResumeHelper(config)

        relevant_ids = resume_helper.get_ids_to_resume_from()
        if len(relevant_ids) > 0:
            _build_indicators(config, get_document_store(config.domain, config.referenced_doc_type), relevant_ids,
                              resume_helper)
            last_id = relevant_ids[-1]
            iteratively_build_table(config, last_id, resume_helper)


def iteratively_build_table(config, last_id=None, resume_helper=None, in_place=False):
    resume_helper = resume_helper or DataSourceResumeHelper(config)
    indicator_config_id = config._id

    relevant_ids = []
    document_store = get_document_store(config.domain, config.referenced_doc_type)
    for relevant_id in document_store.iter_document_ids(last_id):
        relevant_ids.append(relevant_id)
        if len(relevant_ids) >= ID_CHUNK_SIZE:
            resume_helper.set_ids_to_resume_from(relevant_ids)
            _build_indicators(config, document_store, relevant_ids, resume_helper)
            relevant_ids = []

    if relevant_ids:
        resume_helper.set_ids_to_resume_from(relevant_ids)
        _build_indicators(config, document_store, relevant_ids, resume_helper)

    if not id_is_static(indicator_config_id):
        resume_helper.clear_ids()
        if in_place:
            config.meta.build.finished_in_place = True
        else:
            config.meta.build.finished = True
        try:
            config.save()
        except ResourceConflict:
            current_config = DataSourceConfiguration.get(config._id)
            # check that a new build has not yet started
            if in_place:
                if config.meta.build.initiated_in_place == current_config.meta.build.initiated_in_place:
                    current_config.meta.build.finished_in_place = True
            else:
                if config.meta.build.initiated == current_config.meta.build.initiated:
                    current_config.meta.build.finished = True
            current_config.save()
        adapter = get_indicator_adapter(config, raise_errors=True, can_handle_laboratory=True)
        adapter.after_table_build()


@task(queue=UCR_CELERY_QUEUE)
def compare_ucr_dbs(domain, report_config_id, filter_values, sort_column, sort_order, params):
    from corehq.apps.userreports.laboratory.experiment import UCRExperiment

    def _run_report(backend_to_use):
        data_source = ReportFactory.from_spec(spec, include_prefilters=True, backend=backend_to_use)
        data_source.set_filter_values(filter_values)
        if sort_column:
            data_source.set_order_by(
                [(data_source.top_level_columns[int(sort_column)].column_id, sort_order.upper())]
            )

        datatables_params = DatatablesParams.from_request_dict(params)
        page = list(data_source.get_data(start=datatables_params.start, limit=datatables_params.count))
        total_records = data_source.get_total_records()
        json_response = {
            'aaData': page,
            "iTotalRecords": total_records,
        }
        total_row = data_source.get_total_row() if data_source.has_total_row else None
        if total_row is not None:
            json_response["total_row"] = total_row
        return json_response

    spec = get_document_or_not_found(ReportConfiguration, domain, report_config_id)
    experiment_context = {
        "domain": domain,
        "report_config_id": report_config_id,
        "filter_values": filter_values,
    }
    experiment = UCRExperiment(name="UCR DB Experiment", context=experiment_context)
    with experiment.control() as c:
        c.record(_run_report(UCR_SQL_BACKEND))

    with experiment.candidate() as c:
        c.record(_run_report(UCR_ES_BACKEND))

    objects = experiment.run()
    return objects


@periodic_task(
    run_every=ASYNC_INDICATOR_QUEUE_TIME,
    queue=settings.CELERY_PERIODIC_QUEUE,
)
def queue_async_indicators():
    start = datetime.utcnow()
    cutoff = start + ASYNC_INDICATOR_QUEUE_TIME
    time_for_crit_section = ASYNC_INDICATOR_QUEUE_TIME.seconds - 10

    oldest_indicator = AsyncIndicator.objects.order_by('date_queued').first()
    if oldest_indicator and oldest_indicator.date_queued:
        lag = (datetime.utcnow() - oldest_indicator.date_queued).total_seconds()
        datadog_gauge('commcare.async_indicator.oldest_queued_indicator', lag)

    with CriticalSection(['queue-async-indicators'], timeout=time_for_crit_section):
        redis_client = get_redis_client().client.get_client()
        indicators = AsyncIndicator.objects.all()[:10000]
        indicators_by_domain_doc_type = defaultdict(list)
        for indicator in indicators:
            indicators_by_domain_doc_type[(indicator.domain, indicator.doc_type)].append(indicator)

        for k, indicators in indicators_by_domain_doc_type.items():
            now = datetime.utcnow()
            if now > cutoff:
                break
            for indicator in indicators:
                _queue_indicator(redis_client, indicator)


def _queue_indicator(redis_client, indicator):
    lock_key = _get_indicator_queued_lock_key([indicator])
    lock = redis_client.lock(lock_key, timeout=60 * 60 * 24)
    if not lock.acquire(blocking=False):
        return

    indicator.date_queued = datetime.utcnow()
    indicator.save()
    save_document.delay([indicator.doc_id])


def _get_indicator_queued_lock_key(indicators):
    indicator_doc_ids = [i.doc_id for i in indicators]
    key_hash = hashlib.md5(','.join(indicator_doc_ids)).hexdigest()[:5]
    return 'async_indicator_queued-{}'.format(key_hash)


@quickcache(['config_id'])
def _get_config(config_id):
    # performance optimization for save_document.  don't use elsewhere
    return _get_config_by_id(config_id)


@task(queue=UCR_INDICATOR_CELERY_QUEUE, ignore_result=True, acks_late=True)
def save_document(doc_ids):
    lock_keys = []
    for doc_id in doc_ids:
        lock_keys.append(get_async_indicator_modify_lock_key(doc_id))

    with CriticalSection(lock_keys):
        indicators = AsyncIndicator.objects.filter(doc_id__in=doc_ids)
        first_indicator = indicators[0]
        doc_store = get_document_store(first_indicator.domain, first_indicator.doc_type)
        for doc in doc_store.iter_documents(doc_ids):
            eval_context = EvaluationContext(doc)
            indicator = next(i for i in indicators if doc['_id'] == i.doc_id)
            for config_id in indicator.indicator_config_ids:
                config = _get_config(config_id)
                adapter = get_indicator_adapter(config, can_handle_laboratory=True)
                adapter.best_effort_save(doc, eval_context)
                eval_context.reset_iteration()

            redis_client = get_redis_client().client.get_client()
            queued_lock_key = _get_indicator_queued_lock_key([indicator])
            lock = redis_client.lock(queued_lock_key)
            release_lock(lock, degrade_gracefully=True)
            indicator.delete()
