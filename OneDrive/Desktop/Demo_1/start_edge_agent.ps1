Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUNBUFFERED = "1"
python -m uvicorn app:app --host 0.0.0.0 --port 8080 --app-dir apps\edge-agent\backend *>> edge-agent.live.log
