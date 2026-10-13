<#
.SYNOPSIS
Day37 虚拟机脚本共用函数。

.DESCRIPTION
这不是需要单独运行的入口脚本，而是 01～05 脚本共享的“工具箱”。
它只做以下事情：发现正在运行的 VMware IP、验证 SSH/Docker、执行固定远程命令、
复制 Day37 文件，以及核验某个容器确实属于 Day37。

安全约束：
- SSH 强制 BatchMode，不弹出密码输入框，也不把密码写进项目。
- StrictHostKeyChecking=yes，不在后台悄悄接受新的主机指纹。
- 只允许三个固定容器名，防止变量写错后操作旧容器。
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Day37 允许管理的固定容器名。脚本收到其他名字会立即拒绝。
$script:Day37AllowedContainers = @(
    "day37-elasticsearch",
    "day37-redis",
    "day37-neo4j"
)
$script:Day37ExpectedVmx = '<你的VM目录>\AiLLM2603.vmx'
$script:Day37AllowedNetwork = 'day37-bank-qa-net'
$script:Day37AllowedVolumes = @(
    'day37_elasticsearch_data',
    'day37_redis_data',
    'day37_neo4j_data',
    'day37_neo4j_logs'
)

function Test-Day37TcpPort {
    <#
    用一个短超时 TCP 连接判断 IP:端口是否可达。
    返回 $true 或 $false，不修改远端状态。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ComputerName,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMilliseconds = 1200
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $asyncResult = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-Day37VmLoopbackPort {
    <#
    读取虚拟机 `ss -ltn` 的监听表，确认某端口只是在 VM 内部可见。
    与 Test-Day37TcpPort 不同，这个函数通过 SSH 从虚拟机内部观察 127.0.0.1。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $listenRows = @(Invoke-Day37Ssh -VmIp $VmIp -Command 'ss -ltn')
    $listenText = $listenRows -join "`n"
    return ($listenText -match "127\.0\.0\.1:$Port\b")
}

function Get-Day37TunnelStatusPath {
    <# 返回项目 tmp 中唯一的 SSH 隧道状态文件路径。 #>
    [CmdletBinding()]
    param()

    $projectRoot = Split-Path -Parent $PSScriptRoot
    return (Join-Path $projectRoot 'tmp\day37_ssh_tunnel.json')
}

function Assert-Day37GuestUuid {
    <#
    比较VMX的BIOS UUID与Linux的DMI UUID。前3段采用小端字节序，所以不能直接删空格比较。
    Guid(byte[])完成相同转换。身份不一致必须抛错，不能继续部署。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmxUuid,
        [Parameter(Mandatory = $true)][string]$GuestUuid
    )
    $hex = $VmxUuid -replace '[\s-]', ''
    if ($hex -notmatch '^[0-9a-fA-F]{32}$') {
        throw 'VMX BIOS UUID格式无效。'
    }
    [byte[]]$bytes = @(for ($offset = 0; $offset -lt 32; $offset += 2) {
        [Convert]::ToByte($hex.Substring($offset, 2), 16)
    })
    $expectedUuid = [Guid]::new($bytes)
    $actualUuid = [Guid]::Empty
    if (-not [Guid]::TryParse($GuestUuid.Trim(), [ref]$actualUuid) -or
        $actualUuid -ne $expectedUuid) {
        throw 'SSH来宾UUID与精确VMX不一致，拒绝继续。'
    }
}

