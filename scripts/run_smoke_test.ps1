param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$RssUrl = "http://127.0.0.1:8000/static/smoke-feed.xml",
    [string]$AuthName = "Local Smoke Test",
    [string]$AuthEmail = "smoke@ascendanalytics.co",
    [string]$AuthPassword = "Password123!",
    [string]$ToneInstructions = "Keep it concise and peer-like.",
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )

    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        SkipHttpErrorCheck = $true
        StatusCodeVariable = "statusCode"
    }

    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 10)
    }

    $rawResponse = Invoke-RestMethod @params
    return @{
        StatusCode = [int]$statusCode
        Body = $rawResponse
    }
}

$signUpPayload = @{
    name = $AuthName
    email = $AuthEmail
    password = $AuthPassword
}

$authResponse = Invoke-JsonRequest -Method Post -Uri "$BaseUrl/api/auth/signup" -Body $signUpPayload

if ($authResponse.StatusCode -eq 409) {
    $authResponse = Invoke-JsonRequest -Method Post -Uri "$BaseUrl/api/auth/signin" -Body @{
        email = $AuthEmail
        password = $AuthPassword
    }
}

if ($authResponse.StatusCode -notin @(200, 201)) {
    throw "Authentication failed with status $($authResponse.StatusCode)."
}

$token = $authResponse.Body.token
if (-not $token) {
    throw "Authentication response did not include a JWT."
}

$authHeaders = @{
    Authorization = "Bearer $token"
}

$submissionPayload = @{
    rss_url = $RssUrl
    tone_instructions = $ToneInstructions
    submitted_at = (Get-Date).ToUniversalTime().ToString("o")
}

$submissionResponse = Invoke-JsonRequest `
    -Method Post `
    -Uri "$BaseUrl/api/submissions" `
    -Headers $authHeaders `
    -Body $submissionPayload

if ($submissionResponse.StatusCode -ne 202) {
    throw "Submission failed with status $($submissionResponse.StatusCode)."
}

$submission = $submissionResponse.Body

Write-Host "Queued run: $($submission.run_id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$terminalStatuses = @("completed", "partial_failed", "failed")

do {
    Start-Sleep -Seconds 3
    $runResponse = Invoke-JsonRequest -Method Get -Uri "$BaseUrl/api/runs/$($submission.run_id)" -Headers $authHeaders
    if ($runResponse.StatusCode -ne 200) {
        throw "Run lookup failed with status $($runResponse.StatusCode)."
    }
    $run = $runResponse.Body
    Write-Host "Run status: $($run.status) | completed=$($run.completed_items)/$($run.total_items) | failed=$($run.failed_items)"
} until ($terminalStatuses -contains $run.status -or (Get-Date) -gt $deadline)

if ($terminalStatuses -notcontains $run.status) {
    throw "Smoke test timed out waiting for terminal run status."
}

if ($run.items.Count -gt 0 -and $run.items[0].lead) {
    $leadResponse = Invoke-JsonRequest -Method Get -Uri "$BaseUrl/api/leads/$($run.items[0].lead.lead_id)" -Headers $authHeaders
    if ($leadResponse.StatusCode -ne 200) {
        throw "Lead lookup failed with status $($leadResponse.StatusCode)."
    }
    $lead = $leadResponse.Body
    Write-Host ""
    Write-Host "Lead generated:"
    Write-Host "Guest: $($lead.guest_name)"
    Write-Host "Company: $($lead.guest_company)"
    Write-Host "Subject: $($lead.email_subject)"
}

Write-Host ""
Write-Host "Dashboard URL: $($submission.dashboard_url)"
