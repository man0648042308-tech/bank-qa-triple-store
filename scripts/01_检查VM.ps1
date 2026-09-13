<#
.SYNOPSIS
只读检查 VMware、SSH、Docker、旧容器和 Day37 所需镜像。

.EXAMPLE
在 PowerShell 中执行：
  Set-Location "./Day37_Bank_QA_Homework"
  powershell -ExecutionPolicy Bypass -File .\scripts\01_检查VM.ps1

成功标记：DAY37_VM_CHECK_PASS。
#>

[CmdletBinding()]
param([string]$VmIp)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

# 1. 实时发现并验证 IP。即使传入 -VmIp，也会再次验证 SSH 和 Docker。
$resolvedIp = Find-Day37VmIp -VmIp $VmIp

# 2. 这些远程命令全部是只读命令，不会启动旧容器。
Write-Host "`n=== 虚拟机与 Docker 版本 ===" -ForegroundColor Cyan
Invoke-Day37Ssh -VmIp $resolvedIp -Command "hostname; uname -m; docker version; docker compose version"

Write-Host "`n=== 当前全部容器（只读） ===" -ForegroundColor Cyan
Invoke-Day37Ssh -VmIp $resolvedIp -Command "docker ps -a"

Write-Host "`n=== Day37 镜像缓存情况（只读） ===" -ForegroundColor Cyan
$requiredImages = @(
    'redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2',
    'neo4j:5@sha256:362542416de6c09a971484d1893878016cc3b5cdec166e54b1c824a220ecd6b9',
    'docker.elastic.co/elasticsearch/elasticsearch:8.18.0'
)
$imageRows = foreach ($imageName in $requiredImages) {
    $exists = Test-Day37RemoteImage -VmIp $resolvedIp -ImageName $imageName
    [PSCustomObject]@{
        Image = $imageName
        Cached = $exists
    }
}
$imageRows | Format-Table -AutoSize

Write-Host "`n=== VM loopback上的Day37端口（只读） ===" -ForegroundColor Cyan
$ports = @(19200, 6380, 7476, 7689)
$portRows = foreach ($port in $ports) {
    [PSCustomObject]@{
        Port = $port
        VmLoopbackListening = Test-Day37VmLoopbackPort -VmIp $resolvedIp -Port $port
        DirectVmIpReachable = Test-Day37TcpPort -ComputerName $resolvedIp -Port $port -TimeoutMilliseconds 800
    }
}
$portRows | Format-Table -AutoSize

Write-Host "`nDAY37_VM_CHECK_PASS" -ForegroundColor Green
Write-Host "VM_IP=$resolvedIp"
