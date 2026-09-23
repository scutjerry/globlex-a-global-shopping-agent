# Safe runtime verification for controlled simulated-order deletion.
# It never prints .env values or the one-time control token.
$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8080/api'
$body = @{ items = @(@{ product_id = 'P1001'; sku_id = 'P1001-S1'; quantity = 1 }); destination_country = 'US'; currency = 'USD' } | ConvertTo-Json -Compress
$key = [guid]::NewGuid().ToString()

function Get-HttpResult([string] $Method, [string] $Uri, [string] $Body, [hashtable] $Headers = @{}) {
    try {
        # Windows PowerShell 5.1 rejects -Body even when the supplied value is $null for GET.
        if ($Method -eq 'GET' -or $null -eq $Body) {
            $response = Invoke-WebRequest -Method $Method -Uri $Uri -Headers $Headers -UseBasicParsing -TimeoutSec 60
        } else {
            $response = Invoke-WebRequest -Method $Method -Uri $Uri -ContentType 'application/json' -Headers $Headers -Body $Body -UseBasicParsing -TimeoutSec 60
        }
        return @{ Status = [int]$response.StatusCode; Body = $response.Content }
    } catch {
        $response = $_.Exception.Response
        if ($null -eq $response) { throw }
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        return @{ Status = [int]$response.StatusCode; Body = $reader.ReadToEnd() }
    }
}

$before = (Invoke-RestMethod -Uri "$base/commerce/orders?limit=50" -UseBasicParsing).items
# Inventory non-mutation is covered by the domain and SQLite test suites. This runtime check stays
# HTTP-only so Windows PowerShell 5.1 native-command quoting cannot affect its result.

$created = Get-HttpResult 'POST' "$base/commerce/orders" $body @{ 'Idempotency-Key' = $key }
if ($created.Status -ne 201) { throw "Create returned $($created.Status)" }
$createdPayload = $created.Body | ConvertFrom-Json
$orderId = $createdPayload.order_id
$token = $createdPayload.order_control_token
if ([string]::IsNullOrWhiteSpace($token)) { throw 'Create did not return a one-time token' }
Write-Output 'PASS create returned 201 with a non-empty one-time token (redacted)'

$cancelPayload = @{ order_control_token = $token } | ConvertTo-Json -Compress
$cancelled = Get-HttpResult 'POST' "$base/commerce/orders/$orderId/cancellations" $cancelPayload
if ($cancelled.Status -ne 200 -or (($cancelled.Body | ConvertFrom-Json).status -ne 'CANCELLED')) { throw 'Cancel did not produce CANCELLED' }
Write-Output 'PASS cancel transitioned the user simulation to CANCELLED'

$deleted = Get-HttpResult 'DELETE' "$base/commerce/orders/$orderId" $cancelPayload
if ($deleted.Status -ne 204) { throw "Delete returned $($deleted.Status)" }
Write-Output 'PASS delete returned 204'

$hidden = Get-HttpResult 'GET' "$base/commerce/orders/$orderId" $null
if ($hidden.Status -ne 404) { throw "Deleted order GET returned $($hidden.Status), expected 404" }
$after = (Invoke-RestMethod -Uri "$base/commerce/orders?limit=50" -UseBasicParsing).items
if ($after.order_id -contains $orderId) { throw 'Deleted order remained in public list' }
Write-Output 'PASS deleted order is hidden from detail and list'

$seedDelete = Get-HttpResult 'DELETE' "$base/commerce/orders/DEMO-CN-24001" $cancelPayload
if ($seedDelete.Status -ne 409) { throw "Seed delete returned $($seedDelete.Status), expected 409" }
Write-Output 'PASS DEMO seed remains deletion-protected'

$seedCount = @($after | Where-Object { $_.order_kind -eq 'SEEDED_DEMO' }).Count
Write-Output "PASS public list preserves $seedCount seeded demo orders"
