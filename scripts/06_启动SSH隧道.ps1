<#
.SYNOPSIS
在Windows建立四条本地SSH端口转发，使应用安全访问VM loopback数据库。

.DESCRIPTION
转发关系：
- Windows 127.0.0.1:19200 -> VM 127.0.0.1:19200 -> Elasticsearch 9200
- Windows 127.0.0.1:6380  -> VM 127.0.0.1:6380  -> Redis 6379
- Windows 127.0.0.1:7476  -> VM 127.0.0.1:7476  -> Neo4j HTTP 7474
- Windows 127.0.0.1:7689  -> VM 127.0.0.1:7689  -> Neo4j Bolt 7687

脚本使用现有SSH密钥，不读取、不询问、不保存密码。后台窗口使用Hidden模式。
PID和状态只写入项目tmp/day37_ssh_tunnel.json，不能放进提交ZIP。

成功标记：DAY37_SSH_TUNNEL_PASS。
#>

[CmdletBinding()]
param([string]$VmIp)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

function Test-Day37TunnelProcessContract {
    <#
    只有命令行同时包含四条固定转发和正确远端IP，才把某ssh.exe认作本项目隧道。
    #>
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedVmIp
    )

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo -or $processInfo.Name -ne 'ssh.exe') {
        return $false
    }
    $commandLine = [string]$processInfo.CommandLine
    $requiredParts = @(
        '127.0.0.1:19200:127.0.0.1:19200',
        '127.0.0.1:6380:127.0.0.1:6380',
        '127.0.0.1:7476:127.0.0.1:7476',
        '127.0.0.1:7689:127.0.0.1:7689',
        "root@$ExpectedVmIp"
    )
    foreach ($part in $requiredParts) {
        if (-not $commandLine.Contains($part)) {
            return $false
        }
    }
    return $true
}

$resolvedIp = Find-Day37VmIp -VmIp $VmIp
$statusPath = Get-Day37TunnelStatusPath
$tmpDirectory = Split-Path -Parent $statusPath
$localPorts = @(19200, 6380, 7476, 7689)

# 隧道启动前先从VM内部确认数据库确实已经监听，避免建立“能连本地端口、
# 但远端没有服务”的空隧道。
foreach ($port in $localPorts) {
    if (-not (Test-Day37VmLoopbackPort -VmIp $resolvedIp -Port $port)) {
        throw "VM loopback端口127.0.0.1:${port}尚未监听，请先运行02_部署Day37.ps1。"
    }
}

# 幂等处理：状态文件指向的进程和四个端口都正确时，不重复启动第二条隧道。
if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
    try {
        $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $recordedProcessId = [int]$status.process_id
        if ((Test-Day37TunnelProcessContract -ProcessId $recordedProcessId -ExpectedVmIp $resolvedIp) -and
            -not ($localPorts | Where-Object {
                -not (Test-Day37TcpPort -ComputerName '127.0.0.1' -Port $_ -TimeoutMilliseconds 700)
            })) {
            Write-Host "Day37 SSH隧道已经运行，不重复启动。" -ForegroundColor Green
            Write-Host "DAY37_SSH_TUNNEL_PASS"
            Write-Host "TUNNEL_PID=$recordedProcessId"
            return
        }
    }
    catch {
        # 状态文件损坏会进入下面的端口占用检查；不会据此停止任何未知进程。
        Write-Verbose "现有隧道状态文件无法验证，将按新启动流程检查。"
    }
}

# 若端口已被其他程序占用，绝不杀进程，也不覆盖它；只报告冲突并停止。
foreach ($port in $localPorts) {
    if (Test-Day37TcpPort -ComputerName '127.0.0.1' -Port $port -TimeoutMilliseconds 700) {
        throw "Windows本地端口127.0.0.1:${port}已被未知进程占用，拒绝建立隧道。"
    }
}

$sshPath = (Get-Command ssh.exe -ErrorAction Stop).Source
$sshArguments = @(
    '-N',
    '-T',
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-L', '127.0.0.1:19200:127.0.0.1:19200',
    '-L', '127.0.0.1:6380:127.0.0.1:6380',
    '-L', '127.0.0.1:7476:127.0.0.1:7476',
    '-L', '127.0.0.1:7689:127.0.0.1:7689',
    "root@$resolvedIp"
)

# Hidden符合后台辅助进程要求；-PassThru让脚本拿到唯一PID，便于安全停止。
$tunnelProcess = Start-Process -FilePath $sshPath -ArgumentList $sshArguments `
    -PassThru -WindowStyle Hidden

try {
    $deadline = (Get-Date).AddSeconds(12)
    do {
        Start-Sleep -Milliseconds 400
        $tunnelProcess.Refresh()
        if ($tunnelProcess.HasExited) {
            throw "ssh.exe在隧道建立前退出，退出码：$($tunnelProcess.ExitCode)"
        }
        $allPortsReady = -not ($localPorts | Where-Object {
            -not (Test-Day37TcpPort -ComputerName '127.0.0.1' -Port $_ -TimeoutMilliseconds 400)
        })
    } while (-not $allPortsReady -and (Get-Date) -lt $deadline)

    if (-not $allPortsReady) {
        throw "12秒内未能建立全部四条SSH端口转发。"
    }
    if (-not (Test-Day37TunnelProcessContract -ProcessId $tunnelProcess.Id -ExpectedVmIp $resolvedIp)) {
        throw "新ssh.exe进程的命令行不符合Day37固定隧道合同。"
    }
}
catch {
    # 这里只停止本脚本刚创建且PID明确的进程，不接触其他ssh会话。
    if (-not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}

if (-not (Test-Path -LiteralPath $tmpDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $tmpDirectory -Force | Out-Null
}
$statusRecord = [PSCustomObject]@{
    process_id = $tunnelProcess.Id
    vm_ip = $resolvedIp
    expected_vmx = $script:Day37ExpectedVmx
    started_at = (Get-Date).ToString('o')
    local_ports = $localPorts
}
$statusRecord | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statusPath -Encoding UTF8

Write-Host "`nDAY37_SSH_TUNNEL_PASS" -ForegroundColor Green
Write-Host "TUNNEL_PID=$($tunnelProcess.Id)"
Write-Host "ES=http://127.0.0.1:19200"
Write-Host "REDIS=redis://127.0.0.1:6380/0"
Write-Host "NEO4J_HTTP=http://127.0.0.1:7476"
Write-Host "NEO4J_BOLT=bolt://127.0.0.1:7689"
