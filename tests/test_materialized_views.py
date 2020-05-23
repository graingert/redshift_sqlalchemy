import pytest

from sqlalchemy import Table, Integer, String, MetaData, Column, select
from sqlalchemy_redshift import ddl
from rs_sqla_test_utils.utils import clean, compile_query

@pytest.fixture
def selectable():
    table = Table('t1',
                  MetaData(),
                  Column('id', Integer, primary_key=True),
                  Column('name', String))
    return select([table.c.id, table.c.name], from_obj=table)


def test_basic_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    AS SELECT t1.id, t1.name FROM t1
    """
    view = ddl.CreateMaterializedView(
        "test_view",
        selectable
    )
    assert clean(expected_result) == clean(compile_query(view))


def test_no_backup_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    BACKUP NO
    AS SELECT t1.id, t1.name FROM t1
    """
    view = ddl.CreateMaterializedView(
        "test_view",
        selectable,
        backup=False
    )
    assert clean(expected_result) == clean(compile_query(view))


def test_diststyle_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    DISTSTYLE ALL
    AS SELECT t1.id, t1.name FROM t1
    """
    view = ddl.CreateMaterializedView(
        "test_view",
        selectable,
        diststyle='ALL'
    )
    assert clean(expected_result) == clean(compile_query(view))


def test_distkey_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    DISTKEY (id)
    AS SELECT t1.id, t1.name FROM t1
    """
    for key in ("id", selectable.c.id):
        view = ddl.CreateMaterializedView(
            "test_view",
            selectable,
            distkey=key
        )
        assert clean(expected_result) == clean(compile_query(view))


def test_sortkey_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    SORTKEY (id)
    AS SELECT t1.id, t1.name FROM t1
    """
    for key in ("id", selectable.c.id):
        view = ddl.CreateMaterializedView(
            "test_view",
            selectable,
            sortkey=key
        )
        assert clean(expected_result) == clean(compile_query(view))


def test_interleaved_sortkey_materialized_view(selectable):
    expected_result = """
    CREATE MATERIALIZED VIEW test_view
    INTERLEAVED SORTKEY (id)
    AS SELECT t1.id, t1.name FROM t1
    """
    for key in ("id", selectable.c.id):
        view = ddl.CreateMaterializedView(
            "test_view",
            selectable,
            interleaved_sortkey=key
        )
        assert clean(expected_result) == clean(compile_query(view))
