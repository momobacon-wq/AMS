#!/bin/bash
# tools/db/restore.sh — 把一份 .ams_bckup（SQL Server 2014 原生備份）還原進 WSL 的 SQL Server，逐表倒成 SQLite（每份新備份跑一次）。
#   sudo bash tools/db/restore.sh <備份檔.ams_bckup> <輸出 AmsDb.sqlite> [資料庫名，預設 AmsDb]
#   從 Windows（路徑用 /mnt/c/…）：
#     wsl -d Ubuntu-24.04 -u root bash /mnt/c/Users/<me>/AMS/tools/db/restore.sh \
#         "/mnt/c/Users/<me>/我的雲端硬碟/@@新機組資料備份/AMS/20260912.ams_bckup" /mnt/c/Users/<me>/AppData/Local/AMS/AmsDb.sqlite
#   sa 密碼：環境變數 MSSQL_SA_PASSWORD，否則 /root/.ams_sa_pw（install.sh 建立）。
#   輸出的 SQLite 就是 tools/db/paths.py 的 AMS_SQLITE（rebuild.py --sqlite 的輸入）；先寫在 WSL 本機磁碟再複製到目的地（/mnt/c 上寫 SQLite 很慢）。
#   注意：WSL 的 VM 在 wsl.exe 結束後會閒置關機，這支要當前景指令跑完（約 10 分鐘），不要丟到背景。
# 下一行是 CRLF 防呆：若被 core.autocrlf 轉成 CRLF，去掉 CR 後以 bash 重跑（整行必須以註解結尾）
if grep -q "$(printf '\r')" "$0" 2>/dev/null; then tr -d '\r' < "$0" | bash -s -- "$@"; exit $?; fi #
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BAK="${1:-}"; OUT="${2:-}"; DB="${3:-AmsDb}"
if [ -z "$BAK" ] || [ -z "$OUT" ]; then
  sed -n '2,9p' "$0"; exit 2
fi
[ -f "$BAK" ] || { echo "找不到備份檔：$BAK" >&2; exit 2; }
SA_PW="${MSSQL_SA_PASSWORD:-$(cat /root/.ams_sa_pw 2>/dev/null || true)}"
[ -n "$SA_PW" ] || { echo "沒有 sa 密碼：設 MSSQL_SA_PASSWORD 或先跑 tools/db/install.sh" >&2; exit 2; }
SQ=(/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PW" -C)
systemctl is-active --quiet mssql-server || systemctl start mssql-server

mkdir -p /var/opt/mssql/backup
BAKL="/var/opt/mssql/backup/$DB.bak"
echo "==> 複製備份到 $BAKL（$(du -h "$BAK" | cut -f1)）"
cp "$BAK" "$BAKL"; chown mssql:mssql "$BAKL"
"${SQ[@]}" -Q "RESTORE HEADERONLY FROM DISK='$BAKL'" -W -w 400 | head -6
# 邏輯檔名由備份本身讀出（不寫死 AmsDb_dat／AmsDb_log）：FILELISTONLY 第 1 欄 LogicalName、第 3 欄 Type（D 資料、L 記錄）
LIST="$("${SQ[@]}" -Q "SET NOCOUNT ON; RESTORE FILELISTONLY FROM DISK='$BAKL'" -W -s '|' -h -1)"
MOVES=""
n=0
while IFS='|' read -r lname _pname ltype _rest; do
  [ -z "$lname" ] && continue
  case "$ltype" in
    D) n=$((n+1)); MOVES="$MOVES, MOVE '$lname' TO '/var/opt/mssql/data/${DB}_$n.mdf'";;
    L) MOVES="$MOVES, MOVE '$lname' TO '/var/opt/mssql/data/${DB}_log.ldf'";;
  esac
done <<< "$LIST"
[ -n "$MOVES" ] || { echo "FILELISTONLY 讀不到邏輯檔名：" >&2; echo "$LIST" >&2; exit 1; }
echo "==> RESTORE DATABASE $DB${MOVES}"
"${SQ[@]}" -Q "RESTORE DATABASE [$DB] FROM DISK='$BAKL' WITH REPLACE, STATS=25${MOVES}"
"${SQ[@]}" -d "$DB" -Q "SELECT COUNT(*) AS tables FROM sys.tables; SELECT compatibility_level FROM sys.databases WHERE name='$DB'" -W

WORK=/var/tmp/ams_export; mkdir -p "$WORK"
TMP="$WORK/$DB.sqlite"
echo "==> 倒出 SQLite（export_to_sqlite.py → $TMP）"
MSSQL_SA_PASSWORD="$SA_PW" AMS_MSSQL_DB="$DB" python3 "$HERE/export_to_sqlite.py" "$TMP"
echo "==> 修正 varbinary 欄位與索引（fix_blobs.py）"
MSSQL_SA_PASSWORD="$SA_PW" AMS_MSSQL_DB="$DB" python3 "$HERE/fix_blobs.py" "$TMP"
mkdir -p "$(dirname "$OUT")"
cp "$TMP" "$OUT"
ls -la "$OUT"
echo "RESTORE_DONE $OUT"