function Get-Day37ExpectedVmxIp {
    <#
    只接受精确虚拟机文件 <你的VM目录>\AiLLM2603.vmx。
    不扫描其他VM，也不从ARP邻居表猜测身份，避免误连另一台有Docker的主机。
    #>
    [CmdletBinding()]
    param([string]$ExplicitVmIp)

    if (-not (Test-Path -LiteralPath $script:Day37ExpectedVmx -PathType Leaf)) {
        throw "指定的Day37虚拟机文件不存在：$script:Day37ExpectedVmx"
    }

    $vmrunCandidates = @(
        # 本机VMware实际安装位置（2026-08-31已只读核验）。
        "<VMware安装目录>\vmrun.exe",
        "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
        "C:\Program Files\VMware\VMware Workstation\vmrun.exe"
    )
    $vmrun = $vmrunCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

    if (-not $vmrun) {
        throw "找不到VMware vmrun.exe，无法验证精确VM身份。"
    }

    $runningVms = @(& $vmrun list 2>$null | Select-Object -Skip 1)
    $expectedIsRunning = $false
    foreach ($runningVmx in $runningVms) {
        if (-not [string]::IsNullOrWhiteSpace($runningVmx)) {
            $normalized = [System.IO.Path]::GetFullPath($runningVmx.Trim())
            if ([string]::Equals(
                $normalized,
                $script:Day37ExpectedVmx,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                $expectedIsRunning = $true
                break
            }
        }
    }
    if (-not $expectedIsRunning) {
        throw "精确虚拟机未运行：$script:Day37ExpectedVmx"
    }

    $guestIp = (& $vmrun getGuestIPAddress $script:Day37ExpectedVmx 2>$null | Select-Object -First 1)
    if ($guestIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        # Tools的宿主上报可能失效，但SSH仍然可用。只接受显式IP且再次核对UUID，
        # 不扫描网段、不猜测地址、不跳过SSH主机指纹，也不降低精确VM身份要求。
        if (-not $ExplicitVmIp) {
            throw 'VMware Tools未返回IPv4；可显式传入已知 -VmIp，脚本仍会核对精确VMX与来宾UUID。'
        }
        $parsedIp = $null
        if ($ExplicitVmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
            -not [System.Net.IPAddress]::TryParse($ExplicitVmIp, [ref]$parsedIp)) {
            throw '-VmIp 不是合法IPv4。'
        }
        $identityLines = @(Get-Content -LiteralPath $script:Day37ExpectedVmx |
            Where-Object { $_ -match '^uuid\.bios\s*=\s*"([^\"]+)"\s*$' })
        if ($identityLines.Count -ne 1 -or
            $identityLines[0] -notmatch '^uuid\.bios\s*=\s*"([^\"]+)"\s*$') {
            throw '无法唯一读取精确VMX的BIOS UUID。'
        }
        $vmxUuid = $Matches[1]
        $guestUuid = @(Invoke-Day37Ssh -VmIp $ExplicitVmIp -Command 'cat /sys/class/dmi/id/product_uuid')
        if ($guestUuid.Count -ne 1) {
            throw 'SSH未返回唯一的来宾UUID。'
        }
        Assert-Day37GuestUuid -VmxUuid $vmxUuid -GuestUuid ([string]$guestUuid[0])
        Write-Host 'VMware Tools上报不可用；精确VMX运行状态、SSH主机指纹和来宾UUID核验通过。'
        return $ExplicitVmIp
    }
    return $guestIp.Trim()
}

function Test-Day37SshDocker {
    <#
    候选 IP 必须同时满足：22 端口可达、现有 SSH 密钥认证成功、Docker Server 可用。
    这一步只运行 docker info，不创建或启动任何容器。
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$VmIp)

    if (-not (Test-Day37TcpPort -ComputerName $VmIp -Port 22)) {
        return $false
    }

    $sshArgs = @(
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=5',
        "root@$VmIp",
        'docker info >/dev/null 2>&1 && printf DAY37_SSH_DOCKER_OK'
    )
    $result = @(& ssh.exe @sshArgs 2>$null)
    return ($LASTEXITCODE -eq 0 -and (($result -join "`n") -match 'DAY37_SSH_DOCKER_OK'))
}

