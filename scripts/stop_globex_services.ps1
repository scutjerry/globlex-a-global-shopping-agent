# Stops processes listening on the ports reserved for the Globex local stack.
$ports = 8000, 5173, 5174

foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Stopping listener on port $port (PID $($_.OwningProcess))"
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
}

Start-Sleep -Seconds 2
