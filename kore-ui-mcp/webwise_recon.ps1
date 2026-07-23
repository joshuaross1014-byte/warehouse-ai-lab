# =============================================================================
#  WebWise server recon  --  READ ONLY  (one-time per WebWise web app server)
#  Confirms: the Access ODBC driver + bitness, the *Config DSNs and the .wdb
#  file each points at, the config folders, and that a config opens read-only.
#
#  Run ON the WebWise web app server, in 32-BIT PowerShell (the Access driver
#  is 32-bit):  C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
# =============================================================================
$ErrorActionPreference = 'SilentlyContinue'

"===== HOST ====="
"$env:COMPUTERNAME | PS $($PSVersionTable.PSVersion) | $([IntPtr]::Size*8)-bit process"

"`n===== ACCESS ODBC DRIVERS ====="
Get-OdbcDriver | Where-Object Name -like '*Access*' | Select-Object Name, Platform | Format-Table -Auto

"`n===== 32-bit *Config DSNs  (name -> .wdb path) ====="
$dsns = Get-OdbcDsn -Platform 32-bit | Where-Object { $_.Name -like '*Config' }
if (-not $dsns) { "(no *Config DSNs under 32-bit; also try: Get-OdbcDsn -Platform 64-bit)" }
$dsns | ForEach-Object { "{0,-32} -> {1}" -f $_.Name, $_.Attribute['Dbq'] }

"`n===== .wdb files in those config folders ====="
$dsns | ForEach-Object { Split-Path $_.Attribute['Dbq'] } | Sort-Object -Unique | ForEach-Object {
  "---- $_ ----"
  Get-ChildItem $_ -Filter *.wdb |
    Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,2)}}, LastWriteTime |
    Format-Table -Auto
}

"`n===== READ-ONLY OPEN TEST ====="
$testDsn = ($dsns | Select-Object -First 1).Name
"testing DSN: $testDsn"
try {
  $cn = New-Object System.Data.Odbc.OdbcConnection "DSN=$testDsn;"
  $cn.Open()
  $t = $cn.GetSchema('Tables') | Where-Object TABLE_TYPE -eq 'TABLE' | Select-Object -Expand TABLE_NAME
  "OPENED ok  |  user tables: $($t.Count)"
  $cn.Close()
} catch { "OPEN FAILED: $($_.Exception.Message)" }
"`n===== END ====="
