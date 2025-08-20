"""Two-stage data pipeline for SRE knowledge base.

Stage 1: Scraper - Collects artifacts (docs, runbooks) into dated S3 buckets/folders
Stage 2: Ingestion - Processes artifacts from dated folders into vector store

Categories: OSS, Enterprise, Shared
"""
