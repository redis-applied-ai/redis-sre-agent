## REST API Reference (generated)

For interactive docs, see http://localhost:8000/docs


### Endpoints


- GET / — root_health_check
- GET /api/v1/ — root_health_check
- GET /api/v1/health — detailed_health_check
- GET /api/v1/instances — list_instances
- POST /api/v1/instances — create_instance
- POST /api/v1/instances/test-admin-api — test_admin_api_connection
- POST /api/v1/instances/test-connection-url — test_connection_url
- DELETE /api/v1/instances/{instance_id} — delete_instance
- GET /api/v1/instances/{instance_id} — get_instance
- PUT /api/v1/instances/{instance_id} — update_instance
- POST /api/v1/instances/{instance_id}/test-connection — test_instance_connection
- POST /api/v1/knowledge/ingest/document — ingest_single_document
- POST /api/v1/knowledge/ingest/pipeline — start_ingestion_pipeline
- POST /api/v1/knowledge/ingest/source-documents — ingest_source_documents
- GET /api/v1/knowledge/jobs — list_jobs
- DELETE /api/v1/knowledge/jobs/{job_id} — cancel_job
- GET /api/v1/knowledge/jobs/{job_id} — get_job_status
- GET /api/v1/knowledge/search — search_knowledge
- POST /api/v1/knowledge/search — search_knowledge_post
- GET /api/v1/knowledge/settings — get_knowledge_settings
- PUT /api/v1/knowledge/settings — update_knowledge_settings
- POST /api/v1/knowledge/settings/reset — reset_knowledge_settings
- GET /api/v1/knowledge/stats — get_knowledge_base_stats
- GET /api/v1/metrics — prometheus_metrics
- GET /api/v1/metrics/health — metrics_health
- GET /api/v1/schedules/ — list_schedules
- POST /api/v1/schedules/ — create_schedule
- POST /api/v1/schedules/trigger-scheduler — trigger_scheduler
- DELETE /api/v1/schedules/{schedule_id} — delete_schedule
- GET /api/v1/schedules/{schedule_id} — get_schedule
- PUT /api/v1/schedules/{schedule_id} — update_schedule
- GET /api/v1/schedules/{schedule_id}/runs — list_schedule_runs
- POST /api/v1/schedules/{schedule_id}/trigger — trigger_schedule_now
- POST /api/v1/tasks — create_task_endpoint
- GET /api/v1/tasks/{task_id} — get_task
- GET /api/v1/tasks/{thread_id}/stream-info — get_task_stream_info
- GET /api/v1/threads — list_threads
- POST /api/v1/threads — create_thread
- DELETE /api/v1/threads/{thread_id} — delete_thread
- GET /api/v1/threads/{thread_id} — get_thread
- PATCH /api/v1/threads/{thread_id} — update_thread
- POST /api/v1/threads/{thread_id}/append-messages — append_messages
- GET /docs — swagger_ui_html
- GET /docs/oauth2-redirect — swagger_ui_redirect
- GET /openapi.json — openapi
- GET /redoc — redoc_html
