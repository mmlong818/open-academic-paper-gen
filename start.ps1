# 启动后端和前端服务（静默后台，输出到日志文件）
$Root = $PSScriptRoot

Write-Host "启动后端 (port 8080)..."
$backendLog = "$Root\uvicorn.log"
$backendErr = "$Root\uvicorn-err.log"
Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8080", "--reload", "--reload-dir", "backend", "--timeout-graceful-shutdown", "5" `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErr `
    -WindowStyle Hidden `
    -PassThru | ForEach-Object { Write-Host "  后端 PID: $($_.Id)" }

Start-Sleep -Seconds 3

Write-Host "启动前端 (port 3000)..."
$frontendLog = "$Root\frontend\nextjs.log"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c pnpm dev > `"$frontendLog`" 2>&1" `
    -WorkingDirectory "$Root\frontend" `
    -WindowStyle Hidden `
    -PassThru | ForEach-Object { Write-Host "  前端 PID: $($_.Id)" }

Write-Host ""
Write-Host "服务已在后台启动。"
Write-Host "  后端日志: $backendErr"
Write-Host "  前端日志: $frontendLog"
Write-Host ""
Write-Host "停止服务: .\stop.ps1"
