$ErrorActionPreference = 'SilentlyContinue'
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
        if ($response.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:8765'; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
