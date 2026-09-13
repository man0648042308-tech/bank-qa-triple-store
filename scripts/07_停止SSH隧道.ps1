<#
.SYNOPSIS
只停止由06脚本登记的Day37 SSH隧道，不停止数据库容器或其他SSH会话。

.DESCRIPTION
脚本读取tmp/day37_ssh_tunnel.json中的PID，然后再次核验：
- 进程名必须是ssh.exe；
- 命令行必须包含四条Day37固定转发；
- 远端IP必须与状态文件一致。
任何一项不符都拒绝结束进程。

成功标记：DAY37_SSH_TUNNEL_STOP_PASS。
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_VmCommon.ps1"

$statusPath = Get-Day37TunnelStatusPath
if (-not (Test-Path -LiteralPath $statusPath -PathType Leaf)) {
    Write-Host "没有Day37隧道状态文件，视为已经停止。" -ForegroundColor Yellow
    Write-Host "DAY37_SSH_TUNNEL_ALREADY_STOPPED"
    return
}

$status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
$tunnelProcessId = [int]$status.process_id
$recordedVmIp = [string]$status.vm_ip
if ($tunnelProcessId -le 0 -or $recordedVmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    throw "隧道状态文件字段无效；为防止误杀进程，拒绝继续。"
}

$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $tunnelProcessId" -ErrorAction SilentlyContinue
if ($null -eq $processInfo) {
    # PID已不存在，只删除本项目自己的陈旧状态文件。
    Remove-Item -LiteralPath $statusPath -Force
    Write-Host "登记的隧道进程已经退出，已清理陈旧状态文件。" -ForegroundColor Yellow
    Write-Host "DAY37_SSH_TUNNEL_ALREADY_STOPPED"
    return
}

$commandLine = [string]$processInfo.CommandLine
$requiredParts = @(
    '127.0.0.1:19200:127.0.0.1:19200',
    '127.0.0.1:6380:127.0.0.1:6380',
    '127.0.0.1:7476:127.0.0.1:7476',
    '127.0.0.1:7689:127.0.0.1:7689',
    "root@$recordedVmIp"
)
if ($processInfo.Name -ne 'ssh.exe' -or
    ($requiredParts | Where-Object { -not $commandLine.Contains($_) })) {
    throw "PID $tunnelProcessId 不是经过验证的Day37 SSH隧道，拒绝停止。"
}

Stop-Process -Id $tunnelProcessId -Force -ErrorAction Stop
try {
    Wait-Process -Id $tunnelProcessId -Timeout 8 -ErrorAction SilentlyContinue
}
catch {
    # Windows PowerShell 5.1在进程已经退出时可能报告找不到PID，可安全忽略。
}
Remove-Item -LiteralPath $statusPath -Force

Write-Host "`nDAY37_SSH_TUNNEL_STOP_PASS" -ForegroundColor Green
Write-Host "只停止了PID=$tunnelProcessId；数据库容器和数据均保留。"
