$Base = if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8000" }

function Send-Lead($Key, $Email, $Name, $Company) {
    $Body = @{
        name = $Name
        email = $Email
        company = $Company
        source = "portfolio-demo"
    } | ConvertTo-Json

    try {
        Invoke-RestMethod -Method Post -Uri "$Base/webhooks/leads" `
            -Headers @{"Idempotency-Key"=$Key} `
            -ContentType "application/json" -Body $Body | ConvertTo-Json -Depth 8
    } catch {
        if ($_.ErrorDetails.Message) {
            $_.ErrorDetails.Message
        } else {
            throw
        }
    }
}

Write-Host "`n1) Normal success" -ForegroundColor Cyan
Send-Lead "demo-success-001" "buyer@example.com" "Ada Buyer" "example labs"

Write-Host "`n2) Duplicate: no reprocessing" -ForegroundColor Cyan
Send-Lead "demo-success-001" "buyer@example.com" "Ada Buyer" "example labs"

Write-Host "`n3) Transient failure: retry/backoff then success" -ForegroundColor Cyan
Send-Lead "demo-retry-001" "retry@example.com" "Rita Retry" "retry labs"

Write-Host "`n4) Terminal failure: FAILED event + alert" -ForegroundColor Cyan
Send-Lead "demo-hardfail-001" "hardfail@example.com" "Frank Failure" "failure labs"
