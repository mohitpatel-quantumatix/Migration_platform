from __future__ import annotations


POSTGRESQL_TO_MYSQL: dict[str, str] = {
    "integer": "INT",
    "bigint": "BIGINT",
    "smallint": "SMALLINT",
    "serial": "INT AUTO_INCREMENT",
    "bigserial": "BIGINT AUTO_INCREMENT",
    "real": "FLOAT",
    "double": "DOUBLE",
    "numeric": "DECIMAL",
    "boolean": "TINYINT(1)",
    "varchar": "VARCHAR",
    "text": "TEXT",
    "bytea": "BLOB",
    "timestamp": "DATETIME",
    "timestamptz": "DATETIME",
    "date": "DATE",
    "json": "JSON",
    "jsonb": "JSON",
    "uuid": "CHAR(36)",
    "inet": "VARCHAR(45)",
}

MYSQL_TO_POSTGRESQL: dict[str, str] = {
    "INT": "integer",
    "BIGINT": "bigint",
    "SMALLINT": "smallint",
    "FLOAT": "real",
    "DOUBLE": "double",
    "DECIMAL": "numeric",
    "TINYINT(1)": "boolean",
    "VARCHAR": "varchar",
    "TEXT": "text",
    "BLOB": "bytea",
    "DATETIME": "timestamp",
    "DATE": "date",
    "JSON": "jsonb",
    "CHAR": "varchar",
}

RELATIONAL_TO_MONGO: dict[str, str] = {
    "integer": "int32",
    "bigint": "int64",
    "smallint": "int32",
    "real": "double",
    "double": "double",
    "numeric": "decimal128",
    "boolean": "boolean",
    "varchar": "string",
    "text": "string",
    "bytea": "bin_data",
    "timestamp": "date",
    "timestamptz": "date",
    "date": "date",
    "json": "object",
    "jsonb": "object",
    "uuid": "string",
    "inet": "string",
}

MONGO_TO_RELATIONAL: dict[str, str] = {
    "int32": "integer",
    "int64": "bigint",
    "double": "double",
    "decimal128": "numeric",
    "boolean": "boolean",
    "string": "varchar",
    "bin_data": "bytea",
    "date": "timestamp",
    "object": "jsonb",
}

COSMOS_SIZE_LIMIT_MB = 2.0
MONGODB_SIZE_LIMIT_MB = 16.0


def map_type(
    source_engine: str, target_engine: str, source_type: str
) -> str | None:
    key = f"{source_engine}:{target_engine}:{source_type}"
    if key in _DIRECT_MAP:
        return _DIRECT_MAP[key]

    if source_engine in ("postgresql", "mysql", "mssql") and target_engine == "mongodb":
        return RELATIONAL_TO_MONGO.get(source_type)

    if source_engine == "mongodb" and target_engine in ("postgresql", "mysql", "mssql"):
        return MONGO_TO_RELATIONAL.get(source_type)

    return None


def check_size_limit(target_engine: str, size_bytes: int) -> bool:
    if target_engine == "cosmos_mongo":
        return size_bytes <= COSMOS_SIZE_LIMIT_MB * 1024 * 1024
    if target_engine == "mongodb":
        return size_bytes <= MONGODB_SIZE_LIMIT_MB * 1024 * 1024
    return True


