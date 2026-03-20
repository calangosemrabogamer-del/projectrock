# Complete Step-by-Step Azure VM Deployment Guide

## Prerequisites

Before starting, you need:
1. **Azure Account** - Go to https://azure.microsoft.com and create a free account
2. **Credit Card** - Required for verification (won't be charged for free tier)
3. **Your Code** - Already prepared in this folder

---

## Step 1: Install Git (if not installed)

Download from: https://git-scm.com/download/win

During installation, keep all defaults checked.

---

## Step 2: Upload Your Code to GitHub (Recommended)

### 2.1 Create GitHub Account
1. Go to https://github.com
2. Click "Sign up"
3. Follow the instructions

### 2.2 Create a New Repository
1. Click the "+" icon → "New repository"
2. Name: `wordpress-scanner`
3. Select "Private" (important!)
4. Click "Create repository"

### 2.3 Upload Your Files
1. On your computer, open the folder `wordpress_scanner_complete (3)`
2. Right-click → "Git Bash Here" (if you installed Git)
3. Run these commands:

```bash
git init
git add .
git commit -m "Initial commit"
```

4. Go to your GitHub repository
5. Click "uploading an existing file"
6. Drag and drop all your files
7. Click "Commit changes"

---

## Step 3: Create Azure Account

1. Go to https://azure.microsoft.com
2. Click "Start free"
3. Sign in with your Microsoft account
4. Complete verification (credit card required)

---

## Step 4: Create a Virtual Machine

### 4.1 Login to Azure Portal
1. Go to https://portal.azure.com
2. Sign in with your Microsoft account

### 4.2 Create the VM
1. In the search bar (top), type "virtual machines"
2. Click "Virtual machines" in the results
3. Click "+ Create" → "Azure virtual machine"

### 4.3 Fill in the Details (Very Important!)

**Basics Tab:**
- **Subscription**: Keep default (Azure free trial)
- **Resource group**: Click "Create new" → name: `scanner-rg`
- **Virtual machine name**: `wordpress-scanner`
- **Region**: Select one closest to you:
  - `East US` (Virginia, USA)
  - `West Europe` (Netherlands)
  - `Southeast Asia` (Singapore)
- **Image**: Click it → Search for `Ubuntu Server 22.04 LTS` → Select it
  - ⚠️ DO NOT use Windows - it costs more and needs more setup!
- **Size**: Click → Type `D2s` → Select `D2s_v3 (2 vCPU, 8GB RAM)`
  - This costs about $50/month
- **Authentication type**: Select "Password"
- **Username**: `azureuser`
- **Password**: Create a strong password (write it down!)
- **Confirm password**: Same password

**Networking Tab:**
1. Click "Networking" at the top
2. **Virtual network**: Keep default
3. **Public IP**: Keep default (a new one will be created)
4. **Inbound port rules**: 
   - Click "Advanced"
   - Click "Add inbound port rule"
   - **Destination port ranges**: `5000`
   - **Protocol**: `TCP`
   - **Priority**: `100`
   - **Name**: `AllowPort5000`

**Review + Create Tab:**
1. Click "Review + create" at the bottom
2. Wait for validation to pass
3. Click "Create"

### 4.4 Wait for Deployment
- It will take 2-3 minutes
- You'll see "Your deployment is complete"
- Click "Go to resource"

---

## Step 5: Connect to Your VM

### 5.1 Get the Public IP Address
1. On your VM page, look for "Public IP address"
2. Write down the IP address (it looks like: `52.234.xxx.xxx`)

### 5.2 Connect Using SSH
1. On your computer, open "Command Prompt" (search for "cmd")
2. Type:
```bash
ssh azureuser@YOUR_VM_IP
```
(Replace YOUR_VM_IP with your actual IP)

3. Type "yes" to accept the connection
4. Enter your password when prompted

---

## Step 6: Set Up the Server

Once connected to your VM (in the SSH window), run these commands one by one:

### 6.1 Update the Server
```bash
sudo apt update && sudo apt upgrade -y
```
(Press Enter and wait - this takes 2-3 minutes)

### 6.2 Install Python
```bash
sudo apt install python3 python3-pip python3-venv -y
```

### 6.3 Install Git
```bash
sudo apt install git -y
```

### 6.4 Clone Your Code
```bash
cd ~
git clone https://github.com/YOUR_USERNAME/wordpress-scanner.git
cd wordpress-scanner
```

### 6.5 Set Up Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6.6 Set Environment Variables
```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=YourSecurePassword123!
export FLASK_ENV=production
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
```

---

## Step 7: Run the Scanner

### 7.1 Start the Application
```bash
python web_scanner.py
```

You should see:
```
[INFO] Starting WordPress Scanner Web App on port 5000
[INFO] Open http://localhost:5000 in your browser
```

### 7.2 Test It
1. Open your browser on your computer
2. Type: `http://YOUR_VM_IP:5000`
3. You should see the login page!

---

## Step 8: Keep It Running (Important!)

The scanner will stop if you close the SSH window. To keep it running:

### 8.1 Install Screen
```bash
sudo apt install screen -y
```

### 8.2 Create a Screen Session
```bash
screen -S scanner
```

### 8.3 Start the App
```bash
cd ~/wordpress-scanner
source venv/bin/activate
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=YourSecurePassword123!
python web_scanner.py
```

### 8.4 Detach from Screen
1. Press `Ctrl + A`
2. Press `D`

The scanner is now running in the background!

---

## Step 9: Access Your Scanner

1. Open browser on your computer
2. Go to: `http://YOUR_VM_IP:5000`
3. Login with:
   - Username: `admin`
   - Password: `YourSecurePassword123!` (or whatever you set)

---

## Managing Your Scanner

### Check if it's running
```bash
screen -r scanner
```

### Stop the scanner
1. Press `Ctrl + C` in the screen session

### Restart the scanner
```bash
cd ~/wordpress-scanner
source venv/bin/activate
python web_scanner.py
```

---

## Costs and Billing

### Estimated Monthly Cost
| VM Size | Hours/Month | Cost |
|---------|-------------|------|
| D2s_v3 | 730 (always on) | ~$50 |
| D4s_v3 | 730 | ~$100 |
| D8s_v3 | 730 | ~$200 |

### To Minimize Costs
1. **Only run when needed** - Start/stop the VM from Azure Portal
2. **Use smaller VM** - D2s is enough for most scans
3. **Set budget alerts** - In Azure Portal → Cost Management

---

## Important Security Notes

1. **CHANGE THE DEFAULT PASSWORD!** 
   - Default is: `admin` / `changeme123`
   - Set your own with `export ADMIN_PASSWORD=your_new_password`

2. **Don't share your VM IP** - Only access from your computer

3. **Stop VM when not using** - Saves money and reduces detection risk

---

## Troubleshooting

### "Connection refused" on port 5000
- Make sure the scanner is running (`screen -r scanner`)
- Check if port 5000 is allowed in Azure (Step 4.4)

### "Permission denied" error
- Make sure you used `sudo` where needed
- Check file permissions

### Can't connect to VM
- Check the VM is running in Azure Portal
- Verify your IP address is correct

### Billing questions
- Go to Azure Portal → Cost Management
- Set up budget alerts

---

## Summary: What You Need to Remember

1. **VM IP Address**: Write it down
2. **VM Credentials**: Username `azureuser` + your password
3. **Scanner Credentials**: Username `admin` + whatever you set for ADMIN_PASSWORD
4. **To access**: `http://YOUR_VM_IP:5000`
5. **To manage**: SSH into VM → `screen -r scanner`

---

## Need Help?

If you get stuck, search for the error message on Google or ask in Azure forums. The key steps are:
1. Create Azure account
2. Create Ubuntu VM
3. SSH into VM
4. Install Python and dependencies
5. Run web_scanner.py
6. Access via browser
