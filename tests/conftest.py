import os
import copy
import contextlib
import itertools
import uuid
import functools
import time
from logging import getLogger

from rs_sqla_test_utils.db import EngineDefinition

try:
    from urllib import parse as urlparse
except ImportError:
    import urlparse

import requests
import pytest
import sqlalchemy as sa


from rs_sqla_test_utils import db
from rs_sqla_test_utils.utils import make_mock_engine

logger = getLogger(__name__)

_unicode = type(u'')


@pytest.fixture(scope="session")
def connection_kwargs(redshift_dialect_flavor):
    """ Connection parameters for running integration tests
    against an existing Redshift instance.

    The tests are currently designed to work with the Travis CI
    environment, where a Redshift instance is available
    in the cloud. Travis CI passes the PGPASSWORD environment
    variable and an API call to a Heroku app gets the rest
    of the credentials.

    This fixture allows the developer to pass in their own credentials
    for other Redshift instances by setting the following environment
    variables:

        - REDSHIFT_HOST
        - REDSHIFT_PORT
        - REDSHIFT_USERNAME
        - REDSHIFT_PASSWORD
        - REDSHIFT_DATABASE
        - PGPASSWORD

    If these conditions are met, the tests will be ran
    against a real Redshift instance. Otherwise, they
    will be ran against a mock engine.

    See the fixture, _redshift_database_tool, for usage.
    """
    pgpassword = os.environ.get('PGPASSWORD', None)
    if not pgpassword:
        pytest.skip('This test will only work on Travis.')

    return {
        "host": os.getenv("REDSHIFT_HOST", None),
        "port": os.getenv("REDSHIFT_PORT", None),
        "username": os.getenv("REDSHIFT_USERNAME", "travis"),
        "password": pgpassword,
        "database": os.getenv("REDSHIFT_DATABASE", "dev"),
        "dialect": redshift_dialect_flavor,
    }


@pytest.fixture(scope="session")
def aws_account_id():
    return os.getenv("AWS_ACCOUNT_ID", '000123456789')


@pytest.fixture(scope="session")
def iam_role_name():
    return os.getenv("REDSHIFT_IAM_ROLE_NAME", 'redshiftrole')


@pytest.fixture(scope="session")
def aws_partition():
    return os.getenv("AWS_PARTITION", 'aws-us-gov')


@pytest.fixture(scope="session")
def iam_role_arn(aws_account_id, iam_role_name):
    return os.getenv(
        "REDSHIFT_IAM_ROLE_ARN",
        f'arn:aws:iam::{aws_account_id}:role/{iam_role_name}'
    )


@pytest.fixture(scope="session")
def iam_role_arn_with_aws_partition(
    aws_account_id,
    aws_partition,
    iam_role_name
):
    return os.getenv(
        "REDSHIFT_IAM_ROLE_ARN_WITH_AWS_PARTITION",
        f'arn:{aws_partition}:iam::{aws_account_id}:role/{iam_role_name}'
    )


@pytest.fixture(scope="session")
def iam_role_arns():
    default_arns_as_string = (
        'arn:aws:iam::000123456789:role/redshiftrole,'
        'arn:aws:iam::000123456789:role/redshiftrole2'
    )
    arns = os.getenv('REDSHIFT_IAM_ROLE_ARNS', default_arns_as_string)
    return arns.split(',')


def database_name_generator():
    template = 'testdb_{uuid}_{count}'
    db_uuid = _unicode(uuid.uuid1()).replace('-', '')
    for i in itertools.count():
        yield template.format(
            uuid=db_uuid,
            count=i,
        )


database_name = functools.partial(next, database_name_generator())


class DatabaseTool(object):
    """
    Abstracts the creation and destruction of migrated databases.
    """

    def __init__(self, engine_definition: EngineDefinition):
        self.engine = engine_definition.engine()

    def migrate(self, engine):
        from rs_sqla_test_utils import models
        models.Base.metadata.create_all(bind=engine)

    @contextlib.contextmanager
    def _database(self):
        from sqlalchemy_redshift.dialect import \
            RedshiftDialect_redshift_connector

        db_name = database_name()
        with self.engine.connect() as conn:
            conn.execute('COMMIT')  # Can't create databases in a transaction
            if isinstance(conn.dialect, RedshiftDialect_redshift_connector):
                conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute('CREATE DATABASE {db_name}'.format(db_name=db_name))

        dburl = copy.deepcopy(self.engine.url)
        try:
            dburl.database = db_name
        except AttributeError:
            dburl = dburl.set(database=db_name)

        try:
            yield db.EngineDefinition(
                db_connect_url=dburl,
                connect_args=self.engine_definition.connect_args,
            )
        finally:
            with self.engine.connect() as conn:
                conn.execute('COMMIT')  # Can't drop databases in a transaction
                if isinstance(
                        conn.dialect, RedshiftDialect_redshift_connector
                ):
                    conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute('DROP DATABASE {db_name}'.format(db_name=db_name))

    @contextlib.contextmanager
    def migrated_database(self):
        """
        Test fixture for testing real commits/rollbacks.

        Creates and migrates a fresh database for every test.
        """
        with self._database() as engine_definition:
            engine = engine_definition.engine()
            try:
                self.migrate(engine)
                yield {
                    'definition': engine_definition,
                    'engine': engine,
                }
            finally:
                engine.dispose()


