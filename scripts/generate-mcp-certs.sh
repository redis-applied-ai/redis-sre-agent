#!/bin/bash
# Generate self-signed certificates for the MCP server

CERT_DIR="monitoring/nginx/certs"
mkdir -p "$CERT_DIR"

# Generate self-signed certificate valid for 365 days
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.crt" \
    -subj "/CN=localhost/O=Redis SRE Agent/C=US" \
    -addext "subjectAltName=DNS:localhost,DNS:sre-mcp,IP:127.0.0.1"

echo "Certificates generated in $CERT_DIR/"
echo "  - server.crt (certificate)"
echo "  - server.key (private key)"
echo ""
echo "To trust this cert on macOS:"
echo "  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $CERT_DIR/server.crt"
