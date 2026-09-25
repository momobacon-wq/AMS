-- AMS 備品庫存 D1 schema（npx wrangler d1 execute ams-stock --remote --file schema.sql；可重複執行）
CREATE TABLE IF NOT EXISTS items (
  pn         TEXT PRIMARY KEY,          -- 料號 CR…（唯一鍵）
  model      TEXT NOT NULL,             -- 完整型號碼
  brand      TEXT,
  spec       TEXT,                      -- 量程／規格
  loc        TEXT,                      -- 儲位
  qty        INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
  proto      TEXT,                      -- HART／FF
  family     TEXT,                      -- 系列鍵（3051CD、TMT82…）
  contract   TEXT,                      -- 合約簡稱
  cqty       INTEGER,                   -- 合約數量
  min_qty    INTEGER,                   -- 安全存量（NULL＝不提醒）
  note       TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ledger (     -- 出入庫紀錄（只附加）
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT NOT NULL,               -- ISO UTC
  emp_id   TEXT,
  emp_name TEXT,
  action   TEXT NOT NULL,               -- OUT / IN / STOCKTAKE / IMPORT
  pn       TEXT NOT NULL,
  delta    INTEGER,
  balance  INTEGER,
  kks      TEXT,                        -- 安裝位號
  note     TEXT,
  wo       TEXT,                        -- 工單／申請單號
  source   TEXT,                        -- ams-card / ams-stock
  txn_id   TEXT
);
CREATE INDEX IF NOT EXISTS ledger_pn  ON ledger (pn, id);
CREATE INDEX IF NOT EXISTS ledger_kks ON ledger (kks, id);
CREATE INDEX IF NOT EXISTS ledger_txn ON ledger (txn_id);
CREATE TABLE IF NOT EXISTS txns (       -- 冪等：同 txnId 重送不重扣
  txn_id TEXT PRIMARY KEY,
  ts     TEXT NOT NULL,
  emp_id TEXT
);
CREATE TABLE IF NOT EXISTS client_log ( -- 前端錯誤回報（docs/assets/report.js → action clientlog）
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT NOT NULL,               -- ISO UTC
  emp_id   TEXT,
  emp_name TEXT,
  site     TEXT,                        -- 站名（AMS 資料庫解析（20260912）…）
  kind     TEXT,                        -- error / unhandledrejection / resource / load
  msg      TEXT NOT NULL,
  stack    TEXT,
  path     TEXT,                        -- load：資料檔相對路徑
  page     TEXT,                        -- location.hash
  build    TEXT,                        -- 資料建置雜湊
  app      TEXT,                        -- 程式雜湊
  ua       TEXT
);
CREATE INDEX IF NOT EXISTS client_log_ts ON client_log (ts);
