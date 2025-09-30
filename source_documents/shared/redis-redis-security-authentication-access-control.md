# Redis Security Authentication and Access Control

**Category**: shared
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Frequent unauthorized access attempts in Redis logs.
- Misconfigured or absent ACLs leading to overly permissive access.
- Redis instances accessible without authentication.

## Root Cause Analysis

### 1. Check for Unauthorized Access Attempts
```bash
grep "AUTH" /var/log/redis/redis-server.log | wc -l
# Look for a high number of failed authentication attempts indicating unauthorized access attempts.
```

### 2. Verify Current Authentication and ACL Configuration
```bash
redis-cli CONFIG GET requirepass
# Check if 'requirepass' is set. If not, Redis is not using password authentication.

redis-cli ACL LIST
# Review the current ACLs to ensure they are configured correctly and not overly permissive.
```

## Immediate Remediation

### Option 1: Enable Password Authentication
```bash
redis-cli CONFIG SET requirepass yourStrongPasswordHere
# Set a strong password for Redis authentication. Ensure this is distributed securely to all authorized users.
```

### Option 2: Configure ACLs for Access Control
1. Enable ACLs if not already enabled:
   ```bash
   redis-cli ACL SETUSER default off
   # Disable default user access to enforce ACLs.
   ```

2. Create a new user with restricted access:
   ```bash
   redis-cli ACL SETUSER limited_user on >yourStrongPasswordHere ~* +@all
   # Replace 'limited_user' and 'yourStrongPasswordHere' with appropriate values.
   ```

3. Adjust permissions as needed:
   ```bash
   redis-cli ACL SETUSER limited_user +get +set
   # Grant specific command permissions to the user.
   ```

## Long-term Prevention

### 1. Implement Strong Password Policies
- Use complex passwords with a mix of letters, numbers, and symbols.
- Regularly rotate passwords and update the `requirepass` configuration.

### 2. Regularly Audit and Update ACLs
- Schedule periodic reviews of ACL configurations to ensure they meet current security requirements.
- Remove unused users and permissions to minimize attack vectors.

## Monitoring & Alerting

### Key Metrics to Track
```bash
grep "AUTH" /var/log/redis/redis-server.log
# Monitor for failed authentication attempts.

grep "ACL" /var/log/redis/redis-server.log
# Monitor for changes to ACL configurations.
```

### Alert Thresholds
- Alert if failed authentication attempts exceed 10 per minute.
- Alert if any unauthorized ACL changes are detected.

## Production Checklist
- [ ] Ensure `requirepass` is set with a strong password.
- [ ] Verify ACLs are configured and enforced for all users.
- [ ] Implement monitoring for authentication and ACL changes.
- [ ] Conduct a security audit of Redis configurations regularly.
- [ ] Document and distribute access credentials securely.
