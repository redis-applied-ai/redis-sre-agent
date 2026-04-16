---
document_hash: no-live-access-communication
name: no-live-access-communication
title: No Live Access Communication
doc_type: skill
priority: high
summary: Explain lack of live access and pivot to general guidance.
source: fixture://prompt-core/skills/no-live-access-response.md
---
If the user asks for current cluster or instance state in a knowledge-only lane, say that you do not have live access to Redis here.
Offer documented troubleshooting steps or recommend switching to the full SRE agent with the relevant target attached.
