[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')][string]$Namespace = 'codex',
    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')][string]$Service = 'codex-gateway',
    [ValidateRange(1, 65535)][int]$LocalPort = 18080,
    [ValidateRange(1, 65535)][int]$RemotePort = 8080,
    [string]$Context,
    [string]$Kubeconfig,
    [string]$SshHost,
    [ValidateRange(1, 65535)][int]$SshRemotePort = 18080
)

$ErrorActionPreference = 'Stop'
if ($SshHost) {
    if ($Context -or $Kubeconfig) { throw 'SSH mode uses the remote kubectl context; omit -Context and -Kubeconfig.' }
    if ($SshHost.StartsWith('-') -or $SshHost -notmatch '^[A-Za-z0-9_.@:-]+$') { throw 'Invalid SSH host.' }
    Get-Command ssh -ErrorAction Stop | Out-Null
    Write-Host "Codex gateway through SSH: http://127.0.0.1:$LocalPort"
    Write-Host 'Complete SSH authentication in this terminal. Keep it open while developing.'
    $remoteCommand = "kubectl -n $Namespace port-forward --address 127.0.0.1 svc/$Service ${SshRemotePort}:${RemotePort}"
    & ssh -t -o ExitOnForwardFailure=yes -L "127.0.0.1:${LocalPort}:127.0.0.1:${SshRemotePort}" $SshHost $remoteCommand
    exit $LASTEXITCODE
}
Get-Command kubectl -ErrorAction Stop | Out-Null
$kubectlArgs = @()
if ($Kubeconfig) { $kubectlArgs += @('--kubeconfig', $Kubeconfig) }
if ($Context) { $kubectlArgs += @('--context', $Context) }
$kubectlArgs += @('-n', $Namespace, 'port-forward', '--address', '127.0.0.1', "svc/$Service", "${LocalPort}:${RemotePort}")
Write-Host "Codex gateway: http://127.0.0.1:$LocalPort"
Write-Host 'Keep this terminal open. Press Ctrl+C to stop; rerun after the selected Pod restarts.'
& kubectl @kubectlArgs
exit $LASTEXITCODE
