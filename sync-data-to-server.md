# Sync Data Folder to Server

## Commands to Sync Data Folder

### Option 1: Using SCP (Windows PowerShell)

```powershell
# Navigate to project directory
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

# Sync data folder to server
scp -r data root@159.89.164.11:/opt/chatbot/
```

### Option 2: Using SCP with Compression (Faster)

```powershell
# Navigate to project directory
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

# Create tar archive and transfer
tar -czf data.tar.gz data
scp data.tar.gz root@159.89.164.11:/opt/chatbot/
ssh root@159.89.164.11 "cd /opt/chatbot && tar -xzf data.tar.gz && rm data.tar.gz && chmod -R 755 data"
```

### Option 3: Using rsync (If available - Git Bash or WSL)

```bash
# In Git Bash or WSL
cd /c/Users/LaxmanKadari/Desktop/v1-dev/chatbot

# Sync data folder (excludes node_modules and .git)
rsync -avz --progress --exclude='node_modules' --exclude='.git' data/ root@159.89.164.11:/opt/chatbot/data/
```

### Option 4: Manual Step-by-Step (Recommended)

```powershell
# Step 1: Create tar archive locally
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot
tar -czf data.tar.gz data

# Step 2: Upload to server
scp data.tar.gz root@159.89.164.11:/opt/chatbot/

# Step 3: SSH into server and extract
ssh root@159.89.164.11
cd /opt/chatbot
tar -xzf data.tar.gz
chmod -R 755 data
rm data.tar.gz
exit
```

## Complete Command Sequence (Copy & Paste)

### For Windows PowerShell:

```powershell
# Navigate to project
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot

# Create archive
tar -czf data.tar.gz data

# Upload to server
scp data.tar.gz root@159.89.164.11:/opt/chatbot/

# Extract on server (run this after upload)
ssh root@159.89.164.11 "cd /opt/chatbot && tar -xzf data.tar.gz && chmod -R 755 data && rm data.tar.gz && ls -lh data"
```

### One-liner (if tar is available):

```powershell
cd C:\Users\LaxmanKadari\Desktop\v1-dev\chatbot; tar -czf data.tar.gz data; scp data.tar.gz root@159.89.164.11:/opt/chatbot/; ssh root@159.89.164.11 "cd /opt/chatbot && tar -xzf data.tar.gz && chmod -R 755 data && rm data.tar.gz"
```

## Verify Data Folder on Server

After syncing, verify the data folder:

```bash
# SSH into server
ssh root@159.89.164.11

# Check data folder
cd /opt/chatbot
ls -lh data/
ls -lh data/chroma_db/
ls -lh data/jira_chroma_db/

# Check permissions
ls -la data/
```

## Important Notes

1. **Data Folder Contents:**
   - `chroma_db/` - Main vectorstore database
   - `jira_chroma_db/` - Jira vectorstore database
   - `graph_relations.db` - Graph database
   - Various JSON files (chat history, feedback, etc.)

2. **Permissions:** The data folder needs to be readable by the Docker container user. The `chmod -R 755 data` command ensures proper permissions.

3. **Size:** The data folder may be large. Using tar.gz compression will make the transfer faster.

4. **Backup:** If data already exists on server, backup it first:
   ```bash
   ssh root@159.89.164.11 "cd /opt/chatbot && tar -czf data_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/"
   ```
