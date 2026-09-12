import pyodbc, sqlite3, sys
SA_PW=open('/root/.ams_sa_pw').read().strip()
cn=pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=AmsDb;UID=sa;PWD='+SA_PW+';TrustServerCertificate=yes')
cur=cn.cursor()
lite=sqlite3.connect('/root/AmsDb.sqlite'); lite.execute('PRAGMA synchronous=OFF')
for tbl,keys in [('BlockData',['BlockKey','EventIdDay','EventIdFraction','ParamKind','ParamName']),('NamedConfigData',['ConfigKey','EventIdDay','EventIdFraction','ParamKind','ParamName'])]:
    cols=[r[0] for r in lite.execute(f'select column_name from _schema where table_name=? order by column_id',(tbl,))]
    lite.execute(f'drop table "{tbl}"')
    lite.execute(f'create table "{tbl}" ({", ".join(chr(34)+c+chr(34) for c in cols)})')
    sel=', '.join(('CAST(ParamData AS varbinary(max)) AS ParamData' if c=='ParamData' else f'[{c}]') for c in cols)
    cur.execute(f'SELECT {sel} FROM dbo.{tbl}')
    n=0
    while True:
        b=cur.fetchmany(10000)
        if not b: break
        lite.executemany(f'insert into "{tbl}" values ({",".join("?"*len(cols))})',[tuple(bytes(v) if isinstance(v,(bytearray,memoryview)) else v for v in r) for r in b]); n+=len(b)
    lite.commit(); print(tbl,n,flush=True)
for r in lite.execute('select ParamName, ParamDataType, ParamDataSize, hex(ParamData) from BlockData limit 6'): print(r)
lite.execute('create index if not exists ix_bd_block on BlockData(BlockKey)')
lite.execute('create index if not exists ix_bd_name on BlockData(ParamName)')
lite.execute('create index if not exists ix_ev_block on EventLog(BlockKey)')
lite.execute('create index if not exists ix_ncd_cfg on NamedConfigData(ConfigKey)')
lite.commit(); lite.execute('vacuum'); lite.close(); print('FIX_DONE')
