param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$RssUrl = "http://127.0.0.1:8000/static/smoke-feed.xml",
    [string]$UserName = "Local Smoke Test",
    [string]$UserEmail = "smoke@example.com",
    [string]$ToneInstructions = "Keep it concise and peer-like.",
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"

$submissionPayload = @{
    user_name = $UserName
    user_email = $UserEmail
    rss_url = $RssUrl
    tone_instructions = $ToneInstructions
    submitted_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json

$submission = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/api/submissions" `
    -ContentType "application/json" `
    -Body $submissionPayload

Write-Host "Queued run: $($submission.run_id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$terminalStatuses = @("completed", "partial_failed", "failed")

do {
    Start-Sleep -Seconds 3
    $run = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/runs/$($submission.run_id)"
    Write-Host "Run status: $($run.status) | completed=$($run.completed_items)/$($run.total_items) | failed=$($run.failed_items)"
} until ($terminalStatuses -contains $run.status -or (Get-Date) -gt $deadline)

if ($terminalStatuses -notcontains $run.status) {
    throw "Smoke test timed out waiting for terminal run status."
}

if ($run.items.Count -gt 0 -and $run.items[0].lead) {
    $lead = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/leads/$($run.items[0].lead.lead_id)"
    Write-Host ""
    Write-Host "Lead generated:"
    Write-Host "Guest: $($lead.guest_name)"
    Write-Host "Company: $($lead.guest_company)"
    Write-Host "Subject: $($lead.email_subject)"
}

Write-Host ""
Write-Host "Dashboard URL: $($submission.dashboard_url)"
