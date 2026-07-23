# =============================================================================
#  WebWise page inspector  --  READ ONLY
#  Dumps everything about ONE WebWise page (master, fields, picklists, SQL,
#  validations, links, buttons, nav, workflow) from a config .wdb, so a change
#  can be authored precisely and then applied in the WebWise Page Editor.
#
#  Run ON the WebWise web app server, in 32-BIT PowerShell:
#     C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
#  Set the two values from the Page Editor: the config (DSN) and the page id.
# =============================================================================
$Dsn    = 'ExampleConfig'   # the config selected in the Page Editor
$PageId = 1                 # the [ID n] shown on the page node

$cn = New-Object System.Data.Odbc.OdbcConnection "DSN=$Dsn;"
$cn.Open()
"CONFIG=$Dsn   PAGE=$PageId   ($([IntPtr]::Size*8)-bit)   opened=$($cn.State)"

function Q($sql){ $a=New-Object System.Data.Odbc.OdbcDataAdapter($sql,$cn); $d=New-Object System.Data.DataTable; try{[void]$a.Fill($d)}catch{ "   (query failed: $($_.Exception.Message))" }; ,$d }
function Show($d){
  foreach($row in $d.Rows){
    foreach($col in $d.Columns){ $v=$row[$col]; if($v -is [System.DBNull]){$v=''}; "{0} = {1}" -f $col.ColumnName,$v }
    '   ----'
  }
}

"`n########## t_web_page_master ##########"
Show (Q "SELECT * FROM t_web_page_master WHERE web_page_id=$PageId")

"`n########## t_web_menu (page links / menu) ##########"
Show (Q "SELECT * FROM t_web_menu")

# Every base table with a web_page_id column -> dump this page's rows
$pidTables = $cn.GetSchema('Columns') | Where-Object { $_.COLUMN_NAME -eq 'web_page_id' } |
  Select-Object -Expand TABLE_NAME | Sort-Object -Unique
foreach($t in $pidTables){
  if($t -eq 't_web_page_master'){ continue }
  $d = Q "SELECT * FROM [$t] WHERE web_page_id=$PageId"
  if($d.Rows.Count -gt 0){ "`n########## $t  ($($d.Rows.Count) row(s)) ##########"; Show $d }
}
$cn.Close()
"`n===== END ====="
# Access memo columns can truncate ~255 chars via ODBC; if a SQL block looks cut
# off, pull that single column on its own to get the full text.
