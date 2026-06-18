# 项目启动日志

> 本文件记录 `求职分析智能体` 在本机 (Windows + Miniconda + PostgreSQL 17) 上的标准启动流程与踩坑记录,供后续直接复用。
> 适用环境:`D:\miniconda\envs\fastapi` (Python 3.10)、`D:\pgdata` (PG 数据目录)、项目根目录 `c:\Users\10408\Desktop\job`。

---

## 0. 前置检查(只跑一次,确认环境 OK)

```powershell
# conda 环境存在
Test-Path "D:\miniconda\envs\fastapi"

# PG 二进制与数据目录
Test-Path "D:\miniconda\envs\fastapi\Library\bin\postgres.exe"
Test-Path "D:\miniconda\envs\fastapi\Library\bin\pg_ctl.exe"
Test-Path "D:\miniconda\envs\fastapi\Library\bin\psql.exe"
Test-Path "D:\pgdata\PG_VERSION"            # 存在说明已 initdb
```

若 `D:\pgdata\PG_VERSION` 不存在,首次初始化:

```powershell
D:\miniconda\envs\fastapi\Library\bin\initdb.exe -D "D:\pgdata" -U postgres -E UTF8 --locale=C
```

---

## 1. 启动 PostgreSQL

> ⚠️ 踩坑:直接用 `Start-Process postgres.exe` 后进程会立即退出;PowerShell IDE 沙箱会拒绝删除 `D:\pgdata\postmaster.pid`(路径不在 allowlist);`Get-NetTCPConnection` 也查不到 5432 监听。**正确做法是用 `pg_ctl`,并通过 psql 真正验证连通性。**

```powershell
& "D:\miniconda\envs\fastapi\Library\bin\pg_ctl.exe" -D "D:/pgdata" -l "D:/pgdata/server.log" start
```

如果报 `lock file "postmaster.pid" already exists` 且**确认无 postgres 进程**:

```powershell
Get-Process postgres -ErrorAction SilentlyContinue
# 若为空,说明是 pid 残留,手动删除 (需管理员权限或绕过沙箱):
Remove-Item "D:\pgdata\postmaster.pid" -Force
```

验证连接(成功才会输出 PostgreSQL 版本):

```powershell
& "D:\miniconda\envs\fastapi\Library\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "SELECT version();"
```

---

## 2. 验证 / 创建用户和数据库

```powershell
& "D:\miniconda\envs\fastapi\Library\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "SELECT usename FROM pg_user WHERE usename='job';" -c "SELECT datname FROM pg_database WHERE datname='job_analyzer';"
```

不存在则创建(只需要跑一次):

```powershell
& "D:\miniconda\envs\fastapi\Library\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "CREATE USER job WITH PASSWORD 'job';" -c "CREATE DATABASE job_analyzer OWNER job;" -c "GRANT ALL PRIVILEGES ON DATABASE job_analyzer TO job;"
```

---

## 3. 执行 Alembic 迁移

> ⚠️ 踩坑:PowerShell 沙箱默认 GBK,直接跑 alembic 会 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94`。**必须先设置 UTF-8 环境变量**。
> ⚠️ 踩坑:沙箱禁止 `cmd /c`,不能用 `call activate.bat && alembic.exe`,要直接调绝对路径。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
& "D:\miniconda\envs\fastapi\Scripts\alembic.exe" upgrade head
```

输出 `Will assume transactional DDL.` 表示已是最新版本,无需再迁移。

---

## 4. 启动 FastAPI (uvicorn)

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Start-Process -FilePath "D:\miniconda\envs\fastapi\Scripts\uvicorn.exe" `
  -ArgumentList "app.main:app", "--reload", "--port", "8000" `
  -RedirectStandardOutput "uvicorn.out.log" `
  -RedirectStandardError "uvicorn.err.log" `
  -WorkingDirectory "c:\Users\10408\Desktop\job" `
  -NoNewWindow
```

日志落在 `c:\Users\10408\Desktop\job\uvicorn.out.log` 与 `uvicorn.err.log`。

---

## 5. 验证服务

```powershell
# 健康检查
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method GET
# 期望: data.status = "up"

# 服务元信息(确认 provider/model 正确)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/info" -Method GET
# 期望: data.provider = "deepseek", data.model = "deepseek-v4-flash", data.version = "0.2.0"
```

成功启动后可访问:

| 路径 | 用途 |
|---|---|
| http://127.0.0.1:8000/ | 着陆页 |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/api/v1/health | 健康检查 |
| http://127.0.0.1:8000/api/v1/info | 服务元信息 |
| http://127.0.0.1:8000/api/v1/analyze | 简历 ↔ JD 分析 (POST) |
| http://127.0.0.1:8000/app | 主分析页面 |
| http://127.0.0.1:8000/interview | 面试题预测页面 |

---

## 6. 停止服务

```powershell
# 停止 uvicorn
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force

# 停止 PostgreSQL
& "D:\miniconda\envs\fastapi\Library\bin\pg_ctl.exe" -D "D:/pgdata" stop
```

---

## 7. 一键启动脚本(可选)

把以下内容保存为 `start.ps1`,以后双击即可:

```powershell
# start.ps1 - 一键启动 PostgreSQL + FastAPI
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 1. PG
$pg = & "D:\miniconda\envs\fastapi\Library\bin\pg_ctl.exe" -D "D:/pgdata" -l "D:/pgdata/server.log" start 2>&1
Write-Host $pg

# 2. uvicorn
Set-Location "c:\Users\10408\Desktop\job"
Start-Process -FilePath "D:\miniconda\envs\fastapi\Scripts\uvicorn.exe" `
  -ArgumentList "app.main:app", "--reload", "--port", "8000" `
  -RedirectStandardOutput "uvicorn.out.log" `
  -RedirectStandardError "uvicorn.err.log" `
  -NoNewWindow

Start-Sleep -Seconds 5
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health"
```

---

## 8. 故障排查速查

| 症状 | 原因 | 处理 |
|---|---|---|
| `lock file "postmaster.pid" already exists` | 上次 PG 未正常退出,pid 残留 | 确认无 postgres 进程后删除 `D:\pgdata\postmaster.pid` |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94` | PowerShell 默认 GBK 读 alembic.ini / 项目源码 | 命令前设 `$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"` |
| `cmd /c` 命令被沙箱拦截 | Trae IDE 安全策略 | 不要 `cmd /c`,直接 `& "<env>\Scripts\xxx.exe"` |
| `Remove-Item ... not in allowlist` | 沙箱只允许删除指定白名单目录 | 文件移到 `c:\Users\10408\...` 等白名单路径,或开管理员终端 |
| `Get-NetTCPConnection` 查不到 5432 | PowerShell 输出编码 / 权限 | 改用 `netstat -ano \| Select-String ":5432"`,或直接用 psql 验证 |
| alembic 无输出即退出 | 已是最新版本 | 正常,无需处理 |
| uvicorn 启动后立即退出 | 缺依赖 / .env 配置缺失 | 查 `uvicorn.err.log` |