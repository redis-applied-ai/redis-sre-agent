# Knowledge Base Retrieval Evaluation Report

**Test Cases Evaluated**: 12

## Summary Metrics

**Mean Reciprocal Rank (MRR)**: 0.875
**Mean Average Precision (MAP)**: 0.860

### Precision@K
| K | Precision@K |
|---|-------------|
| 1 | 0.750 |
| 3 | 0.861 |
| 5 | 0.850 |
| 10 | 0.767 |

### Recall@K
| K | Recall@K |
|---|----------|
| 1 | 0.226 |
| 3 | 0.679 |
| 5 | 0.972 |
| 10 | 1.000 |

### NDCG@K
| K | NDCG@K |
|---|--------|
| 1 | 0.750 |
| 3 | 0.880 |
| 5 | 0.880 |
| 10 | 0.869 |

## Individual Query Results

### Query 1: Redis memory usage commands
**Relevant Documents**: 5
**Retrieved Documents**: 10
**Reciprocal Rank**: 0.500
**Average Precision**: 0.725
**Top Retrieved:**
  1. ✗ Redis administration (Part 4)
  2. ✗ MEMORY USAGE (Part 10)
  3. ✗ MEMORY STATS (Part 8)
  4. ✗ MEMORY USAGE (Part 8)
  5. ✗ MEMORY STATS (Part 9)

### Query 2: How to check Redis latency and slow queries
**Relevant Documents**: 5
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 0.808
**Top Retrieved:**
  1. ✗ Diagnosing latency issues (Part 2)
  2. ✗ Diagnosing latency issues (Part 5)
  3. ✗ Diagnosing latency issues (Part 3)
  4. ✗ Redis Performance Latency Investigation
  5. ✗ Redis Performance Latency Investigation (Part 2)

### Query 3: Redis replication setup and configuration
**Relevant Documents**: 4
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 0.852
**Top Retrieved:**
  1. ✗ Redis replication (Part 2)
  2. ✗ Redis Replication Lag Emergency (Part 3)
  3. ✗ Redis administration (Part 8)
  4. ✗ Redis replication (Part 10)
  5. ✗ Redis replication (Part 8)

### Query 4: Redis JSON operations and search
**Relevant Documents**: 6
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 1.000
**Top Retrieved:**
  1. ✗ JSON (Part 4)
  2. ✗ Search and query (Part 3)
  3. ✗ JSON.DEL (Part 10)
  4. ✗ JSON.GET (Part 8)
  5. ✗ JSON (Part 5)

### Query 5: Redis security authentication and access control
**Relevant Documents**: 6
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 1.000
**Top Retrieved:**
  1. ✗ Redis security (Part 6)
  2. ✗ Redis security (Part 2)
  3. ✗ Redis security (Part 7)
  4. ✗ Redis Security Authentication Access Control
  5. ✗ Redis security (Part 8)

### Query 6: Redis persistence RDB and AOF configuration
**Relevant Documents**: 4
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 1.000
**Top Retrieved:**
  1. ✗ Redis persistence (Part 8)
  2. ✗ Redis persistence (Part 9)
  3. ✗ Redis persistence (Part 3)
  4. ✗ Redis persistence (Part 5)
  5. ✗ CONFIG SET (Part 10)

### Query 7: Redis cluster information and node management
**Relevant Documents**: 3
**Retrieved Documents**: 10
**Reciprocal Rank**: 0.500
**Average Precision**: 0.646
**Top Retrieved:**
  1. ✗ Redis Cluster Split-Brain Network Partition (Part 3)
  2. ✗ CLUSTER NODES (Part 10)
  3. ✗ CLUSTER INFO (Part 8)
  4. ✗ CLUSTER INFO (Part 9)
  5. ✗ Redis replication (Part 2)

### Query 8: Redis hash operations HSET HGET
**Relevant Documents**: 5
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 0.769
**Top Retrieved:**
  1. ✗ HMGET (Part 9)
  2. ✗ Memory optimization (Part 8)
  3. ✗ HGET (Part 9)
  4. ✗ HGET (Part 8)
  5. ✗ HMGET (Part 10)

### Query 9: Redis list operations push and pop
**Relevant Documents**: 5
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 1.000
**Top Retrieved:**
  1. ✗ LPOP (Part 9)
  2. ✗ RPOP (Part 9)
  3. ✗ RPOP (Part 8)
  4. ✗ LPOP (Part 8)
  5. ✗ RPUSH (Part 9)

### Query 10: Redis key expiration and TTL management
**Relevant Documents**: 4
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 0.921
**Top Retrieved:**
  1. ✗ EXPIRE (Part 8)
  2. ✗ TTL (Part 9)
  3. ✗ EXPIRE (Part 10)
  4. ✗ EXPIRE (Part 9)
  5. ✗ TTL (Part 8)

### Query 11: Redis full-text search index creation and querying
**Relevant Documents**: 4
**Retrieved Documents**: 10
**Reciprocal Rank**: 0.500
**Average Precision**: 0.630
**Top Retrieved:**
  1. ✗ FT.SEARCH (Part 10)
  2. ✗ Search and query (Part 3)
  3. ✗ Search and query (Part 4)
  4. ✗ FT.SEARCH (Part 9)
  5. ✗ Search and query (Part 5)

### Query 12: Redis set operations add and check membership
**Relevant Documents**: 4
**Retrieved Documents**: 10
**Reciprocal Rank**: 1.000
**Average Precision**: 0.963
**Top Retrieved:**
  1. ✗ SISMEMBER (Part 8)
  2. ✗ SISMEMBER (Part 9)
  3. ✗ SMEMBERS (Part 8)
  4. ✗ SADD (Part 8)
  5. ✗ SMEMBERS (Part 9)
