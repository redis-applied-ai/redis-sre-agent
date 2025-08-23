# Document Enrichment Strategies for Enhanced Search

## Current Document Structure Analysis

**Existing Fields:**
- `title`: "MEMORY USAGE (Part 8)"
- `content`: Raw scraped text 
- `source`: URL
- `category`: "oss"/"enterprise"/"shared"  
- `severity`: "critical"/"high"/"medium"

**Search Limitations:**
- Generic titles don't capture semantic meaning
- Content lacks structured metadata
- Missing topical categorization
- No command-to-concept mapping

---

## Enrichment Strategy 1: **Semantic Title Enhancement**

### Problem
Current: `"MEMORY USAGE (Part 8)"` 
Missing: What this command actually does

### Solution: Generate Descriptive Titles
```python
# Enrich with semantic descriptions
enriched_title = "MEMORY USAGE - Analyze Redis key memory consumption and optimization"

# Pattern for commands:
"COMMAND_NAME - Brief description of purpose and use case"
```

### Implementation
```python
async def enrich_command_titles(doc: dict) -> dict:
    if is_redis_command(doc['title']):
        # Use LLM to generate semantic title
        prompt = f"Create a descriptive title for Redis command: {doc['title']}\nContent: {doc['content'][:500]}"
        semantic_title = await generate_semantic_title(prompt)
        doc['enriched_title'] = semantic_title
        doc['search_title'] = f"{doc['title']} - {semantic_title}"
    return doc
```

---

## Enrichment Strategy 2: **Topical Tagging & Classification**

### Problem  
Missing: Conceptual groupings like "memory management", "replication", "performance monitoring"

### Solution: Multi-level Taxonomy
```python
# Add hierarchical tags
doc['topics'] = {
    'primary': 'memory_management',
    'secondary': ['monitoring', 'optimization', 'diagnostics'],
    'use_cases': ['troubleshooting', 'performance_tuning', 'capacity_planning'],
    'redis_concepts': ['memory_usage', 'key_analysis', 'memory_optimization']
}
```

### Implementation
```python
async def classify_document_topics(doc: dict) -> dict:
    # Use LLM to extract topical classifications
    classification_prompt = f"""
    Classify this Redis documentation into topics:
    Title: {doc['title']}
    Content: {doc['content'][:1000]}
    
    Extract:
    1. Primary category (memory, performance, security, replication, etc.)
    2. Use cases (monitoring, troubleshooting, configuration, etc.) 
    3. Related Redis concepts
    4. Operational scenarios
    """
    
    topics = await extract_topics(classification_prompt)
    doc.update(topics)
    return doc
```

---

## Enrichment Strategy 3: **Cross-Reference & Related Commands**

### Problem
Commands exist in isolation - missing "see also" relationships

### Solution: Build Command Graph
```python
# Add related commands and concepts
doc['related_commands'] = ['MEMORY STATS', 'INFO memory', 'MEMORY DOCTOR']
doc['related_concepts'] = ['memory optimization', 'key eviction', 'memory fragmentation']
doc['troubleshooting_scenarios'] = ['high memory usage', 'memory leaks', 'performance issues']
```

### Implementation
```python
async def build_command_relationships(doc: dict) -> dict:
    if is_redis_command(doc['title']):
        # Extract related commands from content
        related_commands = extract_mentioned_commands(doc['content'])
        
        # Use knowledge graph to find conceptually related commands
        semantic_related = await find_semantic_relationships(doc['title'], doc['content'])
        
        doc['related_commands'] = related_commands
        doc['semantic_relationships'] = semantic_related
    return doc
```

---

## Enrichment Strategy 4: **Operational Context Enhancement**

### Problem
Missing: When/why would you use this? What problems does it solve?

### Solution: Add Operational Metadata
```python
doc['operational_context'] = {
    'when_to_use': 'When investigating high memory usage or optimizing Redis memory consumption',
    'common_scenarios': ['Memory usage alerts', 'Performance degradation', 'Capacity planning'],
    'prerequisites': ['Redis 4.0+', 'Sufficient memory for analysis'],
    'output_format': 'Bytes consumed by key',
    'performance_impact': 'Low - O(N) where N is key size'
}
```

