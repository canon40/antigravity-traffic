param(
    [Parameter(Mandatory = $true)]
    [string]$Domain
)

$ErrorActionPreference = "Stop"

function Test-JsonEndpoint {
    param(
        [string]$Url,
        [string]$Name
    )
    try {
        $res = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 20
        Write-Host "[OK] $Name -> $Url"
        $res | ConvertTo-Json -Depth 6
    }
    catch {
        Write-Host "[FAIL] $Name -> $Url"
        Write-Host $_.Exception.Message
        throw
    }
}

$base = "https://$Domain"
Write-Host "Checking deployment: $base"

Test-JsonEndpoint -Url "$base/api/_proxy/health" -Name "Vercel proxy health" | Out-Host
Test-JsonEndpoint -Url "$base/api/health" -Name "Cloudtype api health (via Vercel)" | Out-Host

Write-Host "All checks passed."
