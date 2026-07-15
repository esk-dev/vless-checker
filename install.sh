#!/bin/bash

# VLESS Self-Healing Gateway Installer
# This script automates the setup of the gateway and checker services.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
       error "This script must be run as root. Use sudo."
    fi
}

check_os() {
    log "Checking OS compatibility..."
    if [ -f /etc/debian_version ]; then
        log "Debian-based OS detected."
    elif [ -f /etc/redhat-release ]; then
        error "RedHat-based OS is not officially supported. Please use Ubuntu/Debian."
    else
        error "Unsupported OS. This script requires Ubuntu or Debian."
    fi
}

install_dependencies() {
    log "Installing system dependencies..."
    apt update
    apt install -y curl python3 python3-pip openssl jq
    
    log "Installing Python dependencies..."
    pip3 install python-dotenv requests
}

install_xray() {
    log "Installing Xray-core..."
    bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
}

setup_env() {
    log "Setting up environment variables..."
    if [ -f .env ]; then
        warn ".env file already exists. Skipping creation."
    else
        cp .env.example .env
        log ".env file created from template."
    fi

    # Generate secure password for Shadowsocks-2022
    # Requires 16 bytes base64 encoded
    SS_PASSWORD=$(openssl rand -base64 16)
    log "Generated secure Shadowsocks password."
    
    # Use sed to replace the placeholder in .env
    # We use | as delimiter in case the password contains /
    sed -i "s|SS_PASSWORD=.*|SS_PASSWORD=$SS_PASSWORD|" .env
    log "Password updated in .env."
}

setup_services() {
    log "Settingly up systemd services..."
    
    PROJECT_DIR=$(pwd)
    
    # Prepare service files with absolute paths
    # vless-gateway.service
    sed "s|/home/developer/vless-checker|$PROJECT_DIR|g" vless-gateway.service > /tmp/vless-gateway.service
    cp /tmp/vless-gateway.service /etc/systemd/system/vless-gateway.service
    
    # vless-checker.service
    sed "s|/home/developer/vless-checker|$PROJECT_DIR|g" vless-checker.service > /tmp/vless-checker.service
    cp /tmp/vless-checker.service /etc/systemd/system/vless-checker.service
    
    # vless-checker.timer
    cp vless-checker.timer /etc/systemd/system/vless-checker.timer

    systemctl daemon-reload

    log "Starting vless-gateway.service..."
    systemctl enable --now vless-gateway.service

    log "Starting vless-checker.timer..."
    systemctl enable --now vless-checker.timer
}

verify_installation() {
    log "Verifying installation..."
    
    # Check if services are active
    if systemctl is-active --quiet vless-gateway.service; then
        log "SUCCESS: vless-gateway.service is running."
    else
        error "FAILURE: vless-gateway.service failed to start. Check 'journalctl -u vless-gateway.service'"
    fi

    if systemctl is-active --quiet vless-checker.timer; then
        log "SUCCESS: vless-checker.timer is running."
    else
        error "FAILURE: vless-checker.timer failed to start. Check 'systemctl status vless-checker.timer'"
    fi
}

main() {
    check_root
    check_os
    install_dependencies
    install_xray
    setup_env
    setup_services
    verify_installation

    echo -e "\n${GREEN}====================================================${NC}"
    echo -e "${GREEN} Installation completed successfully! ${NC}"
    echo -e "${GREEN}====================================================${NC}"
    echo -e "Project Directory: $(pwd)"
    echo -e "Your Shadowsocks-2022 password has been generated and saved in .env"
    echo -e "To check logs, use: ${YELLOW}journalctl -u vless-gateway.service -f${NC}"
    echo -e "To check checker logs, use: ${YELLOW}journalctl -u vless-checker.service -f${NC}"
    echo -e "${GREEN}====================================================${NC}"
}

main "$@"
