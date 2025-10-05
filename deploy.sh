#!/bin/bash
set -e

# AppleBooks Map - Hetzner Deployment Script
# This script automates deployment to a Hetzner VPS

REPO_URL="https://github.com/chaodoze/applebooks.git"
DEPLOY_DIR="/opt/applebooks"
DATA_DIR="/opt/applebooks/data"

echo "=================================================="
echo "AppleBooks Map - Hetzner Deployment"
echo "=================================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo "Please run as root (use sudo)"
   exit 1
fi

# Install dependencies
echo "📦 Installing system dependencies..."
apt-get update
apt-get install -y \
    git \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Clone or update repository
if [ -d "$DEPLOY_DIR" ]; then
    echo "📥 Updating repository..."
    cd "$DEPLOY_DIR"
    git pull
else
    echo "📥 Cloning repository..."
    git clone "$REPO_URL" "$DEPLOY_DIR"
    cd "$DEPLOY_DIR"
fi

# Create data directory
mkdir -p "$DATA_DIR"

# Check if database exists
if [ ! -f "$DATA_DIR/full_book.sqlite" ]; then
    echo "⚠️  WARNING: Database not found at $DATA_DIR/full_book.sqlite"
    echo "   Please upload your SQLite database to this location"
    echo "   Example: scp full_book.sqlite root@your-server:$DATA_DIR/"
    read -p "   Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Build frontend
echo "🏗️  Building frontend..."
cd "$DEPLOY_DIR/map/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build

# Copy .env.example to .env if not exists
cd "$DEPLOY_DIR"
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "   ⚠️  Please edit .env file with your actual configuration"
    echo "   Especially: VITE_GOOGLE_MAPS_API_KEY"
fi

# Update docker-compose to mount data directory
echo "🔧 Configuring Docker Compose..."
# Update the volume path in docker-compose.yml to use actual data directory
sed -i "s|./full_book.sqlite|$DATA_DIR/full_book.sqlite|g" docker-compose.yml

# Build and start Docker containers
echo "🐳 Building and starting Docker containers..."
docker-compose down || true
docker-compose build
docker-compose up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services started successfully!"
    docker-compose ps
else
    echo "❌ Error: Services failed to start"
    docker-compose logs
    exit 1
fi

# Display instructions
echo ""
echo "=================================================="
echo "✅ Deployment Complete!"
echo "=================================================="
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Upload your SQLite database (if not done):"
echo "   scp full_book.sqlite root@your-server:$DATA_DIR/"
echo ""
echo "2. Configure your .env file:"
echo "   nano $DEPLOY_DIR/.env"
echo ""
echo "3. Point your domain to this server's IP"
echo ""
echo "4. Set up SSL with Let's Encrypt:"
echo "   Edit nginx.conf with your domain name"
echo "   Then run: certbot --nginx -d yourdomain.com"
echo ""
echo "5. Restart services after SSL setup:"
echo "   cd $DEPLOY_DIR && docker-compose restart"
echo ""
echo "📊 Useful commands:"
echo "  View logs:     cd $DEPLOY_DIR && docker-compose logs -f"
echo "  Restart:       cd $DEPLOY_DIR && docker-compose restart"
echo "  Stop:          cd $DEPLOY_DIR && docker-compose down"
echo "  Swap database: Update $DATA_DIR/full_book.sqlite and restart"
echo ""
echo "🌐 Your app should now be accessible at:"
echo "   http://$(hostname -I | awk '{print $1}')"
echo ""
