param(
  [switch]$Tunnel
)

$Root = $PSScriptRoot
$BackendOut = Join-Path $Root "edge-agent.backend.out.log"
$BackendErr = Join-Path $Root "edge-agent.backend.err.log"
$WebOut = Join-Path $Root "edge-agent.web.out.log"
$WebErr = Join-Path $Root "edge-agent.web.err.log"
$TunnelOut = Join-Path $Root "edge-agent.tunnel.out.log"
$TunnelErr = Join-Path $Root "edge-agent.tunnel.err.log"

$env:PYTHONUNBUFFERED = "1"
$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8080"
$env:MERGEN_BACKEND_ORIGIN = "http://127.0.0.1:8080"

Start-Process `
  -FilePath "python" `
  -ArgumentList "-m","uvicorn","app:app","--host","127.0.0.1","--port","8080","--app-dir","apps\edge-agent\backend" `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $BackendOut `
  -RedirectStandardError $BackendErr `
  -WindowStyle Hidden

Start-Process `
  -FilePath "npm.cmd" `
  -ArgumentList "run","dev","--prefix","apps\edge-agent\web" `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $WebOut `
  -RedirectStandardError $WebErr `
  -WindowStyle Hidden

Write-Host "Backend: http://127.0.0.1:8080"
Write-Host "Next frontend: http://127.0.0.1:3000"
Write-Host "Logs: edge-agent.backend.*.log, edge-agent.web.*.log"

if ($Tunnel) {
  $Cloudflared = Get-Command "cloudflared" -ErrorAction SilentlyContinue
  if ($Cloudflared) {
    Start-Process `
      -FilePath $Cloudflared.Source `
      -ArgumentList "tunnel","--url","http://127.0.0.1:3000" `
      -WorkingDirectory $Root `
      -RedirectStandardOutput $TunnelOut `
      -RedirectStandardError $TunnelErr `
      -WindowStyle Hidden
    Write-Host "Cloudflare tunnel starting. Check edge-agent.tunnel.*.log for the public URL."
  } else {
    Write-Host "cloudflared was not found. Install Cloudflare Tunnel, then rerun with -Tunnel."
  }
}
