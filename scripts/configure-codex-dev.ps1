[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')][string]$Namespace = 'codex',
    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')][string]$SecretName = 'codex-gateway-auth',
    [ValidateRange(1, 65535)][int]$LocalPort = 18080,
    [string]$Context,
    [string]$Kubeconfig,
    [string]$SshHost
)

$ErrorActionPreference = 'Stop'
if ($SshHost) {
    if ($Context -or $Kubeconfig) { throw 'SSH mode uses the remote kubectl context; omit -Context and -Kubeconfig.' }
    if ($SshHost.StartsWith('-') -or $SshHost -notmatch '^[A-Za-z0-9_.@:-]+$') { throw 'Invalid SSH host.' }
    # SSH prompts for authentication directly in the user's terminal. The
    # gateway token is captured, validated, and never written to the console.
    $encodedToken = & ssh $SshHost "kubectl -n $Namespace get secret $SecretName -o jsonpath='{.data.token}'"
} else {
    $kubectlArgs = @()
    if ($Kubeconfig) { $kubectlArgs += @('--kubeconfig', $Kubeconfig) }
    if ($Context) { $kubectlArgs += @('--context', $Context) }
    $kubectlArgs += @('-n', $Namespace, 'get', 'secret', $SecretName, '-o', 'jsonpath={.data.token}')
    $encodedToken = & kubectl @kubectlArgs
}
if ($LASTEXITCODE -ne 0) { throw 'Could not read the gateway Secret. Complete cluster/SSH authentication and retry.' }
$encodedToken = ($encodedToken -join '').Trim()
if ($encodedToken -notmatch '^[A-Za-z0-9+/]+={0,2}$') { throw 'Unexpected output when reading the gateway Secret.' }
$gatewayToken = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedToken))
# Provisioning below uses a hex token; this restriction keeps .env parsing exact.
if ($gatewayToken -notmatch '^[A-Za-z0-9_-]{32,}$') { throw 'Use a gateway token of at least 32 letters, digits, underscores, or hyphens.' }

$repositoryPath = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repositoryPath '.env'
$lines = @()
if (Test-Path -LiteralPath $envFile) { $lines = @(Get-Content -LiteralPath $envFile -Encoding UTF8) }
$settings = [ordered]@{
    LLM_PROVIDER = 'codex'
    CODEX_TRANSPORT = 'http'
    CODEX_REMOTE_URL = "http://127.0.0.1:$LocalPort"
    CODEX_REMOTE_TOKEN = $gatewayToken
    CODEX_TIMEOUT_SECONDS = '600'
    CODEX_REMOTE_TIMEOUT_SECONDS = '630'
}
$pattern = '^\s*(?:export\s+)?(' + (($settings.Keys | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')\s*='
$lines = @($lines | Where-Object { $_ -notmatch $pattern })
foreach ($setting in $settings.GetEnumerator()) { $lines += "$($setting.Key)=$($setting.Value)" }
[IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))
Write-Host 'Updated .env for the remote Codex gateway. Existing unrelated settings were preserved; the token was not displayed.'
