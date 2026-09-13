<# Offline regression: no SSH, VM startup, or infrastructure writes. #>
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\_VmCommon.ps1')
$vmxUuid = '56 4d c3 84 e2 b2 5e 7d-db c7 23 5e ed 46 fe 54'
$guestUuid = '84c34d56-b2e2-7d5e-dbc7-235eed46fe54'
Assert-Day37GuestUuid -VmxUuid $vmxUuid -GuestUuid $guestUuid
Assert-Day37GuestUuid -VmxUuid $vmxUuid.ToUpperInvariant() -GuestUuid $guestUuid.ToUpperInvariant()
$passed = 2
foreach ($badGuest in @('00000000-0000-0000-0000-000000000000', 'invalid', '564dc384-e2b2-5e7d-dbc7-235eed46fe54')) {
    $rejected = $false
    try { Assert-Day37GuestUuid -VmxUuid $vmxUuid -GuestUuid $badGuest }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Unexpected UUID accepted' }
    $passed++
}
$rejected = $false
try { Assert-Day37GuestUuid -VmxUuid 'not-a-bios-uuid' -GuestUuid $guestUuid }
catch { $rejected = $true }
if (-not $rejected) { throw 'Invalid VMX UUID accepted' }
$passed++

# Stubs make it impossible for these input-validation tests to contact a VM.
function Get-Day37ExpectedVmxIp { param([string]$ExplicitVmIp); throw 'UNEXPECTED_DISCOVERY' }
foreach ($badIp in @('999.1.1.1', 'localhost', '192.168.220.77;echo')) {
    $rejected = $false
    try { Find-Day37VmIp -VmIp $badIp }
    catch {
        if ($_.Exception.Message -eq 'UNEXPECTED_DISCOVERY') { throw 'IP guard ran too late' }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Invalid IP accepted' }
    $passed++
}
Write-Output "VM_IDENTITY_TEST_PASS cases=$passed"
