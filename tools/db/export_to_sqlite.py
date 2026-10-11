#!/usr/bin/env python3
"""Runs inside WSL (called by tools/db/restore.sh). Dumps every user table of AmsDb (SQL Server) into one SQLite file,
plus a _schema table (table/column/type/rowcount) and _views/_procs source text.
Usage: python3 export_to_sqlite.py <out.sqlite>   (sa password: env MSSQL_SA_PASSWORD or /root/.ams_sa_pw; database: env AMS_MSSQL_DB, default AmsDb)
"""
import pyodbc, sqlite3, sys, os, decimal, datetime, uuid, json, time

OUT = sys.argv[1]
SA_PW = os.environ.get('MSSQL_SA_PASSWORD') or open('/root/.ams_sa_pw').read().strip()
DBNAME = os.environ.get('AMS_MSSQL_DB', 'AmsDb')
cn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=' + DBNAME + ';'
    f'UID=sa;PWD={SA_PW};TrustServerCertificate=yes', autocommit=True)
cur = cn.cursor()

if os.path.exists(OUT):
    os.remove(OUT)
lite = sqlite3.connect(OUT)
lite.execute('PRAGMA journal_mode=OFF'); lite.execute('PRAGMA synchronous=OFF')

def conv(v):
    if isinstance(v, decimal.Decimal): return float(v)
    if isinstance(v, (datetime.datetime, datetime.date)): return v.isoformat(sep=' ')
    if isinstance(v, datetime.time): return v.isoformat()
    if isinstance(v, uuid.UUID): return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)): return bytes(v)
    return v

# ---- schema inventory
cur.execute("""
SELECT s.name, t.name, c.column_id, c.name, ty.name, c.max_length, c.precision, c.scale, c.is_nullable, c.is_identity,
       ISNULL(pk.is_pk,0)
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
LEFT JOIN (SELECT ic.object_id, ic.column_id, 1 AS is_pk FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id WHERE i.is_primary_key=1) pk
  ON pk.object_id=c.object_id AND pk.column_id=c.column_id
ORDER BY s.name, t.name, c.column_id""")
schema_rows = [tuple(conv(v) for v in r) for r in cur.fetchall()]
lite.execute("""CREATE TABLE _schema(schema_name, table_name, column_id, column_name, data_type, max_length, precision, scale, is_nullable, is_identity, is_pk)""")
lite.executemany('INSERT INTO _schema VALUES (?,?,?,?,?,?,?,?,?,?,?)', schema_rows)

# row counts
cur.execute("""SELECT s.name, t.name, SUM(p.rows) FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) GROUP BY s.name, t.name ORDER BY 1,2""")
counts = cur.fetchall()
lite.execute('CREATE TABLE _tables(schema_name, table_name, row_count, exported_rows, seconds)')

# foreign keys
cur.execute("""SELECT fk.name, OBJECT_SCHEMA_NAME(fk.parent_object_id), OBJECT_NAME(fk.parent_object_id), COL_NAME(fkc.parent_object_id, fkc.parent_column_id),
  OBJECT_SCHEMA_NAME(fk.referenced_object_id), OBJECT_NAME(fk.referenced_object_id), COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id)
FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id""")
lite.execute('CREATE TABLE _foreign_keys(fk_name, parent_schema, parent_table, parent_column, ref_schema, ref_table, ref_column)')
lite.executemany('INSERT INTO _foreign_keys VALUES (?,?,?,?,?,?,?)', [tuple(r) for r in cur.fetchall()])

# views / procs / functions source
cur.execute("""SELECT o.type_desc, s.name, o.name, m.definition FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.sql_modules m ON m.object_id=o.object_id WHERE o.is_ms_shipped=0""")
lite.execute('CREATE TABLE _modules(type_desc, schema_name, object_name, definition)')
lite.executemany('INSERT INTO _modules VALUES (?,?,?,?)', [tuple(r) for r in cur.fetchall()])

# extended properties / db info
cur.execute("SELECT name, compatibility_level, collation_name, create_date FROM sys.databases WHERE name=?", DBNAME)
lite.execute('CREATE TABLE _dbinfo(name, compatibility_level, collation_name, create_date)')
lite.executemany('INSERT INTO _dbinfo VALUES (?,?,?,?)', [tuple(conv(v) for v in r) for r in cur.fetchall()])
lite.commit()

def q(name): return '"' + name.replace('"', '""') + '"'

total = 0
for sch, tbl, rows in counts:
    t0 = time.time()
    cols = [r for r in schema_rows if r[0] == sch and r[1] == tbl]
    lname = tbl if sch == 'dbo' else f'{sch}.{tbl}'
    colsql = ', '.join(q(c[3]) for c in cols)
    lite.execute(f'CREATE TABLE {q(lname)} ({colsql})')
    n = 0
    if rows and rows > 0:
        sel = ', '.join(
            (f'CONVERT(nvarchar(max), {q(c[3])}) AS {q(c[3])}' if c[4] in ('xml', 'hierarchyid', 'geometry', 'geography', 'sql_variant')
             else q(c[3])) for c in cols)
        cur.execute(f'SELECT {sel} FROM {q(sch)}.{q(tbl)}')
        ph = ','.join('?' * len(cols))
        while True:
            batch = cur.fetchmany(5000)
            if not batch: break
            lite.executemany(f'INSERT INTO {q(lname)} VALUES ({ph})', [tuple(conv(v) for v in r) for r in batch])
            n += len(batch)
    lite.execute('INSERT INTO _tables VALUES (?,?,?,?,?)', (sch, tbl, rows, n, round(time.time() - t0, 2)))
    lite.commit()
    total += n
    print(f'{sch}.{tbl}: {n}/{rows} rows', flush=True)
print('TOTAL rows', total)
lite.close()
print('EXPORT_DONE')