def pytest_addoption(parser):
    """
    Pytest option to define which dbdrivers to run the test suite with.

    """
    parser.addoption("--dbdriver", action="append")


class DriverParameterizedTests:
    """
    Helper class for generating fixture params using pytest config opts.

    """
    DEFAULT_DRIVERS = ['psycopg2', 'psycopg2cffi']
    redshift_dialect_flavors = None

    @classmethod
    def set_drivers(cls,  _drivers):
        DriverParameterizedTests.redshift_dialect_flavors = [
            'redshift+{}'.format(x) for x in _drivers
        ]


def pytest_generate_tests(metafunc):

    if 'redshift_dialect_flavor' in metafunc.fixturenames:
        if DriverParameterizedTests.redshift_dialect_flavors is None:
            dbdrivers = metafunc.config.getoption(
                "--dbdriver", default=DriverParameterizedTests.DEFAULT_DRIVERS
            )
            DriverParameterizedTests.set_drivers(dbdrivers)

        metafunc.parametrize(
            'redshift_dialect_flavor',
            DriverParameterizedTests.redshift_dialect_flavors,
            ids=DriverParameterizedTests.redshift_dialect_flavors,
            scope="session")


@pytest.yield_fixture(scope='session')
def _redshift_database_tool(connection_kwargs):
    if all([x is not None for x in connection_kwargs.values()]):
        yield DatabaseTool(
            engine_definition=db.redshift_engine_definition(
                **connection_kwargs
            )
        )
        return

    session = requests.Session()
    while True:
        resp = session.post('https://bigcrunch.herokuapp.com/session/')
        if resp.status_code != 503:
            break
        logger.info('waiting for Redshift to boot up')
        time.sleep(15)

    resp.raise_for_status()

    config = resp.json()
    cluster = config['cluster']
    connection_kwargs.update({
        'port': cluster['Port'],
        'host': cluster['Address']
    })

    try:
        yield DatabaseTool(
            engine_definition=db.redshift_engine_definition(
                **connection_kwargs
            )
        )

    finally:
        base_url = resp.request.url
        resp = session.delete(
            urlparse.urljoin(base_url, config['resource_url'])
        )
        resp.raise_for_status()


@pytest.yield_fixture(scope='function')
def _redshift_engine_and_definition(_redshift_database_tool):
    with _redshift_database_tool.migrated_database() as database:
        yield database


@pytest.fixture(scope='function')
def redshift_engine(_redshift_engine_and_definition):
    """
    A redshift engine for a freshly migrated database.
    """
    return _redshift_engine_and_definition['engine']


@pytest.fixture(scope='function')
def redshift_engine_definition(_redshift_engine_and_definition):
    """
    A redshift engine definition for a freshly migrated database.
    """
    return _redshift_engine_and_definition['definition']


@pytest.yield_fixture(scope='session')
def _session_scoped_redshift_engine(_redshift_database_tool):
    """
    Private fixture to maintain a db for the entire test session.
    """
    with _redshift_database_tool.migrated_database() as egs:
        yield egs['engine']


@pytest.yield_fixture(scope='function')
def redshift_session(_session_scoped_redshift_engine):
    """
    A redshift session that rolls back all operations.

    The engine and db is maintained for the entire test session for efficiency.
    """
    conn = _session_scoped_redshift_engine.connect()
    tx = conn.begin()

    RedshiftSession = sa.orm.sessionmaker()
    session = RedshiftSession(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()


@pytest.fixture(scope='session')
def stub_redshift_engine(redshift_dialect_flavor):
    yield make_mock_engine(redshift_dialect_flavor)


@pytest.fixture(scope='session')
def stub_redshift_dialect(stub_redshift_engine):
    yield stub_redshift_engine.dialect
