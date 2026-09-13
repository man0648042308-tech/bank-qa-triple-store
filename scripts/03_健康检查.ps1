<#
.SYNOPSIS
验证三个 Day37 容器、VM loopback绑定、SSH隧道以及服务层响应。

.DESCRIPTION
容器“正在运行”不等于服务“可以使用”。本脚本分四层检查：
1. 所有权与容器健康状态；
2. 数据库端口只绑定VM的127.0.0.1，虚拟机IP不能直接访问；
3. Windows本机SSH隧道端口可达；
4. Elasticsearch HTTP、Redis PING、Neo4j HTTP 的真实协议响应。
#>

[CmdletBinding()]
param(
    [string]$VmIp,
    [int]$WaitSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

function Send-Day37RedisPing {
    <#
    使用 Redis 的 RESP 文本协议发送 PING。正常返回 +PONG。
    这样验证的是 Windows -> VM -> Docker -> Redis 的完整链路。
    #>
    param([Parameter(Mandatory = $true)][string]$ComputerName)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect($ComputerName, 6380)
        $stream = $client.GetStream()
        $stream.ReadTimeout = 3000
        $payload = [System.Text.Encoding]::ASCII.GetBytes("*1`r`n`$4`r`nPING`r`n")
        $stream.Write($payload, 0, $payload.Length)
        $buffer = New-Object byte[] 64
        $read = $stream.Read($buffer, 0, $buffer.Length)
        return [System.Text.Encoding]::ASCII.GetString($buffer, 0, $read).Trim()
    }
    finally {
        $client.Dispose()
    }
}

$resolvedIp = Find-Day37VmIp -VmIp $VmIp
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$lastStates = @{}

do {
    $allHealthy = $true
    foreach ($containerName in $script:Day37AllowedContainers) {
        $container = Assert-Day37ContainerOwned -VmIp $resolvedIp -ContainerName $containerName
        $status = [string]$container.State.Status
        $health = if ($null -ne $container.State.Health) {
            [string]$container.State.Health.Status
        }
        else {
            'no-healthcheck'
        }
        $lastStates[$containerName] = "$status/$health"
        if ($status -ne 'running' -or $health -ne 'healthy') {
            $allHealthy = $false
        }
    }
    if ($allHealthy) {
        break
    }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)

if (-not $allHealthy) {
    Write-Host "容器未在限定时间内全部健康：" -ForegroundColor Red
    $lastStates.GetEnumerator() | Sort-Object Name | Format-Table -AutoSize
    foreach ($containerName in $script:Day37AllowedContainers) {
        Write-Host "`n--- $containerName 最近 80 行日志 ---" -ForegroundColor Yellow
        Invoke-Day37Ssh -VmIp $resolvedIp -Command "docker logs --tail 80 '$containerName'"
    }
    throw "Day37 容器健康检查超时。"
}

# 逐项读取 Docker 端口绑定，硬性要求 HostIp 是 127.0.0.1。
$bindingContracts = @(
    @{ Container = 'day37-elasticsearch'; ContainerPort = '9200/tcp'; HostPort = '19200' },
    @{ Container = 'day37-redis'; ContainerPort = '6379/tcp'; HostPort = '6380' },
    @{ Container = 'day37-neo4j'; ContainerPort = '7474/tcp'; HostPort = '7476' },
    @{ Container = 'day37-neo4j'; ContainerPort = '7687/tcp'; HostPort = '7689' }
)
foreach ($contract in $bindingContracts) {
    $container = Assert-Day37ContainerOwned -VmIp $resolvedIp -ContainerName $contract.Container
    $property = $container.HostConfig.PortBindings.PSObject.Properties[$contract.ContainerPort]
    if ($null -eq $property) {
        throw "$($contract.Container) 缺少端口绑定 $($contract.ContainerPort)。"
    }
    $actual = @($property.Value) | Select-Object -First 1
    if ($actual.HostIp -ne '127.0.0.1' -or $actual.HostPort -ne $contract.HostPort) {
        throw "$($contract.Container) 端口未安全绑定到 127.0.0.1：$($actual.HostIp):$($actual.HostPort)"
    }
}

