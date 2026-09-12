#!/bin/bash
# Install SQL Server 2025 (Express edition) inside WSL Ubuntu 24.04 and restore AmsDb
set -x
export DEBIAN_FRONTEND=noninteractive
mkdir -p /usr/share/keyrings
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg
echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/mssql-server-2025 noble main" > /etc/apt/sources.list.d/mssql-server-2025.list
echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/prod noble main" > /etc/apt/sources.list.d/msprod.list
apt-get update -qq
apt-get install -y -qq mssql-server 2>&1 | tail -5
ACCEPT_EULA=Y apt-get install -y -qq mssql-tools18 unixodbc-dev 2>&1 | tail -3
SA_PW="$(cat /root/.ams_sa_pw)"
ACCEPT_EULA=Y MSSQL_PID=Express MSSQL_SA_PASSWORD="$SA_PW" /opt/mssql/bin/mssql-conf -n setup 2>&1 | tail -5
systemctl enable mssql-server >/dev/null 2>&1
systemctl restart mssql-server
sleep 15
systemctl status mssql-server --no-pager | head -5
mkdir -p /var/opt/mssql/backup
cp "/mnt/c/Users/bacon/我的雲端硬碟/@@新機組資料備份/AMS/20260912.ams_bckup" /var/opt/mssql/backup/AmsDb.bak
chown mssql:mssql /var/opt/mssql/backup/AmsDb.bak
ls -la /var/opt/mssql/backup/
SQ="/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $SA_PW -C"
$SQ -Q "RESTORE HEADERONLY FROM DISK='/var/opt/mssql/backup/AmsDb.bak'" -W -w 400 | head -8
$SQ -Q "RESTORE FILELISTONLY FROM DISK='/var/opt/mssql/backup/AmsDb.bak'" -W -w 300 | cut -c1-160
$SQ -Q "RESTORE DATABASE AmsDb FROM DISK='/var/opt/mssql/backup/AmsDb.bak' WITH MOVE 'AmsDb_dat' TO '/var/opt/mssql/data/AmsDb.mdf', MOVE 'AmsDb_log' TO '/var/opt/mssql/data/AmsDb.ldf', REPLACE, STATS=25"
$SQ -d AmsDb -Q "SELECT COUNT(*) AS tables FROM sys.tables; SELECT compatibility_level FROM sys.databases WHERE name='AmsDb'" -W
echo INSTALL_DONE
