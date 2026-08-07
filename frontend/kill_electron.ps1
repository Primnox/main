Get-Process | Where-Object { $_.ProcessName -like '*electron*' } | ForEach-Object { 
    Write-Host "Killing electron PID $($_.Id)"
    Stop-Process -Id $_.Id -Force 
}
Get-Process | Where-Object { $_.ProcessName -eq 'node' } | ForEach-Object {
    Write-Host "Killing node PID $($_.Id)"
    Stop-Process -Id $_.Id -Force
}
Write-Host "All electron and node processes killed."
