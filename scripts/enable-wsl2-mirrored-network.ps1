# Enable WSL2 Mirrored Networking for mDNS/multicast support
# Requires Windows 11 22H2 or later

$wslConfigPath = "$env:USERPROFILE\.wslconfig"

Write-Host "🔧 Enabling WSL2 Mirrored Networking..." -ForegroundColor Cyan
Write-Host ""

# Check Windows version
$version = [System.Environment]::OSVersion.Version
Write-Host "Windows Version: $version" -ForegroundColor Yellow

if ($version.Build -lt 22621) {
    Write-Host "⚠️  Warning: Mirrored networking requires Windows 11 22H2 (build 22621) or later" -ForegroundColor Yellow
    Write-Host "   Your build: $($version.Build)" -ForegroundColor Yellow
    Write-Host ""
}

# Backup existing config if it exists
if (Test-Path $wslConfigPath) {
    $backup = "$wslConfigPath.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $wslConfigPath $backup
    Write-Host "📋 Backed up existing config to: $backup" -ForegroundColor Green
    Write-Host ""
}

# Create or update .wslconfig
$config = @"
[wsl2]
# Enable mirrored networking mode
# This allows mDNS/multicast traffic to work
networkingMode=mirrored

# Enable DNS tunneling (helps with name resolution)
dnsTunneling=true

# Auto proxy (forwards Windows proxy settings)
autoProxy=true

# Firewall (integrated with Windows Firewall)
firewall=true

# Memory settings (optional, adjust as needed)
# memory=8GB
# processors=4
"@

Set-Content -Path $wslConfigPath -Value $config -Force
Write-Host "✅ Created/updated: $wslConfigPath" -ForegroundColor Green
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Cyan
Get-Content $wslConfigPath
Write-Host ""
Write-Host "⚠️  IMPORTANT: You MUST restart WSL2 for changes to take effect:" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Option 1 - Restart from PowerShell (as Admin):" -ForegroundColor White
Write-Host "   wsl --shutdown" -ForegroundColor Green
Write-Host ""
Write-Host "   Option 2 - Restart from Windows Terminal:" -ForegroundColor White
Write-Host "   Close all WSL terminals, then run: wsl --shutdown" -ForegroundColor Green
Write-Host ""
Write-Host "After restart, mDNS discovery should work!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test with: avahi-browse -a -t" -ForegroundColor Yellow
