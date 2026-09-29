#requires -Version 7.0
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$Package,
  [string]$WorkRoot        = "C:\backups\caixaclaro-restore-fn",
  [string]$Image           = "caixaclaro-backup:1",
  [string]$ApiImage        = "caixaclaro-api:prod",
  [string]$Network         = "caixaclaro-restore-fn",
  [string]$DbContainer     = "caixaclaro-restore-fn-db",
  [string]$ApiContainer    = "caixaclaro-restore-fn-api",
  [string]$WorkerContainer = "caixaclaro-restore-fn-worker",
  [string]$VolumeName      = "caixaclaro-restore-fn-pgdata",
  [string]$DbName          = "caixaclaro",
  [string]$DbUser          = "caixaclaro",
  [int]   $ApiHostPort     = 18000
)

$ErrorActionPreference = "Stop"

function Teardown {
  docker rm -f $ApiContainer    2>$null | Out-Null
  docker rm -f $WorkerContainer 2>$null | Out-Null
  docker rm -f $DbContainer     2>$null | Out-Null
  docker volume rm $VolumeName  2>$null | Out-Null
  docker network rm $Network    2>$null | Out-Null
  Remove-Item $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
}
function Fail($m) { Write-Host "FAIL: $m" -ForegroundColor Red; Teardown; exit 1 }
function Ok($m)   { Write-Host "PASS: $m" -ForegroundColor Green }
function Info($m) { Write-Host "== $m ==" -ForegroundColor Cyan }

if (-not (Test-Path $Package)) { Fail "pacote nao encontrado: $Package" }

$secure = Read-Host -AsSecureString "Passphrase GPG"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try   { $pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ([string]::IsNullOrWhiteSpace($pass)) { Fail "passphrase vazia" }
$passBytes = [Text.Encoding]::UTF8.GetBytes($pass + "`n")
$pass = $null

Teardown
$null = New-Item -ItemType Directory -Force -Path $WorkRoot
$extractDir = Join-Path $WorkRoot "extracted"
$null = New-Item -ItemType Directory -Force -Path $extractDir

Info "Extraindo pacote"
$workPath  = (Resolve-Path $WorkRoot).Path
$pkgParent = Split-Path $Package -Parent
$pkgLeaf   = Split-Path $Package -Leaf
$passBytes | docker run --rm -i --entrypoint bash `
  -v "${workPath}:/work" `
  -v "${pkgParent}:/in:ro" `
  $Image -c "gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 -d /in/$pkgLeaf > /work/pkg.tar && tar -xf /work/pkg.tar -C /work/extracted && rm -f /work/pkg.tar"
if ($LASTEXITCODE -ne 0) { Fail "extracao falhou" }
[Array]::Clear($passBytes, 0, $passBytes.Length)
Ok "extracao"

$envPath  = Join-Path $extractDir "caixaclaro\env\.env"
$dumpPath = Join-Path $extractDir "caixaclaro\db.dump"
foreach ($p in @($envPath,$dumpPath)) { if (-not (Test-Path $p)) { Fail "ausente: $p" } }

$envMap = @{}
foreach ($l in (Get-Content $envPath | Where-Object { $_ -match '^[A-Z_][A-Z0-9_]*=' })) {
  $k,$v = $l -split '=', 2
  if ($v) { $envMap[$k] = $v }
}
foreach ($k in @("JWT_SECRET","CPF_HMAC_KEY","CPF_AES_KEY")) {
  if (-not $envMap.ContainsKey($k) -or [string]::IsNullOrWhiteSpace($envMap[$k])) {
    Fail "chave critica ausente/vazia no .env: $k"
  }
}
Ok ".env restaurado contem JWT_SECRET, CPF_HMAC_KEY, CPF_AES_KEY"

Info "Provisionando Postgres descartavel"
docker network create $Network 2>$null | Out-Null
docker volume  create $VolumeName 2>$null | Out-Null
docker rm -f $DbContainer 2>$null | Out-Null

$restorePass = [Guid]::NewGuid().ToString("N")
docker run -d --name $DbContainer --network $Network `
  -e "POSTGRES_DB=$DbName" `
  -e "POSTGRES_USER=$DbUser" `
  -e "POSTGRES_PASSWORD=$restorePass" `
  -v "${VolumeName}:/var/lib/postgresql/data" `
  postgres:16 | Out-Null

$pgReady = $false
for ($i=0; $i -lt 30; $i++) {
  docker exec $DbContainer pg_isready -U $DbUser -d $DbName 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $pgReady = $true; break }
  Start-Sleep 1
}
if (-not $pgReady) { Fail "Postgres nao ficou pronto" }
Ok "Postgres pronto"

