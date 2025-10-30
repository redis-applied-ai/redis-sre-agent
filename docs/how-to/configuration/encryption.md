## Advanced: Secret Encryption

The agent encrypts sensitive data (connection URLs and passwords) before storing them in Redis using envelope encryption.

### How it works
- Data Encryption Key (DEK) per secret
- Master key (env: REDIS_SRE_MASTER_KEY) encrypts the DEK
- AES-GCM (AEAD) provides confidentiality and integrity
- Stored fields: ciphertext, nonce, wrapped DEK, DEK nonce, version

Benefits
- Database leak alone isn’t enough to decrypt
- Unique key per secret
- Authenticated encryption (tamper detection)
- Master key rotation is supported

### Setup
1) Generate a 32-byte master key
```bash
python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```
2) Set environment variable (all processes that read/write instances)
```bash
REDIS_SRE_MASTER_KEY=<base64-32-byte-key>
```

Docker Compose example
```yaml
services:
  sre-agent:
    environment:
      - REDIS_SRE_MASTER_KEY=${REDIS_SRE_MASTER_KEY}
  sre-worker:
    environment:
      - REDIS_SRE_MASTER_KEY=${REDIS_SRE_MASTER_KEY}
```

### Migrating existing plaintext secrets
If any stored instances still contain plaintext secrets, re-save them with the master key set:
```python
import asyncio
from redis_sre_agent.core.instances import get_instances, save_instances

async def migrate():
    items = await get_instances()
    await save_instances(items)

asyncio.run(migrate())
```
Run inside your container:
```bash
docker compose exec -T sre-agent uv run python -c "import asyncio; from redis_sre_agent.core.instances import get_instances, save_instances; async def m():
    items = await get_instances(); await save_instances(items); print('Migrated', len(items), 'instances');
asyncio.run(m())"
```

### Key rotation
1) Generate a new master key
2) Load with old key, then re-save with new key
```python
import asyncio, os
from redis_sre_agent.core.instances import get_instances, save_instances

async def rotate(new_key_b64: str):
    items = await get_instances()  # load using current (old) key
    os.environ['REDIS_SRE_MASTER_KEY'] = new_key_b64
    await save_instances(items)    # re-save using new key

# asyncio.run(rotate('<new-base64-key>'))
```

### Troubleshooting
- “REDIS_SRE_MASTER_KEY environment variable not set”
  - Set the env var on all relevant processes
- “Master key must be 32 bytes”
  - Generate a new base64 key for exactly 32 bytes
- “Decryption failed”
  - Wrong key or data corruption; ensure the correct key for this environment

### Security considerations
Current implementation
- Secrets encrypted at rest
- DEK per secret; AEAD (AES-GCM)
- Master key separate from database

Future hardening options
- KMS/HSM for key storage and unwrapping
- Automated rotation with versioned keys
- Audit logging for encryption operations
- Dedicated secrets manager (Vault, AWS Secrets Manager)
