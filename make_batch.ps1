$ErrorActionPreference = "Stop"

# (اختياري) يخلي الكونسول يفهم UTF-8 كويس
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$API = "http://127.0.0.1:8000/api/api/tts"
$textFile = Join-Path $PSScriptRoot "texts.txt"

if (!(Test-Path $textFile)) { throw "texts.txt not found at: $textFile" }

# اقرأ السطور كنصوص صافية 100% (بدون PSObject)
$texts = [System.IO.File]::ReadAllLines($textFile, [System.Text.Encoding]::UTF8) |
Where-Object { $_ -and $_.Trim() -ne "" }

foreach ($line in $texts) {

    # تأكيد أنه String
    $txt = [string]$line
    $txt = $txt.Trim()

    Write-Host "=== TTS ==="
    Write-Host $txt

    # Body JSON UTF-8
    $body = (@{ text = $txt } | ConvertTo-Json -Compress)
    $tmp = Join-Path $env:TEMP "tts.json"
    [System.IO.File]::WriteAllText($tmp, $body, [System.Text.Encoding]::UTF8)

    $raw = curl.exe -sS -X POST $API `
        -H "Content-Type: application/json; charset=utf-8" `
        --data-binary "@$tmp"

    Write-Host "RAW RESPONSE:"
    Write-Host $raw

    $resp = $raw | ConvertFrom-Json

    $audio = [string]$resp.audio_path
    $runId = [string]$resp.run_id

    if ([string]::IsNullOrWhiteSpace($audio) -or [string]::IsNullOrWhiteSpace($runId)) {
        throw "Missing audio_path/run_id. RAW: $raw"
    }

    if (!(Test-Path $audio)) { throw "Audio file not found: $audio" }

    Write-Host "=== RENDER ==="
    python .\backend\tools\render_shorts.py "$audio" "$txt"

    $mp4 = ".\backend\outputs\$runId\shorts.mp4"
    if (Test-Path $mp4) {
        Write-Host "OK: $mp4"
    }
    else {
        Write-Host "MP4 not found at expected path: $mp4"
    }

    Write-Host "------------------------------"
}

Write-Host "BATCH DONE"
