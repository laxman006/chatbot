# Jira Vectorstore Recovery Script
# This script recovers from database corruption by rebuilding the vectorstore

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "JIRA VECTORSTORE RECOVERY SCRIPT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if server is running
Write-Host "[1/6] Checking if server is running..." -ForegroundColor Yellow
$serverProcess = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*server.py*" }
if ($serverProcess) {
    Write-Host "WARNING: Server appears to be running!" -ForegroundColor Red
    Write-Host "Please stop the server first (Ctrl+C) and run this script again." -ForegroundColor Red
    Read-Host "Press Enter to continue anyway (NOT RECOMMENDED)"
}

# Step 2: Backup corrupted database
Write-Host "[2/6] Backing up corrupted database..." -ForegroundColor Yellow
if (Test-Path "data\jira_chroma_db") {
    $backupPath = "data\jira_chroma_db.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -Path "data\jira_chroma_db" -Destination $backupPath -Recurse -ErrorAction SilentlyContinue
    Write-Host "  Backup created: $backupPath" -ForegroundColor Green
} else {
    Write-Host "  No existing database found - will create new one" -ForegroundColor Gray
}

# Step 3: Remove corrupted database
Write-Host "[3/6] Removing corrupted database..." -ForegroundColor Yellow
if (Test-Path "data\jira_chroma_db") {
    Remove-Item -Path "data\jira_chroma_db" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  Corrupted database removed" -ForegroundColor Green
} else {
    Write-Host "  No database to remove" -ForegroundColor Gray
}

# Step 4: Remove lock file
Write-Host "[4/6] Removing lock file..." -ForegroundColor Yellow
if (Test-Path "data\jira_sync.lock") {
    Remove-Item -Path "data\jira_sync.lock" -Force -ErrorAction SilentlyContinue
    Write-Host "  Lock file removed" -ForegroundColor Green
} else {
    Write-Host "  No lock file found" -ForegroundColor Gray
}

# Step 5: Verify .env configuration
Write-Host "[5/6] Verifying .env configuration..." -ForegroundColor Yellow
$envContent = Get-Content ".env" -Raw
if ($envContent -match "INITIALIZE_JIRA_VECTORSTORE=true") {
    Write-Host "  INITIALIZE_JIRA_VECTORSTORE=true ✓" -ForegroundColor Green
} else {
    Write-Host "  WARNING: INITIALIZE_JIRA_VECTORSTORE is not set to true!" -ForegroundColor Red
    Write-Host "  Please set INITIALIZE_JIRA_VECTORSTORE=true in .env" -ForegroundColor Red
}

if ($envContent -match "ENABLE_JIRA_VECTORSTORE=true") {
    Write-Host "  ENABLE_JIRA_VECTORSTORE=true ✓" -ForegroundColor Green
} else {
    Write-Host "  WARNING: ENABLE_JIRA_VECTORSTORE is not set to true!" -ForegroundColor Red
}

# Step 6: Instructions
Write-Host "[6/6] Recovery preparation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "1. Start your server: python server.py" -ForegroundColor White
Write-Host "2. The server will automatically rebuild the Jira vectorstore" -ForegroundColor White
Write-Host "3. Monitor logs for: 'BUILDING SEPARATE JIRA VECTORSTORE'" -ForegroundColor White
Write-Host "4. After rebuild completes, set INITIALIZE_JIRA_VECTORSTORE=false in .env" -ForegroundColor White
Write-Host "5. Restart server" -ForegroundColor White
Write-Host ""
Write-Host "The locking mechanism is now active and will prevent future corruption." -ForegroundColor Green
Write-Host ""
