<#
.SYNOPSIS
把 Day37 银行图数据写入自己的 dataset_id='day37' 命名空间，并执行只读验收。

.DESCRIPTION
初始化文件只 MERGE Day37 专属标签和 dataset_id，不包含全库删除语句。
重复运行是幂等的：同一个客户/产品会被更新，不会无限重复创建。
#>

[CmdletBinding()]
param([string]$VmIp)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

$resolvedIp = Find-Day37VmIp -VmIp $VmIp
$neo4j = Assert-Day37ContainerOwned -VmIp $resolvedIp -ContainerName 'day37-neo4j'
if ($neo4j.State.Status -ne 'running' -or $neo4j.State.Health.Status -ne 'healthy') {
    throw "day37-neo4j 不是 healthy 状态，请先运行 03_健康检查.ps1。"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$initCypherPath = Join-Path $projectRoot 'cypher\01_init_day37_bank_graph.cypher'
$verifyCypherPath = Join-Path $projectRoot 'cypher\02_verify_day37_readonly.cypher'

# 每次初始化前重新复制，确保 VM 执行的是当前本地版本。
Copy-Day37FileToVm -VmIp $resolvedIp -LocalPath $initCypherPath `
    -RemotePath '/opt/day37-bank-qa/cypher/01_init_day37_bank_graph.cypher'
Copy-Day37FileToVm -VmIp $resolvedIp -LocalPath $verifyCypherPath `
    -RemotePath '/opt/day37-bank-qa/cypher/02_verify_day37_readonly.cypher'

Write-Host "开始执行 Day37 幂等初始化……" -ForegroundColor Cyan
Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "docker exec -i day37-neo4j cypher-shell -a bolt://localhost:7687 --format plain < /opt/day37-bank-qa/cypher/01_init_day37_bank_graph.cypher"

Write-Host "开始执行只读验收……" -ForegroundColor Cyan
$verifyOutput = @(Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "docker exec -i day37-neo4j cypher-shell -a bolt://localhost:7687 --format plain < /opt/day37-bank-qa/cypher/02_verify_day37_readonly.cypher")
$verifyOutput | ForEach-Object { Write-Host $_ }

if (($verifyOutput -join "`n") -notmatch 'PASS') {
    throw "Neo4j 只读验收没有返回 PASS。"
}

Write-Host "`nDAY37_NEO4J_INIT_PASS" -ForegroundColor Green
Write-Host "VM_IP=$resolvedIp"
