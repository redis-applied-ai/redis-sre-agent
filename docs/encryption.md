# Secret Encryption

The Redis SRE Agent encrypts sensitive data (connection URLs and passwords) before storing them in Redis using envelope encryption.

## How It Works

### Envelope Encryption

Each secret is encrypted using a two-layer approach:

1. **Data Encryption Key (DEK)**: A unique random key is generated for each secret
2. **Master Key**: Encrypts the DEK (stored in environment variable)
3. **AES-GCM**: AEAD cipher provides both encryption and authentication

**Stored in Redis:**
- Ciphertext (encrypted secret)
- Nonce (for AES-GCM)
- Wrapped DEK (encrypted with master key)
- DEK nonce
- Algorithm version

**Security Benefits:**
- Database leak alone isn't enough to decrypt secrets
- Each secret has a unique encryption key
- AEAD provides tamper detection
- Master key rotation is possible

## Setup

### 1. Generate Master Key

Generate a 32-byte master key:

```bash
python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

### 2. Set Environment Variable

Add to your `.env` file:

```bash
REDIS_SRE_MASTER_KEY=<your-generated-key>
```

**⚠️ IMPORTANT:**
- Save this key securely (password manager, secrets vault)
- Without it, you cannot decrypt existing secrets
- Use the same key across all environments accessing the same Redis database
- Never commit this key to version control

### 3. Migrate Existing Secrets

If you have existing instances with plaintext secrets:

```bash
export REDIS_SRE_MASTER_KEY=<your-key>
python scripts/migrate_encrypt_secrets.py
```

This will:
- Load all instances from Redis
- Encrypt any plaintext `connection_url` and `admin_password` fields
- Save them back encrypted
- Skip already-encrypted secrets

## Docker Deployment

Add the master key to your docker-compose.yml:

```yaml
services:
  sre-agent:
    environment:
      - REDIS_SRE_MASTER_KEY=${REDIS_SRE_MASTER_KEY}

  sre-worker:
    environment:
      - REDIS_SRE_MASTER_KEY=${REDIS_SRE_MASTER_KEY}
```

Then set it in your shell before starting:

```bash
export REDIS_SRE_MASTER_KEY=<your-key>
docker-compose up
```

## Key Rotation

To rotate the master key:

1. Generate a new master key
2. Load all instances with the old key
3. Re-encrypt with the new key
4. Update environment variable
5. Restart services

Example rotation script:

```python
import asyncio
from redis_sre_agent.core.instances import get_instances,

save_instances


async def rotate_key():
    # Load with old key
    instances = await get_instances()

    # Update environment with new key
    import os
    os.environ['REDIS_SRE_MASTER_KEY'] = '<new-key>'

    # Save with new key
    await save_instances(instances)


asyncio.run(rotate_key())
```

## Security Considerations

### Current Implementation (Good Enough for Now)

✅ Secrets encrypted at rest in Redis
✅ Unique DEK per secret
✅ AEAD cipher (AES-GCM) with authentication
✅ Master key separate from database
✅ Backward compatible (handles plaintext during migration)

### Future Improvements (Production Hardening)

For production deployments, consider:

1. **KMS/HSM Integration**
   - Store master key in AWS KMS, GCP KMS, Azure Key Vault, or HashiCorp Vault
   - Unwrap DEKs on-demand using KMS API
   - Requires service authentication to access KMS

2. **Key Rotation**
   - Automated key rotation schedule
   - Version tracking for multiple active keys
   - Gradual migration to new keys

3. **Audit Logging**
   - Log all encryption/decryption operations
   - Track key access patterns
   - Alert on anomalies

4. **Secrets Management**
   - Use dedicated secrets manager (Vault, AWS Secrets Manager)
   - Automatic secret rotation
   - Fine-grained access control

## Troubleshooting

### Error: "REDIS_SRE_MASTER_KEY environment variable not set"

Set the master key environment variable:

```bash
export REDIS_SRE_MASTER_KEY=<your-key>
```

### Error: "Master key must be 32 bytes"

The key must be exactly 32 bytes (256 bits). Generate a new one:

```bash
python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

### Error: "Decryption failed"

Possible causes:
- Wrong master key
- Corrupted data in Redis
- Data encrypted with different key

Check that you're using the correct master key for this environment.

### Secrets Still Plaintext

Run the migration script:

```bash
python scripts/migrate_encrypt_secrets.py
```

## API Behavior

### Creating Instances

When you create an instance via API:
```json
{
  "name": "My Redis",
  "connection_url": "redis://localhost:6379",
  "admin_password": "secret123"
}
```

The agent:
1. Validates the URL/password
2. Encrypts them using envelope encryption
3. Stores encrypted data in Redis

### Reading Instances

When you read an instance via API:
```json
{
  "name": "My Redis",
  "connection_url": "**********",
  "admin_password": "***"
}
```

The agent:
1. Loads encrypted data from Redis
2. Decrypts using master key
3. Masks for API response (security)
4. Uses plaintext internally for connections

### Updating Instances

When updating, the agent:
- Accepts new plaintext values
- Encrypts before saving
- Skips masked values (`***`) to preserve existing secrets
