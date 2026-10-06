# 停止后端和前端服务：只结束监听 8080 / 3000 端口的进程，连同启动它的 uvicorn / pnpm / next 进程链
$Ports = 8080, 3000
$Launcher = 'uvicorn|pnpm|next'

function Get-ServiceRoot([int]$procId) {
    # 向上追溯启动链，直到父进程不再是本服务的 node / cmd / python（例如用户自己的终端）
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId"
    while ($proc) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)"
        if (-not $parent -or $parent.Name -notin 'node.exe', 'cmd.exe', 'python.exe' -or
            $parent.CommandLine -notmatch $Launcher) { break }
        $proc = $parent
    }
    return $proc
}

$stopped = 0
foreach ($port in $Ports) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        $root = Get-ServiceRoot $procId
        if (-not $root) { continue }
        Write-Host "停止端口 $port 的服务：$($root.Name) PID $($root.ProcessId)（含子进程）"
        taskkill /PID $root.ProcessId /T /F | Out-Null
        $stopped++
    }
}

if ($stopped -eq 0) {
    Write-Host "没有找到运行中的服务。"
} else {
    Write-Host "已停止 $stopped 个服务。"
}
