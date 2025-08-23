# Redis Streams Consumer Group Lag Crisis

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Consumer group lag exceeds 2.5 million messages.
- Application queues are backing up.
- Increased latency in message processing.
- Potential client connection errors due to backlog.

## Root Cause Analysis

### 1. Analyze Consumer Group Lag
```bash
redis-cli XINFO GROUPS <stream_name>
# Look for the 'lag' field in the output. High values indicate that consumers are not keeping up with the message production rate.
```

### 2. Check Pending Messages
```bash
redis-cli XPENDING <stream_name> <group_name>
# Review the 'count' of pending messages. A high count suggests that messages are not being acknowledged by consumers.
```

## Immediate Remediation

### Option 1: Scale Consumers
```bash
# Increase the number of consumers in the group to parallelize processing.
# Ensure that each consumer is processing a unique subset of messages.
```

### Option 2: Optimize Consumer Processing
1. Review consumer application logic for inefficiencies.
2. Ensure consumers are acknowledging messages promptly.
3. Consider increasing the processing power of consumer instances.

## Long-term Prevention

### 1. Implement Stream Trimming
- Use the `XTRIM` command to limit the length of the stream and prevent excessive backlog.
```bash
redis-cli XTRIM <stream_name> MAXLEN ~ <max_length>
# This will trim the stream to approximately <max_length> messages.
```

### 2. Enhance Consumer Parallelism
- Design consumers to handle messages in parallel, leveraging multi-threading or asynchronous processing where applicable.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor consumer group lag
redis-cli XINFO GROUPS <stream_name> | grep lag

# Monitor pending messages
redis-cli XPENDING <stream_name> <group_name> | grep count
```

### Alert Thresholds
- Alert if consumer group lag exceeds 1 million messages.
- Alert if pending messages remain unacknowledged for more than 5 minutes.

## Production Checklist
- [ ] Verify that all consumers are running and healthy.
- [ ] Ensure that stream trimming is configured to prevent excessive backlog.
- [ ] Confirm that monitoring and alerting are set up for consumer lag and pending messages.
- [ ] Review and optimize consumer application logic for efficiency.

Focus on practical, production-ready guidance with specific commands, thresholds, and procedures.