_DIRECT_MAP: dict[str, str] = {
    "postgresql:mysql:integer": "INT",
    "postgresql:mysql:bigint": "BIGINT",
    "postgresql:mysql:smallint": "SMALLINT",
    "postgresql:mysql:real": "FLOAT",
    "postgresql:mysql:double": "DOUBLE",
    "postgresql:mysql:numeric": "DECIMAL",
    "postgresql:mysql:boolean": "TINYINT(1)",
    "postgresql:mysql:varchar": "VARCHAR",
    "postgresql:mysql:text": "TEXT",
    "postgresql:mysql:bytea": "BLOB",
    "postgresql:mysql:timestamp": "DATETIME",
    "postgresql:mysql:timestamptz": "DATETIME",
    "postgresql:mysql:date": "DATE",
    "postgresql:mysql:json": "JSON",
    "postgresql:mysql:jsonb": "JSON",
    "postgresql:mysql:uuid": "CHAR(36)",
    "postgresql:mysql:inet": "VARCHAR(45)",
    "mysql:postgresql:INT": "integer",
    "mysql:postgresql:BIGINT": "bigint",
    "mysql:postgresql:SMALLINT": "smallint",
    "mysql:postgresql:FLOAT": "real",
    "mysql:postgresql:DOUBLE": "double",
    "mysql:postgresql:DECIMAL": "numeric",
    "mysql:postgresql:TINYINT(1)": "boolean",
    "mysql:postgresql:VARCHAR": "varchar",
    "mysql:postgresql:TEXT": "text",
    "mysql:postgresql:BLOB": "bytea",
    "mysql:postgresql:DATETIME": "timestamp",
    "mysql:postgresql:DATE": "date",
    "mysql:postgresql:JSON": "jsonb",
    "mysql:postgresql:CHAR": "varchar",
    "mssql:postgresql:INT": "integer",
    "mssql:postgresql:BIGINT": "bigint",
    "mssql:postgresql:SMALLINT": "smallint",
    "mssql:postgresql:BIT": "boolean",
    "mssql:postgresql:VARCHAR": "varchar",
    "mssql:postgresql:TEXT": "text",
    "mssql:postgresql:NVARCHAR": "varchar",
    "mssql:postgresql:DATETIME": "timestamp",
    "mssql:postgresql:DATE": "date",
    "mssql:mysql:INT": "INT",
    "mssql:mysql:BIGINT": "BIGINT",
    "mssql:mysql:SMALLINT": "SMALLINT",
    "mssql:mysql:BIT": "TINYINT(1)",
    "mssql:mysql:VARCHAR": "VARCHAR",
    "mssql:mysql:TEXT": "TEXT",
    "mssql:mysql:DATETIME": "DATETIME",
    "mssql:mysql:DATE": "DATE",
    "postgresql:mongodb:integer": "int32",
    "postgresql:mongodb:bigint": "int64",
    "postgresql:mongodb:smallint": "int32",
    "postgresql:mongodb:real": "double",
    "postgresql:mongodb:double": "double",
    "postgresql:mongodb:numeric": "decimal128",
    "postgresql:mongodb:boolean": "boolean",
    "postgresql:mongodb:varchar": "string",
    "postgresql:mongodb:text": "string",
    "postgresql:mongodb:bytea": "bin_data",
    "postgresql:mongodb:timestamp": "date",
    "postgresql:mongodb:timestamptz": "date",
    "postgresql:mongodb:date": "date",
    "postgresql:mongodb:json": "object",
    "postgresql:mongodb:jsonb": "object",
    "postgresql:mongodb:uuid": "string",
    "postgresql:mongodb:inet": "string",
    "mysql:mongodb:INT": "int32",
    "mysql:mongodb:BIGINT": "int64",
    "mysql:mongodb:SMALLINT": "int32",
    "mysql:mongodb:FLOAT": "double",
    "mysql:mongodb:DOUBLE": "double",
    "mysql:mongodb:DECIMAL": "decimal128",
    "mysql:mongodb:TINYINT(1)": "boolean",
    "mysql:mongodb:VARCHAR": "string",
    "mysql:mongodb:TEXT": "string",
    "mysql:mongodb:BLOB": "bin_data",
    "mysql:mongodb:DATETIME": "date",
    "mysql:mongodb:DATE": "date",
    "mysql:mongodb:JSON": "object",
    "mssql:mongodb:INT": "int32",
    "mssql:mongodb:BIGINT": "int64",
    "mssql:mongodb:SMALLINT": "int32",
    "mssql:mongodb:BIT": "boolean",
    "mssql:mongodb:VARCHAR": "string",
    "mssql:mongodb:TEXT": "string",
    "mssql:mongodb:NVARCHAR": "string",
    "mssql:mongodb:DATETIME": "date",
    "mssql:mongodb:DATE": "date",
}