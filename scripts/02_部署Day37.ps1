<#
.SYNOPSIS
把本地 Compose/Cypher 文件复制到虚拟机，并只创建 Day37 隔离容器。

.DESCRIPTION
脚本会：
1. 实时确认 VM IP、SSH 和 Docker；
2. 拒绝覆盖不属于 Day37 的同名容器；
3. 要求固定RepoDigest的 Redis 7.4.10、Neo4j 5.26.28 已在本机缓存；
4. 只在缺失时拉取安全修订版本 Elasticsearch 8.18.0；
5. 创建 /opt/day37-bank-qa、Day37 网络/卷/容器；
6. 调用 03_健康检查.ps1。

明确不会执行：--remove-orphans、docker compose down、down -v、删除旧容器/卷/网络。
#>

[CmdletBinding()]
param(
    [string]$VmIp,
    [int]$HealthWaitSeconds = 240
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

$resolvedIp = Find-Day37VmIp -VmIp $VmIp
$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot 'infra\compose.vm.yml'
$initCypherPath = Join-Path $projectRoot 'cypher\01_init_day37_bank_graph.cypher'
$verifyCypherPath = Join-Path $projectRoot 'cypher\02_verify_day37_readonly.cypher'

# 同名容器存在时，必须先证明它属于本作业；否则立刻停止。
foreach ($containerName in $script:Day37AllowedContainers) {
    Assert-Day37ContainerOwnedOrAbsent -VmIp $resolvedIp -ContainerName $containerName
}

# 同名网络和数据卷也可能来自别的项目，必须在Compose运行前逐个检查标签。
Assert-Day37NamedResourceOwnedOrAbsent -VmIp $resolvedIp `
    -ResourceType network -ResourceName $script:Day37AllowedNetwork
foreach ($volumeName in $script:Day37AllowedVolumes) {
    Assert-Day37NamedResourceOwnedOrAbsent -VmIp $resolvedIp `
        -ResourceType volume -ResourceName $volumeName
}

# Redis/Neo4j使用现场核验过的精确RepoDigest；本脚本不会拉取浮动标签。
$pinnedCachedImages = @(
    'redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2',
    'neo4j:5@sha256:362542416de6c09a971484d1893878016cc3b5cdec166e54b1c824a220ecd6b9'
)
foreach ($cachedImage in $pinnedCachedImages) {
    if (-not (Test-Day37RemoteImage -VmIp $resolvedIp -ImageName $cachedImage)) {
        throw "虚拟机缺少已批准复用的镜像 $cachedImage；本脚本不会擅自拉取，请重新审批。"
    }
}

# 如果VM loopback端口被其他进程占用，且对应Day37容器还不存在，就拒绝部署。
$portOwners = @(
    @{ Port = 19200; Container = 'day37-elasticsearch' },
    @{ Port = 6380; Container = 'day37-redis' },
    @{ Port = 7476; Container = 'day37-neo4j' },
    @{ Port = 7689; Container = 'day37-neo4j' }
)
foreach ($entry in $portOwners) {
    $container = Get-Day37RemoteContainer -VmIp $resolvedIp -ContainerName $entry.Container
    if ($null -eq $container -and (Test-Day37VmLoopbackPort -VmIp $resolvedIp -Port $entry.Port)) {
        throw "端口 $($entry.Port) 已被非 Day37 进程占用，部署已停止。"
    }
}

# 远端路径是用户已批准的唯一写入范围。
Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "mkdir -p /opt/day37-bank-qa/infra /opt/day37-bank-qa/cypher"

Copy-Day37FileToVm -VmIp $resolvedIp -LocalPath $composePath `
    -RemotePath '/opt/day37-bank-qa/infra/compose.vm.yml'
Copy-Day37FileToVm -VmIp $resolvedIp -LocalPath $initCypherPath `
    -RemotePath '/opt/day37-bank-qa/cypher/01_init_day37_bank_graph.cypher'
Copy-Day37FileToVm -VmIp $resolvedIp -LocalPath $verifyCypherPath `
    -RemotePath '/opt/day37-bank-qa/cypher/02_verify_day37_readonly.cypher'

# `config --quiet` 只校验 YAML 和 Compose 合并结果，不创建容器。
Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "cd /opt/day37-bank-qa && docker compose -f infra/compose.vm.yml config --quiet"

$elasticsearchImage = 'docker.elastic.co/elasticsearch/elasticsearch:8.18.0'
if (-not (Test-Day37RemoteImage -VmIp $resolvedIp -ImageName $elasticsearchImage)) {
    Write-Host "Elasticsearch 8.18.0 镜像缺失，开始执行本次唯一允许的镜像拉取。" -ForegroundColor Yellow
    Invoke-Day37Ssh -VmIp $resolvedIp -Command "docker pull '$elasticsearchImage'"
}
else {
    Write-Host "Elasticsearch 镜像已缓存，不重复下载。" -ForegroundColor Green
}

# --pull never 确保 up 阶段不再下载其他镜像；没有使用 --remove-orphans。
Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "cd /opt/day37-bank-qa && docker compose -f infra/compose.vm.yml up -d --no-build --pull never"

# 创建后再次验证网络/卷确实带有Day37与Compose项目标签。
Assert-Day37NamedResourceOwned -VmIp $resolvedIp `
    -ResourceType network -ResourceName $script:Day37AllowedNetwork | Out-Null
foreach ($volumeName in $script:Day37AllowedVolumes) {
    Assert-Day37NamedResourceOwned -VmIp $resolvedIp `
        -ResourceType volume -ResourceName $volumeName | Out-Null
}

# 数据库仅监听VM loopback，所以先建立Windows本地SSH隧道，再执行完整健康检查。
& "$PSScriptRoot\06_启动SSH隧道.ps1" -VmIp $resolvedIp
& "$PSScriptRoot\03_健康检查.ps1" -VmIp $resolvedIp -WaitSeconds $HealthWaitSeconds

Write-Host "`nDAY37_DEPLOY_PASS" -ForegroundColor Green
Write-Host "VM_IP=$resolvedIp"
