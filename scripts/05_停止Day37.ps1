<#
.SYNOPSIS
停止三个 Day37 容器，但保留容器、网络、数据卷和数据库数据。

.DESCRIPTION
这里故意使用 `docker compose stop`，而不是 `down` 或 `down -v`。
stop 只让进程停止，下次运行 02_部署Day37.ps1 可以继续使用原数据。
#>

[CmdletBinding()]
param([string]$VmIp)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

$resolvedIp = Find-Day37VmIp -VmIp $VmIp

# 停止前逐个验证标签，避免 Compose 文件或名字指向别人的容器。
foreach ($containerName in $script:Day37AllowedContainers) {
    Assert-Day37ContainerOwned -VmIp $resolvedIp -ContainerName $containerName | Out-Null
}

Invoke-Day37Ssh -VmIp $resolvedIp -Command `
    "cd /opt/day37-bank-qa && docker compose -f infra/compose.vm.yml stop"

Write-Host "`n=== 停止后的 Day37 容器状态 ===" -ForegroundColor Cyan
foreach ($containerName in $script:Day37AllowedContainers) {
    $container = Assert-Day37ContainerOwned -VmIp $resolvedIp -ContainerName $containerName
    [PSCustomObject]@{
        Container = $containerName
        Status = $container.State.Status
        DataPreserved = $true
    }
}

Write-Host "`nDAY37_STOP_PASS（只停止，未删除）" -ForegroundColor Green