function Find-Day37VmIp {
    <#
    返回已经通过 SSH + Docker 验证的实时虚拟机 IP。
    `-VmIp` 必须与Tools实时IP相同，或在Tools上报失败时通过精确VMX UUID核验。
    显式IP失败立即停止，不扫描或改连其他主机。
    #>
    [CmdletBinding()]
    param([string]$VmIp)

    $parsedIp = $null
    if ($VmIp -and ($VmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
        -not [System.Net.IPAddress]::TryParse($VmIp, [ref]$parsedIp))) {
        throw '-VmIp 不是合法IPv4地址。'
    }
    $expectedIp = Get-Day37ExpectedVmxIp -ExplicitVmIp $VmIp
    if ($VmIp) {
        if ($VmIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
            throw "-VmIp 不是合法 IPv4 地址：$VmIp"
        }
        if ($VmIp -ne $expectedIp) {
            throw "显式IP $VmIp 与精确VMX实时IP $expectedIp 不一致，拒绝回退或改连其他主机。"
        }
        Write-Host "正在验证显式虚拟机IP：$VmIp"
        if (-not (Test-Day37SshDocker -VmIp $VmIp)) {
            throw "显式IP $VmIp 的SSH密钥认证或Docker检查失败；按安全规则立即停止。"
        }
        Write-Host "已确认精确VMX及显式IP：$VmIp" -ForegroundColor Green
        return $VmIp
    }

    Write-Host "正在验证精确VMX实时IP：$expectedIp"
    if (-not (Test-Day37SshDocker -VmIp $expectedIp)) {
        throw "精确VMX的IP $expectedIp 无法通过SSH密钥和Docker检查。"
    }
    Write-Host "已确认 Day37 精确VMX及IP：$expectedIp" -ForegroundColor Green
    return $expectedIp
}

function Invoke-Day37Ssh {
    <#
    在已验证的虚拟机执行一条远程命令。
    返回远端标准输出；远端退出码非 0 时抛出异常并停止后续步骤。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $sshArgs = @(
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=8',
        "root@$VmIp",
        $Command
    )
    $output = @(& ssh.exe @sshArgs)
    if ($LASTEXITCODE -ne 0) {
        throw "远程命令执行失败（退出码 $LASTEXITCODE）：$Command"
    }
    return $output
}

function Copy-Day37FileToVm {
    <#
    用现有 SSH 密钥把一个本地文件复制到 Day37 专用远端目录。
    远端路径必须以 /opt/day37-bank-qa/ 开头，避免误覆盖其他项目。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$RemotePath
    )

    if (-not (Test-Path -LiteralPath $LocalPath -PathType Leaf)) {
        throw "待复制的本地文件不存在：$LocalPath"
    }
    if (-not $RemotePath.StartsWith('/opt/day37-bank-qa/')) {
        throw "拒绝复制到 Day37 目录以外：$RemotePath"
    }

    $scpArgs = @(
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=8',
        $LocalPath,
        "root@${VmIp}:$RemotePath"
    )
    & scp.exe @scpArgs
    if ($LASTEXITCODE -ne 0) {
        throw "复制失败：$LocalPath -> $RemotePath"
    }
}

function Test-Day37RemoteImage {
    <# 返回远端是否已经存在指定镜像；只执行 docker image inspect。 #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$ImageName
    )

    & ssh.exe -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
        "root@$VmIp" "docker image inspect '$ImageName' >/dev/null 2>&1"
    return ($LASTEXITCODE -eq 0)
}

function Get-Day37LabelValue {
    <# 安全读取Docker标签；标签对象或指定键不存在时返回$null。 #>
    [CmdletBinding()]
    param(
        [AllowNull()][object]$Labels,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Labels) {
        return $null
    }
    $property = $Labels.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return [string]$property.Value
}

function Get-Day37RemoteNamedResource {
    <#
    读取Day37固定网络或数据卷的inspect JSON。资源不存在时返回$null。
    参数先经过白名单校验，不能用它检查或操作旧项目的任意资源。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][ValidateSet('network', 'volume')][string]$ResourceType,
        [Parameter(Mandatory = $true)][string]$ResourceName
    )

    if ($ResourceType -eq 'network' -and $ResourceName -ne $script:Day37AllowedNetwork) {
        throw "拒绝检查非Day37网络：$ResourceName"
    }
    if ($ResourceType -eq 'volume' -and $ResourceName -notin $script:Day37AllowedVolumes) {
        throw "拒绝检查非Day37数据卷：$ResourceName"
    }

    $raw = @(& ssh.exe -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
        "root@$VmIp" "docker $ResourceType inspect '$ResourceName' 2>/dev/null")
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return (($raw -join "`n") | ConvertFrom-Json | Select-Object -First 1)
}

