# Kindle RNDIS Driver Installer (Run as Administrator)
# Usage: Right-click -> Run with PowerShell as Administrator

$infPath = "E:\workbuddy\2026-08-05-10-54-06\kindle-dashboard\kindle_rndis.inf"
$certFile = "E:\workbuddy\2026-08-05-10-54-06\kindle-dashboard\kindle_cert.cer"

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] Please run as Administrator!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "=== Kindle RNDIS Driver Installer ===" -ForegroundColor Cyan

# Step 1: Create cert
$cert = Get-ChildItem Cert:\CurrentUser\My -ErrorAction SilentlyContinue | Where-Object { $_.Subject -match "WorkBuddy Kindle RNDIS" } | Select-Object -First 1
if (-not $cert) {
    Write-Host "[1/6] Creating code signing certificate..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=WorkBuddy Kindle RNDIS" -CertStoreLocation Cert:\CurrentUser\My
    Write-Host "  Certificate created: $($cert.Thumbprint)" -ForegroundColor Green
} else {
    Write-Host "[1/6] Certificate already exists: $($cert.Thumbprint)" -ForegroundColor Green
}

# Step 2: Sign INF
Write-Host "[2/6] Signing INF file..." -ForegroundColor Yellow
$sig = Set-AuthenticodeSignature -FilePath $infPath -Certificate $cert
Write-Host "  Signature status: $($sig.Status)" -ForegroundColor Green

# Step 3: Export cert
Write-Host "[3/6] Exporting certificate..." -ForegroundColor Yellow
Export-Certificate -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" -FilePath $certFile -Force | Out-Null
Write-Host "  Exported to: $certFile" -ForegroundColor Green

# Step 4: Import to Trusted Root
Write-Host "[4/6] Importing to Trusted Root CA..." -ForegroundColor Yellow
Import-Certificate -CertStoreLocation Cert:\LocalMachine\Root -FilePath $certFile -ErrorAction SilentlyContinue | Out-Null
Write-Host "  Done" -ForegroundColor Green

# Step 5: Import to Trusted Publisher
Write-Host "[5/6] Importing to Trusted Publisher..." -ForegroundColor Yellow
Import-Certificate -CertStoreLocation Cert:\LocalMachine\TrustedPublisher -FilePath $certFile -ErrorAction SilentlyContinue | Out-Null
Write-Host "  Done" -ForegroundColor Green

# Step 6: Install driver
Write-Host "[6/6] Installing driver with pnputil..." -ForegroundColor Yellow
$result = & pnputil /add-driver $infPath /install 2>&1
Write-Host $result

Write-Host ""
Write-Host "=== Complete ===" -ForegroundColor Cyan
Write-Host "If you see 'Added driver packages: 1' above, the driver is installed."
Write-Host "COM7 should now become a network adapter."
Write-Host ""
Read-Host "Press Enter to exit"
