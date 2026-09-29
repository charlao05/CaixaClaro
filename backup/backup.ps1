#requires -Version 7.0
[CmdletBinding()]
param(
  [string]$BackupRoot = "D:\backups\caixaclaro",
  [string]$Image       = "caixaclaro-backup:1",
  [string]$Network     = "caixaclaro-prod_default",
  [string]$EnvFile     = "C:\Users\Charles\CaixaClaro\backend\.env"
)

$ErrorActionPreference = "Stop"

$secure = Read-Host -AsSecureString "Passphrase GPG do backup"
$bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try   { $Passphrase = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ([string]::IsNullOrWhiteSpace($Passphrase)) { throw "Passphrase vazia." }

$repo = "C:\Users\Charles\CaixaClaro"
$commit = (& git -C $repo rev-parse --short HEAD).Trim()
$dirty  = (& git -C $repo status --porcelain)
if ($dirty) { throw "Working tree sujo. Commit ou stash antes do backup." }

$daily   = Join-Path $BackupRoot "daily"
$weekly  = Join-Path $BackupRoot "weekly"
$monthly = Join-Path $BackupRoot "monthly"
$null = New-Item -ItemType Directory -Force -Path $daily, $weekly, $monthly

$ts   = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$name = "caixaclaro-$ts"

if (-not (Test-Path $EnvFile)) { throw "ENV_FILE nao encontrado: $EnvFile" }
if (-not (docker network inspect $Network 2>$null)) { throw "Rede Docker $Network nao existe." }
if (-not $env:POSTGRES_PASSWORD) { throw "POSTGRES_PASSWORD nao definida no shell." }

$passBytes = [Text.Encoding]::UTF8.GetBytes($Passphrase + "`n")
$Passphrase = $null

try {
  $passBytes | docker run --rm -i `
    --network $Network `
    --tmpfs "/work:size=512m,mode=0700" `
    -v "${EnvFile}:/secrets/.env:ro" `
    -v "${daily}:/out" `
    -e "BACKUP_NAME=$name" `
    -e "GIT_COMMIT=$commit" `
    -e "PGHOST=db" -e "PGPORT=5432" `
    -e "PGDATABASE=caixaclaro" -e "PGUSER=caixaclaro" `
    -e "PGPASSWORD=$env:POSTGRES_PASSWORD" `
    $Image

  if ($LASTEXITCODE -ne 0) { throw "Container de backup retornou $LASTEXITCODE" }
}
finally {
  [Array]::Clear($passBytes, 0, $passBytes.Length)
}

Push-Location $daily
try {
  $expected = (Get-Content "${name}.tar.gpg.sha256").Split()[0]
  $actual   = (Get-FileHash "${name}.tar.gpg" -Algorithm SHA256).Hash.ToLower()
  if ($expected -ne $actual) { throw "SHA256 nao confere no artefato em disco." }
} finally { Pop-Location }

Write-Host "PASS  $daily\${name}.tar.gpg"

function Rotate-Tier {
  param([string]$From, [string]$To, [int]$Keep)
  $files = Get-ChildItem $From -Filter "caixaclaro-*.tar.gpg" | Sort-Object Name
  while ($files.Count -gt $Keep) {
    $oldest = $files[0]
    if ($To) {
      Move-Item $oldest.FullName (Join-Path $To $oldest.Name) -Force
      Move-Item "$($oldest.FullName).sha256" (Join-Path $To "$($oldest.Name).sha256") -Force
    } else {
      Remove-Item $oldest.FullName, "$($oldest.FullName).sha256" -Force
    }
    $files = Get-ChildItem $From -Filter "caixaclaro-*.tar.gpg" | Sort-Object Name
  }
}

Rotate-Tier -From $daily   -To $weekly  -Keep 7
Rotate-Tier -From $weekly  -To $monthly -Keep 4
Rotate-Tier -From $monthly -To $null    -Keep 3

$log = Join-Path $BackupRoot "backup.log"
"$(Get-Date -Format o) PASS $name" | Add-Content $log