function Assert-Day37NamedResourceOwnedOrAbsent {
    <#
    同名网络/卷不存在时允许Compose创建；存在时必须同时有：
    Day37作业标签、owner标签、Compose项目标签。缺一项都拒绝复用。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][ValidateSet('network', 'volume')][string]$ResourceType,
        [Parameter(Mandatory = $true)][string]$ResourceName
    )

    $resource = Get-Day37RemoteNamedResource -VmIp $VmIp `
        -ResourceType $ResourceType -ResourceName $ResourceName
    if ($null -eq $resource) {
        return
    }

    $assignment = Get-Day37LabelValue -Labels $resource.Labels -Name 'ai.course.assignment'
    $owner = Get-Day37LabelValue -Labels $resource.Labels -Name 'ai.course.owner'
    $composeProject = Get-Day37LabelValue -Labels $resource.Labels -Name 'com.docker.compose.project'
    if ($assignment -ne 'day37' -or
        $owner -ne 'day37-bank-qa-stack' -or
        $composeProject -ne 'day37-bank-qa-stack') {
        throw "同名${ResourceType}资源 $ResourceName 的Day37/Compose标签不完整，拒绝复用。"
    }
}

function Assert-Day37NamedResourceOwned {
    <# 资源必须存在且通过相同的三标签所有权检查。 #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][ValidateSet('network', 'volume')][string]$ResourceType,
        [Parameter(Mandatory = $true)][string]$ResourceName
    )

    $resource = Get-Day37RemoteNamedResource -VmIp $VmIp `
        -ResourceType $ResourceType -ResourceName $ResourceName
    if ($null -eq $resource) {
        throw "Day37 ${ResourceType}资源不存在：$ResourceName"
    }
    $assignment = Get-Day37LabelValue -Labels $resource.Labels -Name 'ai.course.assignment'
    $owner = Get-Day37LabelValue -Labels $resource.Labels -Name 'ai.course.owner'
    $composeProject = Get-Day37LabelValue -Labels $resource.Labels -Name 'com.docker.compose.project'
    if ($assignment -ne 'day37' -or
        $owner -ne 'day37-bank-qa-stack' -or
        $composeProject -ne 'day37-bank-qa-stack') {
        throw "Day37 ${ResourceType}资源 $ResourceName 的所有权标签不符合合同。"
    }
    return $resource
}

function Get-Day37RemoteContainer {
    <#
    读取一个 Day37 容器的 docker inspect JSON，并转换成 PowerShell 对象。
    容器不存在时返回 $null；传入非白名单容器名时直接拒绝。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$ContainerName
    )

    if ($ContainerName -notin $script:Day37AllowedContainers) {
        throw "拒绝检查非 Day37 容器：$ContainerName"
    }

    # `2>/dev/null` 在 Linux 远端完成重定向。容器不存在是正常分支，不应让
    # Windows PowerShell 5.1 把 ssh 的标准错误包装成 NativeCommandError。
    $raw = @(& ssh.exe -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
        "root@$VmIp" "docker inspect '$ContainerName' 2>/dev/null")
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return (($raw -join "`n") | ConvertFrom-Json | Select-Object -First 1)
}

function Assert-Day37ContainerOwnedOrAbsent {
    <#
    同名容器不存在时允许后续创建；存在时必须带 Day37 专属标签。
    这样不会因为容器名字碰巧相同而覆盖别人的资源。
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$ContainerName
    )

    $container = Get-Day37RemoteContainer -VmIp $VmIp -ContainerName $ContainerName
    if ($null -eq $container) {
        return
    }

    $assignment = $container.Config.Labels.'ai.course.assignment'
    $owner = $container.Config.Labels.'ai.course.owner'
    if ($assignment -ne 'day37' -or $owner -ne 'day37-bank-qa-stack') {
        throw "同名容器 $ContainerName 已存在，但不属于 Day37；为保护旧资源，部署已停止。"
    }
}

function Assert-Day37ContainerOwned {
    <# 容器必须存在且标签正确，用于健康检查、初始化和停止。 #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$VmIp,
        [Parameter(Mandatory = $true)][string]$ContainerName
    )

    $container = Get-Day37RemoteContainer -VmIp $VmIp -ContainerName $ContainerName
    if ($null -eq $container) {
        throw "Day37 容器不存在：$ContainerName"
    }
    $assignment = $container.Config.Labels.'ai.course.assignment'
    $owner = $container.Config.Labels.'ai.course.owner'
    if ($assignment -ne 'day37' -or $owner -ne 'day37-bank-qa-stack') {
        throw "容器 $ContainerName 的标签不属于 Day37，拒绝操作。"
    }
    return $container
}



