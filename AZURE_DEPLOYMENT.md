# Azure Deployment Guide for WordPress Scanner

This guide explains how to deploy the WordPress Scanner web application to Microsoft Azure.

## Prerequisites

- Azure Account (https://azure.microsoft.com)
- Git installed locally
- Python 3.8+ installed

## Recommended Azure VM Sizes

For 3+ parallel scanner instances, choose:

| VM Size | vCPU | RAM | Monthly Cost* | Use Case |
|---------|------|-----|---------------|----------|
| Standard_D2s_v3 | 2 | 8 GB | ~$50/mo | Light use (1-2 threads) |
| Standard_D4s_v3 | 4 | 16 GB | ~$100/mo | Medium use (3-5 threads) |
| Standard_D8s_v3 | 8 | 32 GB | ~$200/mo | Heavy use (10+ threads) |

*Prices are estimates and vary by region

## Deployment Option 1: Azure App Service (Recommended)

### Step 1: Create Azure Account & Resource Group

```bash
# Login to Azure
az login

# Create resource group
az group create --name wordpress-scanner-rg --location eastus
```

### Step 2: Create App Service Plan

```bash
# Create App Service plan (Pricing tier)
az appservice plan create --name wordpress-scanner-plan \
    --resource-group wordpress-scanner-rg \
    --sku B1  # Or D1, S1, etc.
```

### Step 3: Create Web App

```bash
# Create web app
az webapp create --name your-scanner-name \
    --resource-group wordpress-scanner-rg \
    --plan wordpress-scanner-plan \
    --runtime "PYTHON:3.11"
```

### Step 4: Configure Deployment

```bash
# Configure deployment from local Git
az webapp deployment source config-local-git \
    --name your-scanner-name \
    --resource-group wordpress-scanner-rg
```

### Step 5: Add Deployment Credentials

```bash
# Set deployment credentials
az webapp deployment user set --user-name your-username \
    --password your-password
```

### Step 6: Push Code to Azure

```bash
# Add Azure remote
git remote add azure <deployment-url>

# Push to Azure
git push azure main
```

## Deployment Option 2: Azure Virtual Machine

### Step 1: Create VM

```bash
# Create VM (Ubuntu Server)
az vm create \
    --resource-group wordpress-scanner-rg \
    --name scanner-vm \
    --image UbuntuLTS \
    --size Standard_D4s_v3 \
    --admin-username azureuser \
    --admin-password your-password
```

### Step 2: Open Ports

```bash
# Open port 5000 for Flask
az vm open-port --resource-group wordpress-scanner-rg \
    --name scanner-vm \
    --port 5000
```

### Step 3: SSH into VM and Setup

```bash
# SSH into VM
ssh azureuser@your-vm-ip

# Install dependencies
sudo apt update
sudo apt install python3-pip python3-venv

# Clone your code
git clone your-repo-url
cd your-repo

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Run the app
python web_scanner.py
```

### Step 4: Run as Service (Optional)

```bash
# Create systemd service
sudo nano /etc/systemd/system/scanner.service

# Add:
[Unit]
Description=WordPress Scanner
After=network.target

[Service]
User=azureuser
WorkingDirectory=/home/azureuser/your-repo
ExecStart=/home/azureuser/your-repo/venv/bin/python web_scanner.py
Restart=always

[Install]
WantedBy=multi-user.target

# Enable service
sudo systemctl enable scanner
sudo systemctl start scanner
```

## Running Multiple Instances

For 3+ parallel instances, you have two options:

### Option A: Single VM with More Threads

- Use a larger VM (D8s_v3 or larger)
- Run the scanner with 5-10 threads
- All scans share the same database

### Option B: Multiple VMs with Shared Database

- Create multiple VMs
- Use Azure SQL Database or external MySQL
- Modify web_scanner.py to use remote database
- Each VM runs independently

## Accessing Your Scanner

Once deployed, access your scanner at:

```
http://your-app-name.azurewebsites.net
```

Or for VM:

```
http://your-vm-ip:5000
```

## Security Considerations

1. **Add Authentication**: Currently no login - consider adding Flask-Login
2. **SSL/HTTPS**: Enable in Azure Portal
3. **Firewall**: Restrict access to your IP only
4. **Environment Variables**: Set SECRET_KEY for production

## Troubleshooting

### Check Logs

```bash
# Azure App Service
az webapp log tail --name your-app --resource-group wordpress-scanner-rg

# VM
journalctl -u scanner -f
```

### Common Issues

1. **Module not found**: Ensure all dependencies in requirements.txt
2. **Port already in use**: Change PORT in web_scanner.py
3. **Memory issues**: Use larger VM or reduce threads
4. **Timeout errors**: Increase timeout in scanner configuration

## Cost Optimization

- Use Azure Spot VMs for non-critical workloads
- Set up auto-shutdown schedule
- Use Azure Cost Management to monitor spending

## Security Configuration

### Set Authentication Credentials

Before deploying, set strong credentials:

```bash
# Set environment variables
ADMIN_USERNAME=your_secure_username
ADMIN_PASSWORD=your_very_secure_password
SECRET_KEY=random_secret_key
```

### In Azure Portal:
1. Go to your App Service / VM
2. Find "Configuration" or "Environment Variables"
3. Add the variables above
4. Restart the application

### Recommended Security Settings:

1. **Use HTTPS** - Enable in Azure (App Service has free SSL)
2. **Restrict IP** - Configure firewall rules
3. **Use strong passwords** - At least 12 characters, mixed case, numbers, symbols
4. **Don't share credentials** - Create separate accounts if needed

## Next Steps

1. Add SSL certificate (Azure provides free)
2. Set up custom domain
3. Configure backup for database
4. Set up monitoring and alerts