---

## Enrichment Strategy 5: **Example & Usage Pattern Extraction**

### Problem
Raw documentation doesn't highlight practical usage patterns

### Solution: Extract Structured Examples
```python
doc['usage_examples'] = [
    {
        'command': 'MEMORY USAGE user:1000',
        'purpose': 'Check memory usage of specific user key',
        'expected_output': 'Memory in bytes'
    },
    {
        'command': 'MEMORY USAGE mykey SAMPLES 5',
        'purpose': 'Get more accurate memory estimate with sampling',
        'use_case': 'Large keys where default estimation is insufficient'
    }
]
```

---

## Implementation Approaches

### **Approach A: LLM-Based Enrichment Pipeline**

```python
class DocumentEnricher:
    async def enrich_document(self, doc: dict) -> dict:
        # 1. Generate semantic titles
        if is_command_doc(doc):
            doc = await self.enrich_command_semantics(doc)
        
        # 2. Extract topical classifications  
        doc = await self.classify_topics(doc)
        
        # 3. Build relationships
        doc = await self.extract_relationships(doc)
        
        # 4. Add operational context
        doc = await self.add_operational_context(doc)
        
        return doc
    
    async def enrich_command_semantics(self, doc: dict) -> dict:
        prompt = f"""
        Analyze this Redis command documentation and extract:
        1. One-line description of what the command does
        2. Primary use cases (3-5 scenarios)
        3. Related commands
        4. Performance characteristics
        5. Common troubleshooting scenarios where this is used
        
        Command: {doc['title']}
        Documentation: {doc['content'][:1500]}
        
        Return as structured JSON.
        """
        
        enrichment = await self.llm_extract(prompt)
        doc.update(enrichment)
        return doc
```

### **Approach B: Rule-Based + Template Enrichment**

```python
class TemplateEnricher:
    def __init__(self):
        # Predefined templates for different doc types
        self.command_templates = {
            'MEMORY_*': {
                'category': 'memory_management',
                'use_cases': ['troubleshooting', 'optimization', 'monitoring'],
                'related_concepts': ['memory fragmentation', 'eviction policies']
            },
            'CLUSTER_*': {
                'category': 'clustering', 
                'use_cases': ['cluster_management', 'scaling', 'high_availability'],
                'related_concepts': ['sharding', 'failover', 'cluster topology']
            }
        }
    
    def enrich_by_pattern(self, doc: dict) -> dict:
        command = doc['title'].upper()
        for pattern, enrichment in self.command_templates.items():
            if fnmatch.fnmatch(command, pattern):
                doc.update(enrichment)
                break
        return doc
```

---

## **Recommended Implementation Plan**

### **Phase 1: High-Impact Quick Wins** 
1. **Semantic Title Enhancement** - Use LLM to generate "COMMAND - Description" format
2. **Topical Classification** - Add primary category tags (memory, security, replication, etc.)
3. **Use Case Tagging** - Tag with common scenarios (troubleshooting, monitoring, configuration)

### **Phase 2: Relationship Mapping**
1. **Command Cross-References** - Build "related commands" mappings
2. **Concept Linking** - Connect commands to broader Redis concepts  
3. **Troubleshooting Scenarios** - Tag when/why to use each command

### **Phase 3: Advanced Enrichment**
1. **Operational Context** - Add when-to-use guidance
2. **Example Extraction** - Structure common usage patterns
3. **Performance Metadata** - Add complexity and impact information

### **Expected Impact**
- **Query Expansion**: Enriched metadata enables better query matching
- **Improved Ranking**: Semantic titles and tags improve relevance scoring
- **Better Coverage**: Operational context helps match user intent to technical docs
- **Cross-Discovery**: Related command mappings surface additional relevant results

**Estimated Improvement**: 15-25% increase in MRR/MAP scores, especially for conceptual queries like the replication example.