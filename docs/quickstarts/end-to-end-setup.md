# Robert notes on getting going

## hiccups
- uv perms issue => updated
- vite_api config
- set SRE_MASTER_KEY env var
- document the difference between redis and redis-demo
- not obvious ingest needs to be run
- had to recreate the index for the knowledge base to be populated
- default for everything should be 8080


## goal

The redis SRE agent monitors a redis instance and can make suggestions about how to fix it. When it comes to observability there are many different tools for monitoring such as Prometheus, Grafana, Loki, etc. The redis SRE agent is able to integrate with these tools to provide a more complete picture of what is going on with the redis instance but the central focus of these tool is to use an LLM and tools calls to be able to automatically detect and suggest fixes for redis issues.