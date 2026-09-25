#!/bin/bash
# tools/db/install.sh — 在 WSL Ubuntu 24.04 內安裝 SQL Server 2025 Express、sqlcmd、ODBC 與 pyodbc（每台機器只做一次）。
#   從 Windows：wsl -d Ubuntu-24.04 -u root bash /mnt/c/Users/<me>/AMS/tools/db/install.sh
#   sa 密碼：環境變數 MSSQL_SA_PASSWORD；沒設就沿用 /root/.ams_sa_pw，也沒有就隨機產生一組寫到 /root/.ams_sa_pw（0600，不進 repo）。
#   之後每拿到一份 .ams_bckup 跑 tools/db/restore.sh。
# 下一行是 CRLF 防呆：若被 core.autocrlf 轉成 CRLF，去掉 CR 後以 bash 重跑（整行必須以註解結尾）
if grep -q "$(printf '\r')" "$0" 2>/dev/null; then tr -d '\r' < "$0" | bash -s -- "$@"; exit $?; fi #
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
PW_FILE=/root/.ams_sa_pw

if [ -n "${MSSQL_SA_PASSWORD:-}" ]; then
  SA_PW="$MSSQL_SA_PASSWORD"
elif [ -s "$PW_FILE" ]; then
  SA_PW="$(cat "$PW_FILE")"
else
  # SQL Server 要求：≥8 字元且含大小寫、數字、符號
  SA_PW="Ams$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)!9"
  echo "產生 sa 密碼寫到 $PW_FILE（restore.sh 會讀）"
fi
umask 077; printf '%s\n' "$SA_PW" > "$PW_FILE"; umask 022

mkdir -p /usr/share/keyrings
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg
echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/mssql-server-2025 noble main" > /etc/apt/sources.list.d/mssql-server-2025.list
echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/prod noble main" > /etc/apt/sources.list.d/msprod.list
apt-get update -qq
apt-get install -y -qq mssql-server 2>&1 | tail -5
ACCEPT_EULA=Y apt-get install -y -qq mssql-tools18 msodbcsql18 unixodbc-dev python3-pyodbc 2>&1 | tail -3
if [ ! -f /var/opt/mssql/mssql.conf ] || ! grep -q '^\[sqlagent\]\|^\[network\]\|^\[filelocation\]' /var/opt/mssql/mssql.conf 2>/dev/null; then
  ACCEPT_EULA=Y MSSQL_PID=Express MSSQL_SA_PASSWORD="$SA_PW" /opt/mssql/bin/mssql-conf -n setup 2>&1 | tail -5
fi
systemctl enable mssql-server >/dev/null 2>&1 || true
systemctl restart mssql-server
sleep 15
systemctl status mssql-server --no-pager | head -5
/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PW" -C -Q "SELECT @@VERSION" -W | head -3
echo INSTALL_DONE
