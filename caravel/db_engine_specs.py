"""Compatibility layer for different database engines

This modules stores logic specific to different database engines. Things
like time-related functions that are similar but not identical, or
information as to expose certain features or not and how to expose them.

For instance, Hive/Presto supports partitions and have a specific API to
list partitions. Other databases like Vertica also support partitions but
have different API to get to them. Other databases don't support partitions
at all. The classes here will use a common interface to specify all this.

The general idea is to use static classes and an inheritance scheme.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import inspect
from collections import namedtuple
from flask_babel import lazy_gettext as _

Grain = namedtuple('Grain', 'name label function')


class BaseEngineSpec(object):
    engine = 'base'  # str as defined in sqlalchemy.engine.engine
    time_grains = tuple()

    @classmethod
    def epoch_to_dttm(cls):
        raise NotImplementedError()

    @classmethod
    def epoch_ms_to_dttm(cls):
        return cls.epoch_to_dttm().replace('{col}', '({col}/1000.0)')

    @classmethod
    def extra_table_metadata(cls, table):
        """Returns engine-specific table metadata"""
        return {}

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        return "'{}'".format(dttm.strftime('%Y-%m-%d %H:%M:%S'))


class PostgresEngineSpec(BaseEngineSpec):
    engine = 'postgres'

    time_grains = (
        Grain("Time Column", _('Time Column'), "{col}"),
        Grain("second", _('second'), "DATE_TRUNC('second', {col})"),
        Grain("minute", _('minute'), "DATE_TRUNC('minute', {col})"),
        Grain("hour", _('hour'), "DATE_TRUNC('hour', {col})"),
        Grain("day", _('day'), "DATE_TRUNC('day', {col})"),
        Grain("week", _('week'), "DATE_TRUNC('week', {col})"),
        Grain("month", _('month'), "DATE_TRUNC('month', {col})"),
        Grain("quarter", _('quarter'), "DATE_TRUNC('quarter', {col})"),
        Grain("year", _('year'), "DATE_TRUNC('year', {col})"),
    )

    @classmethod
    def epoch_to_dttm(cls):
        return "(timestamp 'epoch' + {col} * interval '1 second')"

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        return "'{}'".format(dttm.strftime('%Y-%m-%d %H:%M:%S'))


class SqliteEngineSpec(BaseEngineSpec):
    engine = 'sqlite'
    time_grains = (
        Grain('Time Column', _('Time Column'), '{col}'),
        Grain('day', _('day'), 'DATE({col})'),
        Grain("week", _('week'),
              "DATE({col}, -strftime('%w', {col}) || ' days')"),
        Grain("month", _('month'),
              "DATE({col}, -strftime('%d', {col}) || ' days')"),
    )

    @classmethod
    def epoch_to_dttm(cls):
        return "datetime({col}, 'unixepoch')"

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        iso = dttm.isoformat().replace('T', ' ')
        if '.' not in iso:
            iso += '.000000'
        return "'{}'".format(iso)


class MySQLEngineSpec(BaseEngineSpec):
    engine = 'mysql'
    time_grains = (
        Grain('Time Column', _('Time Column'), '{col}'),
        Grain("second", _('second'), "DATE_ADD(DATE({col}), "
              "INTERVAL (HOUR({col})*60*60 + MINUTE({col})*60"
              " + SECOND({col})) SECOND)"),
        Grain("minute", _('minute'), "DATE_ADD(DATE({col}), "
              "INTERVAL (HOUR({col})*60 + MINUTE({col})) MINUTE)"),
        Grain("hour", _('hour'), "DATE_ADD(DATE({col}), "
              "INTERVAL HOUR({col}) HOUR)"),
        Grain('day', _('day'), 'DATE({col})'),
        Grain("week", _('week'), "DATE(DATE_SUB({col}, "
              "INTERVAL DAYOFWEEK({col}) - 1 DAY))"),
        Grain("month", _('month'), "DATE(DATE_SUB({col}, "
              "INTERVAL DAYOFMONTH({col}) - 1 DAY))"),
    )
    @classmethod
    def convert_dttm(cls, target_type, dttm):
        if target_type.upper() in ('DATETIME', 'DATE'):
            return "STR_TO_DATE('{}', '%Y-%m-%d %H:%i:%s')".format(
                dttm.strftime('%Y-%m-%d %H:%M:%S'))
        return "'{}'".format(dttm.strftime('%Y-%m-%d %H:%M:%S'))

    @classmethod
    def epoch_to_dttm(cls):
        return "from_unixtime({col})"


class PrestoEngineSpec(BaseEngineSpec):
    engine = 'presto'

    time_grains = (
        Grain('Time Column', _('Time Column'), '{col}'),
        Grain('second', _('second'),
              "date_trunc('second', CAST({col} AS TIMESTAMP))"),
        Grain('minute', _('minute'),
              "date_trunc('minute', CAST({col} AS TIMESTAMP))"),
        Grain('hour', _('hour'),
              "date_trunc('hour', CAST({col} AS TIMESTAMP))"),
        Grain('day', _('day'),
              "date_trunc('day', CAST({col} AS TIMESTAMP))"),
        Grain('week', _('week'),
              "date_trunc('week', CAST({col} AS TIMESTAMP))"),
        Grain('month', _('month'),
              "date_trunc('month', CAST({col} AS TIMESTAMP))"),
        Grain('quarter', _('quarter'),
              "date_trunc('quarter', CAST({col} AS TIMESTAMP))"),
        Grain("week_ending_saturday", _('week_ending_saturday'),
              "date_add('day', 5, date_trunc('week', date_add('day', 1, "
              "CAST({col} AS TIMESTAMP))))"),
        Grain("week_start_sunday", _('week_start_sunday'),
              "date_add('day', -1, date_trunc('week', "
              "date_add('day', 1, CAST({col} AS TIMESTAMP))))"),
    )

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        if target_type.upper() in ('DATE', 'DATETIME'):
            return "from_iso8601_date('{}')".format(dttm.isoformat())
        return "'{}'".format(dttm.strftime('%Y-%m-%d %H:%M:%S'))

    @classmethod
    def epoch_to_dttm(cls):
        return "from_unixtime({col})"


class MssqlEngineSpec(BaseEngineSpec):
    engine = 'mssql'
    epoch_to_dttm = "dateadd(S, {col}, '1970-01-01')"

    time_grains = (
        Grain("Time Column", _('Time Column'), "{col}"),
        Grain("second", _('second'), "DATEADD(second, "
              "DATEDIFF(second, '2000-01-01', {col}), '2000-01-01')"),
        Grain("minute", _('minute'), "DATEADD(minute, "
              "DATEDIFF(minute, 0, {col}), 0)"),
        Grain("5 minute", _('5 minute'), "DATEADD(minute, "
              "DATEDIFF(minute, 0, {col}) / 5 * 5, 0)"),
        Grain("half hour", _('half hour'), "DATEADD(minute, "
              "DATEDIFF(minute, 0, {col}) / 30 * 30, 0)"),
        Grain("hour", _('hour'), "DATEADD(hour, "
              "DATEDIFF(hour, 0, {col}), 0)"),
        Grain("day", _('day'), "DATEADD(day, "
              "DATEDIFF(day, 0, {col}), 0)"),
        Grain("week", _('week'), "DATEADD(week, "
              "DATEDIFF(week, 0, {col}), 0)"),
        Grain("month", _('month'), "DATEADD(month, "
              "DATEDIFF(month, 0, {col}), 0)"),
        Grain("quarter", _('quarter'), "DATEADD(quarter, "
              "DATEDIFF(quarter, 0, {col}), 0)"),
        Grain("year", _('year'), "DATEADD(year, "
              "DATEDIFF(year, 0, {col}), 0)"),
    )

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        return "CONVERT(DATETIME, '{}', 126)".format(iso)


class RedshiftEngineSpec(PostgresEngineSpec):
    engine = 'redshift'


class OracleEngineSpec(PostgresEngineSpec):
    engine = 'oracle'

    @classmethod
    def convert_dttm(cls, target_type, dttm):
        return (
            """TO_TIMESTAMP('{}', 'YYYY-MM-DD"T"HH24:MI:SS.ff6')"""
        ).format(dttm.isoformat())


class VerticaEngineSpec(PostgresEngineSpec):
    engine = 'vertica'

engines = {
    o.engine: o for o in globals().values()
    if inspect.isclass(o) and issubclass(o, BaseEngineSpec)}
