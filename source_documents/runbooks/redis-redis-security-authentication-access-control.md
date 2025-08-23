# Redis Security Authentication Access Control

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Unauthorized access attempts logged in Redis logs.
- Unexpected data access or modification.
- Alerts from security monitoring tools indicating unauthorized access.
- Redis instances exposed to the public internet without authentication.

## Root Cause Analysis

### 1. Check Redis Logs for Unauthorized Access
```bash
grep "AUTH" /var/log/redis/redis-server.log
# Look for repeated failed AUTH attempts indicating unauthorized access attempts.
```

### 2. Verify Current Authentication and Access Control Settings
```bash
redis-cli CONFIG GET requirepass
# Check if 'requirepass' is set. If not, Redis is not using password authentication.

redis-cli ACL LIST
# Review the current ACLs to ensure they are configured correctly and not overly permissive.
```

## Immediate Remediation

### Option 1: Enable Password Authentication
```bash
# Edit the Redis configuration file (redis.conf)
sudo nano /etc/redis/redis.conf

# Add or modify the following line to set a strong password
requirepass yourStrongPasswordHere

# Restart Redis to apply changes
sudo systemctl restart redis

# Warning: Ensure the password is stored securely and shared only with authorized personnel.
```

### Option 2: Implement Access Control Lists (ACLs)
1. Connect to Redis CLI:
   ```bash
   redis-cli
   ```

2. Create a new user with restricted access:
   ```bash
   ACL SETUSER limited_user on >yourStrongPasswordHere ~* +@all
   ```

3. Adjust permissions as needed:
   ```bash
   ACL SETUSER limited_user -@dangerous
   ```

4. Save the configuration:
   ```bash
   ACL SAVE
   ```

## Long-term Prevention

### 1. Network Security Hardening
- Restrict Redis access to trusted IP addresses using firewall rules.
- Ensure Redis is bound to localhost or a private network interface:
  ```bash
  bind 127.0.0.1
  ```

### 2. Regular Security Audits
- Schedule regular audits of Redis configurations and access logs.
- Implement automated scripts to check for configuration drift and unauthorized changes.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor failed authentication attempts
grep "AUTH" /var/log/redis/redis-server.log | wc -l

# Monitor ACL changes
grep "ACL" /var/log/redis/redis-server.log
```

### Alert Thresholds
- Alert if failed authentication attempts exceed 5 per minute.
- Alert on any unauthorized ACL changes.

## Production Checklist
- [ ] Ensure `requirepass` is set with a strong password.
- [ ] Implement ACLs for all users with appropriate permissions.
- [ ] Restrict Redis network access to trusted IPs.
- [ ] Regularly review and update Redis security configurations.
- [ ] Set up monitoring and alerting for unauthorized access attempts.