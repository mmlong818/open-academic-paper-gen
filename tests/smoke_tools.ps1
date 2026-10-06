# Smoke-test all 6 toolbox SSE endpoints. Reads SSE stream until "done" / "error".
param([string]$Base = "http://127.0.0.1:8080/api/tools")

function Invoke-SSE {
    param([string]$Path, [hashtable]$Body, [int]$TimeoutSec = 90)
    $url = "$Base$Path"
    $json = $Body | ConvertTo-Json -Depth 8 -Compress
    Write-Host "`n=== POST $Path ===" -ForegroundColor Cyan
    $req = [System.Net.HttpWebRequest]::Create($url)
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Timeout = $TimeoutSec * 1000
    $req.ReadWriteTimeout = $TimeoutSec * 1000
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $req.ContentLength = $bytes.Length
    $rs = $req.GetRequestStream(); $rs.Write($bytes, 0, $bytes.Length); $rs.Close()
    try {
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $events = 0; $gotResult = $false; $gotDone = $false; $err = $null
        $start = Get-Date
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if (-not $line) { continue }
            if ($line.StartsWith("data: ")) {
                $events++
                $payload = $line.Substring(6)
                $parsed = $payload | ConvertFrom-Json
                if ($parsed.type -eq "result") { $gotResult = $true }
                if ($parsed.type -eq "done")   { $gotDone = $true; break }
                if ($parsed.type -eq "error")  { $err = $parsed.message; break }
                if ($parsed.type -eq "status") { Write-Host "  status: $($parsed.message)" -ForegroundColor DarkGray }
            }
            if ((Get-Date) - $start -gt [TimeSpan]::FromSeconds($TimeoutSec)) { $err = "client_timeout"; break }
        }
        $reader.Close(); $resp.Close()
        if ($err) { Write-Host "  RESULT: FAIL ($err)" -ForegroundColor Red; return $false }
        if ($gotResult -and $gotDone) { Write-Host "  RESULT: OK ($events events)" -ForegroundColor Green; return $true }
        Write-Host "  RESULT: INCOMPLETE (result=$gotResult done=$gotDone)" -ForegroundColor Yellow; return $false
    } catch {
        Write-Host "  RESULT: EXCEPTION $($_.Exception.Message)" -ForegroundColor Red; return $false
    }
}

$results = @{}
$results["literature"] = Invoke-SSE "/literature" @{ topic = "transformer architecture"; language = "en"; count = 5 }
$results["outline"]    = Invoke-SSE "/outline"    @{ topic = "transformer architecture"; language = "en"; paper_type = "review" }
$results["angle"]      = Invoke-SSE "/angle"      @{ topic = "transformer architecture"; language = "en"; synthesis = "Transformers have become dominant."; research_questions = @("What are the limits?") }
$results["abstract"]   = Invoke-SSE "/abstract"   @{ topic = "transformer architecture"; language = "en"; paper_type = "review"; key_argument = "Attention is all you need."; method = "literature review"; findings = "scaling works" }
$litJson = '[{"title":"Attention Is All You Need","authors":["Vaswani"],"year":2017,"abstract":"The dominant sequence transduction models...","source":"arxiv","url":"","doi":"10.0/x"}]'
$results["synthesis"]  = Invoke-SSE "/synthesis"  @{ topic = "transformers"; language = "en"; literature_json = $litJson }
$results["guide_start"] = Invoke-SSE "/guide/start" @{ field = "machine learning"; language = "en" }
$results["guide_reply"] = Invoke-SSE "/guide/reply" @{ field = "machine learning"; language = "en"; history = @(); user_answer = "A" }

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
foreach ($k in $results.Keys) {
    $tag = if ($results[$k]) { "PASS" } else { "FAIL" }
    $color = if ($results[$k]) { "Green" } else { "Red" }
    Write-Host ("{0,-14} {1}" -f $k, $tag) -ForegroundColor $color
}
