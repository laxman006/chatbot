#!/bin/bash

# Slack2Teams Production Deployment Script for Ubuntu
# Domain: newcf3.cloudfuze.com
# This is the DEV deployment that will be tested before deploying to ai.cloudfuze.com

set -e  # Exit on any error

echo "🚀 Starting Slack2Teams DEV Deployment to newcf3.cloudfuze.com..."
echo "Domain: newcf3.cloudfuze.com"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons"
   exit 1
fi

# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required packages
print_status "Installing required packages..."
sudo apt install -y curl wget git unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release

# Install Docker
print_status "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    print_success "Docker installed successfully"
else
    print_success "Docker is already installed"
fi

# Install Docker Compose (standalone)
print_status "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    print_success "Docker Compose installed successfully"
else
    print_success "Docker Compose is already installed"
fi

# Install Certbot for SSL certificates
print_status "Installing Certbot for SSL certificates..."
sudo apt install -y certbot python3-certbot-nginx

# Create application directory
APP_DIR="/opt/slack2teams-newcf3"
print_status "Creating application directory: $APP_DIR"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Copy application files
print_status "Copying application files..."
cp -r . $APP_DIR/
cd $APP_DIR

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p data logs

# Set proper permissions
print_status "Setting proper permissions..."
chmod +x deploy-newcf3.sh
chmod 644 nginx-newcf3.conf
chmod 644 docker-compose.prod.yml

# Create production environment file
print_status "Creating production environment file..."
if [ ! -f .env.prod ]; then
    cat > .env.prod << EOF
# Production Environment Variables for newcf3.cloudfuze.com
# Replace these with your actual production values

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Microsoft OAuth Configuration
MICROSOFT_CLIENT_ID=your_microsoft_client_id_here
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret_here
MICROSOFT_TENANT=your_microsoft_tenant_here

# Langfuse Configuration (Optional)
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key_here
LANGFUSE_SECRET_KEY=your_langfuse_secret_key_here
LANGFUSE_HOST=http://langfuse:3000

# NextAuth Secret (if using Langfuse)
NEXTAUTH_SECRET=your_nextauth_secret_here

# MongoDB Configuration
MONGODB_URL=your_mongodb_url_here
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories
MONGODB_VECTORSTORE_COLLECTION=vectorstore

# Vectorstore Configuration
VECTORSTORE_BACKEND=weaviate
INITIALIZE_VECTORSTORE=false

# Data Sources
ENABLE_WEB_SOURCE=true
ENABLE_PDF_SOURCE=true
ENABLE_EXCEL_SOURCE=true
ENABLE_DOC_SOURCE=true
ENABLE_SHAREPOINT_SOURCE=true
ENABLE_OUTLOOK_SOURCE=true
EOF
    print_warning "Please edit .env.prod with your actual production values"
fi

# Stop any existing containers
print_status "Stopping any existing containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Copy nginx config for newcf3
print_status "Setting up nginx configuration for newcf3.cloudfuze.com..."
cp nginx-newcf3.conf nginx-prod.conf

# Build and start containers
print_status "Building and starting containers..."
docker-compose -f docker-compose.prod.yml --env-file .env.prod up --build -d

# Wait for services to start
print_status "Waiting for services to start..."
sleep 30

# Check if services are running
print_status "Checking service status..."
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    print_success "Services are running successfully"
else
    print_error "Some services failed to start. Check logs with: docker-compose -f docker-compose.prod.yml logs"
    exit 1
fi

# Setup SSL certificate
print_status "Setting up SSL certificate with Let's Encrypt..."
print_warning "Make sure your domain newcf3.cloudfuze.com points to this server's IP"
read -p "Press Enter to continue with SSL setup..."

# Stop nginx temporarily for SSL setup
docker-compose -f docker-compose.prod.yml stop nginx

# Get SSL certificate
sudo certbot certonly --standalone -d newcf3.cloudfuze.com --non-interactive --agree-tos --email admin@cloudfuze.com

# Update nginx configuration with SSL
print_status "Updating nginx configuration with SSL..."
sudo cp nginx-newcf3.conf /etc/nginx/sites-available/slack2teams-newcf3
sudo ln -sf /etc/nginx/sites-available/slack2teams-newcf3 /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
sudo nginx -t

# Start nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Restart containers with SSL
print_status "Restarting containers with SSL configuration..."
docker-compose -f docker-compose.prod.yml up -d

# Setup firewall
print_status "Setting up firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Setup log rotation
print_status "Setting up log rotation..."
sudo tee /etc/logrotate.d/slack2teams-newcf3 > /dev/null << EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
}
EOF

# Create systemd service for auto-start
print_status "Creating systemd service for auto-start..."
sudo tee /etc/systemd/system/slack2teams-newcf3.service > /dev/null << EOF
[Unit]
Description=Slack2Teams Application (newcf3.cloudfuze.com)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable slack2teams-newcf3.service

# Final status check
print_status "Performing final status check..."
sleep 10

if curl -f -s https://newcf3.cloudfuze.com/health > /dev/null; then
    print_success "Application is accessible via HTTPS!"
else
    print_warning "HTTPS not yet available, checking HTTP..."
    if curl -f -s http://newcf3.cloudfuze.com/health > /dev/null; then
        print_success "Application is accessible via HTTP (SSL setup may need time)"
    else
        print_error "Application is not accessible. Check logs and configuration."
    fi
fi

echo "================================================"
print_success "Deployment to newcf3.cloudfuze.com completed!"
echo ""
echo "🌐 Application URLs:"
echo "   HTTPS: https://newcf3.cloudfuze.com"
echo "   HTTP:  http://newcf3.cloudfuze.com"
echo "   API:   https://newcf3.cloudfuze.com/api/"
echo "   Docs:  https://newcf3.cloudfuze.com/api/docs"
echo ""
echo "📋 Management Commands:"
echo "   View logs:     docker-compose -f docker-compose.prod.yml logs -f"
echo "   Restart:       docker-compose -f docker-compose.prod.yml restart"
echo "   Stop:          docker-compose -f docker-compose.prod.yml down"
echo "   Start:         docker-compose -f docker-compose.prod.yml up -d"
echo "   Service:       sudo systemctl status slack2teams-newcf3"
echo ""
echo "🔧 Configuration:"
echo "   App Directory: $APP_DIR"
echo "   Config File:   $APP_DIR/.env.prod"
echo "   Nginx Config:  /etc/nginx/sites-available/slack2teams-newcf3"
echo ""
print_warning "Don't forget to:"
echo "   1. Update .env.prod with your actual API keys"
echo "   2. Verify DNS settings for newcf3.cloudfuze.com"
echo "   3. Test the application thoroughly"
echo "   4. Once verified, deploy to ai.cloudfuze.com using deploy-ubuntu.sh"
echo ""
print_success "Happy deploying! 🚀"

