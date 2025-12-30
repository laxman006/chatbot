# Commands to Verify Cursor Implementation on Server

## Server Information
- **Server IP**: `64.227.160.206`
- **Server User**: `root`
- **Project Directory**: `/opt/slack2teams-ai`
- **Domain**: `ai.cloudfuze.com`

---

## Quick Verification Commands

### Option 1: SSH into Server and Check Manually

```bash
# SSH into server
ssh root@64.227.160.206

# Once connected, run these commands:

# 1. Check if cursor images exist in Docker container
docker exec $(docker ps -q -f name=frontend) ls -lh /app/public/images/ | grep -i christmas

# 2. Check image file sizes (should be around 24x24 pixels)
docker exec $(docker ps -q -f name=frontend) file /app/public/images/Christmas*.png

# 3. Check CSS file for cursor definitions
docker exec $(docker ps -q -f name=frontend) grep -A 2 "cursor-tree\|cursor-bulb" /app/.next/static/css/*.css | head -10

# 4. Check source CSS file
grep -A 2 "cursor-tree\|cursor-bulb" /opt/slack2teams-ai/frontend/src/app/globals.css | head -10

# 5. Check if frontend container is running
docker ps | grep frontend

# 6. View frontend logs
docker logs $(docker ps -q -f name=frontend) --tail 30
```

---

### Option 2: Run Verification Script

```bash
# Make script executable
chmod +x verify-cursors-on-server.sh

# Run the script
./verify-cursors-on-server.sh
```

---

### Option 3: Check via HTTP/HTTPS

```bash
# Test if cursor images are accessible
curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--cursor--SweezyCursors.png"

curl -I "https://ai.cloudfuze.com/images/Christmas%20Tree%20&%20Bulb%20Animated--pointer--SweezyCursors.png"

# Check CSS file
curl -s "https://ai.cloudfuze.com/_next/static/css/" | grep -i cursor
```

---

### Option 4: PowerShell Commands (Windows)

```powershell
# SSH into server
ssh root@64.227.160.206

# Once connected, run these commands:

# 1. Check cursor images
docker exec $(docker ps -q -f name=frontend) ls -lh /app/public/images/ | Select-String -Pattern "christmas|cursor|pointer"

# 2. Check image file sizes
docker exec $(docker ps -q -f name=frontend) file /app/public/images/Christmas*.png

# 3. Check CSS for cursor definitions
docker exec $(docker ps -q -f name=frontend) grep -A 2 "cursor-tree" /app/.next/static/css/*.css | Select-Object -First 10

# 4. Check frontend container status
docker ps | Select-String -Pattern "frontend"

# 5. View logs
docker logs $(docker ps -q -f name=frontend) --tail 30
```

---

## Browser-Based Verification

### Step 1: Open the Website
```
https://ai.cloudfuze.com
```

### Step 2: Open Developer Tools (F12)

### Step 3: Check Network Tab
1. Go to **Network** tab
2. Filter by **Img** or search for `Christmas`
3. Reload the page
4. Look for:
   - `Christmas Tree & Bulb Animated--cursor--SweezyCursors.png`
   - `Christmas Tree & Bulb Animated--pointer--SweezyCursors.png`
5. Check Status: Should be `200 OK`
6. Check Size: Should be small (around 1-5 KB for 24x24 images)

### Step 4: Check CSS
1. Go to **Elements** tab
2. Select `<body>` element
3. In **Computed** styles, check `cursor` property
4. Should show: `url("/images/Christmas Tree & Bulb Animated--cursor--SweezyCursors.png") 2 2, auto`

### Step 5: Test Cursor Behavior
1. Move mouse normally → Should see **tree cursor**
2. Hover over buttons/links → Should see **bulb cursor**
3. Check in **Elements** tab → Selected element should have `cursor: var(--cursor-bulb)`

---

## Expected Results

### ✅ Success Indicators:
- ✅ Cursor images exist in `/app/public/images/` directory
- ✅ Images are 24x24 pixels (or smaller)
- ✅ CSS file contains `--cursor-tree` and `--cursor-bulb` variables
- ✅ `body` element has `cursor: var(--cursor-tree)`
- ✅ Clickable elements have `cursor: var(--cursor-bulb)`
- ✅ Images are accessible via HTTP (200 OK)
- ✅ Cursor changes when hovering over clickable elements

### ❌ Failure Indicators:
- ❌ Images not found (404 errors)
- ❌ Images too large (>50KB suggests wrong size)
- ❌ CSS variables not found
- ❌ Cursor doesn't change on hover
- ❌ Default system cursor still showing

---

## Troubleshooting

### If images are not found:
```bash
# Check if images exist in source
ls -lh /opt/slack2teams-ai/frontend/public/images/Christmas*.png

# Rebuild frontend container
cd /opt/slack2teams-ai
docker-compose down
docker-compose up -d --build frontend
```

### If CSS is not updated:
```bash
# Check if globals.css has the changes
grep "cursor-tree\|cursor-bulb" /opt/slack2teams-ai/frontend/src/app/globals.css

# Rebuild frontend
cd /opt/slack2teams-ai
docker-compose restart frontend
# Or rebuild:
docker-compose up -d --build frontend
```

### If cursor doesn't work:
1. Clear browser cache (Ctrl+Shift+Delete)
2. Hard refresh (Ctrl+F5)
3. Check browser console for errors
4. Verify images are loading in Network tab

---

## Quick One-Liner Check

```bash
# Run this single command to check everything:
ssh root@64.227.160.206 "docker exec \$(docker ps -q -f name=frontend) sh -c 'echo \"=== Images ===\" && ls -lh /app/public/images/Christmas*.png 2>/dev/null && echo \"=== CSS ===\" && grep -A 1 cursor-tree /app/.next/static/css/*.css 2>/dev/null | head -5'"
```

