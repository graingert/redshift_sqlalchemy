import pytest
import sqlalchemy

import sqlalchemy_redshift.dialect


def test_defined_types():
    # These types are the officially supported Redshift types as of 20191121
    # AWS Redshift Docs Reference:
    # https://docs.aws.amazon.com/redshift/latest/dg/c_Supported_data_types.html
    assert sqlalchemy_redshift.dialect.VARCHAR is sqlalchemy.sql.sqltypes.VARCHAR
    assert sqlalchemy_redshift.dialect.NullType is sqlalchemy.sql.sqltypes.NullType
    assert sqlalchemy_redshift.dialect.SMALLINT is sqlalchemy.sql.sqltypes.SMALLINT
    assert sqlalchemy_redshift.dialect.INTEGER is sqlalchemy.sql.sqltypes.INTEGER
    assert sqlalchemy_redshift.dialect.BIGINT is sqlalchemy.sql.sqltypes.BIGINT
    assert sqlalchemy_redshift.dialect.DECIMAL is sqlalchemy.sql.sqltypes.DECIMAL
    assert sqlalchemy_redshift.dialect.REAL is sqlalchemy.sql.sqltypes.REAL
    assert sqlalchemy_redshift.dialect.CHAR is sqlalchemy.sql.sqltypes.CHAR
    assert sqlalchemy_redshift.dialect.DATE is sqlalchemy.sql.sqltypes.DATE
    assert sqlalchemy_redshift.dialect.TIMESTAMP is sqlalchemy.sql.sqltypes.TIMESTAMP
    assert (
        sqlalchemy_redshift.dialect.DOUBLE_PRECISION
        is sqlalchemy.dialects.postgresql.DOUBLE_PRECISION
    )

    assert (
        sqlalchemy_redshift.dialect.TIMESTAMPTZ is not sqlalchemy.sql.sqltypes.TIMESTAMP
    )

    assert sqlalchemy_redshift.dialect.TIMETZ is not sqlalchemy.sql.sqltypes.TIME


custom_type_inheritance = [
    (sqlalchemy_redshift.dialect.TIMESTAMP, sqlalchemy.sql.sqltypes.TIMESTAMP),
    (sqlalchemy_redshift.dialect.TIMETZ, sqlalchemy.sql.sqltypes.TIME),
]


@pytest.mark.parametrize("custom_type, super_type", custom_type_inheritance)
def test_custom_types_extend_super_type(custom_type, super_type):
    custom_type_inst = custom_type()
    assert isinstance(custom_type_inst, super_type)


column_and_ddl = [
    (
        sqlalchemy_redshift.dialect.TIMESTAMPTZ,
        (
            "\nCREATE TABLE t1 ("
            "\n\tid INTEGER NOT NULL, "
            "\n\tname VARCHAR, "
            "\n\ttest_col TIMESTAMPTZ, "
            "\n\tPRIMARY KEY (id)\n)\n\n"
        ),
    ),
    (
        sqlalchemy_redshift.dialect.TIMETZ,
        (
            "\nCREATE TABLE t1 ("
            "\n\tid INTEGER NOT NULL, "
            "\n\tname VARCHAR, "
            "\n\ttest_col TIMETZ, "
            "\n\tPRIMARY KEY (id)\n)\n\n"
        ),
    ),
]


@pytest.mark.parametrize("custom_datatype, expected", column_and_ddl)
def test_custom_types_ddl_generation(custom_datatype, expected):
    compiler = sqlalchemy_redshift.dialect.RedshiftDDLCompiler(
        sqlalchemy_redshift.dialect.RedshiftDialect(), None
    )
    table = sqlalchemy.Table(
        "t1",
        sqlalchemy.MetaData(),
        sqlalchemy.Column("id", sqlalchemy.INTEGER, primary_key=True),
        sqlalchemy.Column("name", sqlalchemy.String),
        sqlalchemy.Column("test_col", custom_datatype),
    )

    create_table = sqlalchemy.schema.CreateTable(table)
    actual = compiler.process(create_table)
    assert expected == actual
