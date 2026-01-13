# PowerShell Script to Sync Data Folder to Server
# Run this from: C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

param(
    [string]$ServerIP = "159.89.164.11",
    [string]$ServerUser = "root",
    [string]$ProjectDir = "/opt/chatbot",
    [string]$DataDir = "data"
)

Write-Host "========================================" -ForegroundColor Green
Write-Host "Syncing Data Folder to Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check if data folder exists
if (-not (Test-Path $DataDir)) {
    Write-Host "ERROR: Data folder '$DataDir' not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Step 1: Creating compressed archive..." -ForegroundColor Yellow
$archiveName = "data.tar.gz"
if (Test-Path $archiveName) {
    Remove-Item $archiveName -Force
}

# Create tar archive (requires tar command - available in Windows 10+)
tar -czf $archiveName $DataDir

if (-not (Test-Path $archiveName)) {
    Write-Host "ERROR: Failed to create archive!" -ForegroundColor Red
    Write-Host "Trying alternative method with scp -r..." -ForegroundColor Yellow
    
    Write-Host "Step 2: Uploading data folder directly..." -ForegroundColor Yellow
    scp -r $DataDir "${ServerUser}@${ServerIP}:${ProjectDir}/"
    
    Write-Host "Step 3: Setting permissions on server..." -ForegroundColor Yellow
    ssh "${ServerUser}@${ServerIP}" "cd ${ProjectDir} && chmod -R 755 ${DataDir}"
    
    Write-Host ""
    Write-Host "✓ Data folder synced successfully!" -ForegroundColor Green
    exit 0
}

Write-Host "✓ Archive created: $archiveName" -ForegroundColor Green
Write-Host ""

# Get archive size
$archiveSize = (Get-Item $archiveName).Length / 1MB
Write-Host "Archive size: $([math]::Round($archiveSize, 2)) MB" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 2: Uploading archive to server..." -ForegroundColor Yellow
scp $archiveName "${ServerUser}@${ServerIP}:${ProjectDir}/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload archive!" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Archive uploaded successfully" -ForegroundColor Green
Write-Host ""

Write-Host "Step 3: Extracting archive on server..." -ForegroundColor Yellow
ssh "${ServerUser}@${ServerIP}" @"
cd ${ProjectDir}
if [ -d '${DataDir}' ]; then
    echo 'Backing up existing data folder...'
    tar -czf data_backup_\$(date +%Y%m%d_%H%M%S).tar.gz ${DataDir}/
fi
tar -xzf ${archiveName}
chmod -R 755 ${DataDir}
rm ${archiveName}
echo 'Data folder contents:'
ls -lh ${DataDir}/
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to extract archive on server!" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Archive extracted successfully" -ForegroundColor Green
Write-Host ""

Write-Host "Step 4: Cleaning up local archive..." -ForegroundColor Yellow
Remove-Item $archiveName -Force
Write-Host "✓ Local archive removed" -ForegroundColor Green
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "Data Sync Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Server: ${ServerUser}@${ServerIP}" -ForegroundColor Cyan
Write-Host "Location: ${ProjectDir}/${DataDir}" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verify on server:" -ForegroundColor Yellow
Write-Host "  ssh ${ServerUser}@${ServerIP} 'cd ${ProjectDir} && ls -lh ${DataDir}/'" -ForegroundColor White
Write-Host ""
