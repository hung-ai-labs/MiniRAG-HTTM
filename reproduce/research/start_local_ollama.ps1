param()
$ErrorActionPreference = 'Stop'
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
try {
    $version = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    Write-Output ('Reusing local Ollama ' + $version.version + '; model/digest checked by local_qwen.py')
    return
} catch {
    # Only start a new server; do not stop or reconfigure an existing user service.
}
$exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Ollama executable not found; no automatic install/download performed' }
$session = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$logs = Join-Path $repo ('runs\2wiki\local\server\' + $session)
New-Item -ItemType Directory -Path $logs | Out-Null
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_CONTEXT_LENGTH = '32768'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_KEEP_ALIVE = '0'
$server = Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'stdout.log') -RedirectStandardError (Join-Path $logs 'stderr.log')
Write-Output ('Started loopback-only Ollama PID ' + $server.Id + '; logs: ' + $logs)