Info "Restaurando dump"
$dumpDir  = Split-Path $dumpPath -Parent
$dumpLeaf = Split-Path $dumpPath -Leaf
docker run --rm --entrypoint bash --network $Network `
  -e "PGPASSWORD=$restorePass" `
  -v "${dumpDir}:/dump:ro" `
  $Image -c "pg_restore --no-owner --no-acl -h $DbContainer -U $DbUser -d $DbName /dump/$dumpLeaf" 2>&1 |
  Where-Object { $_ -notmatch "warning" } | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { Fail "pg_restore falhou" }
Ok "pg_restore"

Info "Subindo API descartavel"
$restoreDbUrl = "postgresql://${DbUser}:${restorePass}@${DbContainer}:5432/${DbName}"
docker rm -f $ApiContainer 2>$null | Out-Null
docker run -d --name $ApiContainer --network $Network `
  --env-file $envPath `
  -e "DATABASE_URL=$restoreDbUrl" `
  -p "${ApiHostPort}:8000" `
  --entrypoint "" `
  $ApiImage uvicorn caixaclaro.main:app --host 0.0.0.0 --port 8000 | Out-Null

$apiReady = $false
for ($i=0; $i -lt 30; $i++) {
  Start-Sleep 1
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiHostPort/healthz" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $apiReady = $true; break }
  } catch {}
}
if (-not $apiReady) {
  docker logs $ApiContainer --tail 100 2>&1 | Write-Host
  Fail "API nao respondeu /healthz em 30s"
}
Ok "GET /healthz = 200"

Info "Register + Login"
$guid  = [Guid]::NewGuid().ToString("N").Substring(0,12)
$email = "restore-$guid@example.com"
$senha = "senha-$guid-1234"
$cpf   = "12345678901"

$regBody = @{ email=$email; senha=$senha; cpf=$cpf } | ConvertTo-Json
try {
  $reg = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiHostPort/api/v1/auth/register" `
    -ContentType "application/json" -Body $regBody
} catch {
  docker logs $ApiContainer --tail 100 2>&1 | Write-Host
  Fail "register falhou: $_"
}
if (-not $reg.token) { Fail "register sem token" }
Ok "POST /api/v1/auth/register = 201 + token"

$logBody = @{ email=$email; senha=$senha } | ConvertTo-Json
try {
  $log = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiHostPort/api/v1/auth/login" `
    -ContentType "application/json" -Body $logBody
} catch { Fail "login falhou: $_" }
if (-not $log.token) { Fail "login sem token" }
Ok "POST /api/v1/auth/login = 200 + token"

Info "Decifrando cpf_cifrado no ambiente restaurado"
docker cp .\backup\check-cpf.py "${ApiContainer}:/tmp/check-cpf.py"
if ($LASTEXITCODE -ne 0) { Fail "docker cp do check-cpf.py falhou" }
docker exec $ApiContainer python /tmp/check-cpf.py
if ($LASTEXITCODE -ne 0) { Fail "decifrar_cpf falhou" }
Ok "decifrar_cpf"

Info "Subindo worker descartavel"
docker rm -f $WorkerContainer 2>$null | Out-Null
docker run -d --name $WorkerContainer --network $Network `
  --env-file $envPath `
  -e "DATABASE_URL=$restoreDbUrl" `
  --entrypoint python `
  $ApiImage -m caixaclaro.workers | Out-Null

Start-Sleep 8
$state = docker inspect $WorkerContainer --format '{{.State.Status}}'
$wlog  = docker logs $WorkerContainer 2>&1
if ($state -ne "running") {
  $wlog | Write-Host
  Fail "worker nao esta rodando (state=$state)"
}
if ($wlog -match "Traceback|ERROR|CRITICAL") {
  $wlog | Write-Host
  Fail "worker logou erro no startup"
}
Ok "worker iniciou sem erro"

Teardown
Ok "RESTORE FUNCIONAL CONCLUIDO"