# 从VM内部确认四个loopback端口均在监听，并执行协议级检查。
foreach ($port in @(19200, 6380, 7476, 7689)) {
    if (-not (Test-Day37VmLoopbackPort -VmIp $resolvedIp -Port $port)) {
        throw "虚拟机 loopback 端口 127.0.0.1:$port 未监听。"
    }
}
$remoteEsRaw = @(Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    'curl -fsS http://127.0.0.1:19200/_cluster/health')
$remoteEsHealth = (($remoteEsRaw -join "`n") | ConvertFrom-Json)
$remoteRedisReply = ((Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    'docker exec day37-redis redis-cli ping') -join "`n").Trim()
$remoteNeo4jReply = ((Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    'curl -fsS http://127.0.0.1:7476 >/dev/null && printf DAY37_NEO4J_HTTP_OK') -join "`n").Trim()
if ($remoteEsHealth.status -notin @('yellow', 'green') -or
    $remoteRedisReply -ne 'PONG' -or
    $remoteNeo4jReply -ne 'DAY37_NEO4J_HTTP_OK') {
    throw "虚拟机loopback协议检查失败。"
}

# 安全硬门槛：通过VM的网卡IP直接连接这些数据库端口必须失败。
foreach ($port in @(19200, 6380, 7476, 7689)) {
    if (Test-Day37TcpPort -ComputerName $resolvedIp -Port $port -TimeoutMilliseconds 900) {
        throw "安全检查失败：$resolvedIp`:$port 可直接访问，端口不应暴露到VMnet。"
    }
}

# Windows只允许通过本机127.0.0.1上的SSH隧道访问。
foreach ($port in @(19200, 6380, 7476, 7689)) {
    if (-not (Test-Day37TcpPort -ComputerName '127.0.0.1' -Port $port -TimeoutMilliseconds 2000)) {
        throw "Windows SSH隧道端口 127.0.0.1:$port 不可用。请运行 06_启动SSH隧道.ps1。"
    }
}

$esHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:19200/_cluster/health' -TimeoutSec 10
if ($esHealth.status -notin @('yellow', 'green')) {
    throw "Elasticsearch 集群状态不可用：$($esHealth.status)"
}

$redisReply = Send-Day37RedisPing -ComputerName '127.0.0.1'
if ($redisReply -ne '+PONG') {
    throw "Redis PING 返回异常：$redisReply"
}

$neo4jHttp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:7476' -TimeoutSec 10
if ($neo4jHttp.StatusCode -ne 200) {
    throw "Neo4j HTTP 返回异常：$($neo4jHttp.StatusCode)"
}

Write-Host "`n=== Day37 真实健康结果 ===" -ForegroundColor Cyan
$lastStates.GetEnumerator() | Sort-Object Name | Format-Table Name, Value -AutoSize
$protocolRows = @(
    [PSCustomObject]@{ Layer = 'VM loopback'; Check = 'Elasticsearch'; Result = $remoteEsHealth.status },
    [PSCustomObject]@{ Layer = 'VM loopback'; Check = 'Redis'; Result = $remoteRedisReply },
    [PSCustomObject]@{ Layer = 'VM loopback'; Check = 'Neo4j HTTP'; Result = '200' },
    [PSCustomObject]@{ Layer = 'Windows SSH tunnel'; Check = 'Elasticsearch'; Result = $esHealth.status },
    [PSCustomObject]@{ Layer = 'Windows SSH tunnel'; Check = 'Redis'; Result = $redisReply },
    [PSCustomObject]@{ Layer = 'Windows SSH tunnel'; Check = 'Neo4j HTTP'; Result = $neo4jHttp.StatusCode }
)
$protocolRows | Format-Table -AutoSize

Write-Host "`nDAY37_HEALTH_PASS" -ForegroundColor Green
Write-Host "VM_IP=$resolvedIp"
