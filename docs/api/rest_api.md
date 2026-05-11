---
description: Auto-generated reference for the Redis SRE Agent FastAPI server.
---

# REST API reference

This page is generated from the FastAPI route tree.

For live schemas and request models, start the API and open `http://localhost:8000/docs` (local) or `http://localhost:8080/docs` (Docker Compose).

## Start here

- Health and readiness: `/`, `/api/v1/health`, `/api/v1/metrics`
- Manage Redis targets: `/api/v1/instances`, `/api/v1/clusters`
- Run agent work: `/api/v1/tasks`, `/api/v1/threads`, `/api/v1/ws/tasks/{thread_id}`
- Search and ingest knowledge: `/api/v1/knowledge/*`
- Schedule recurring checks: `/api/v1/schedules/*`
- Analyze support packages: `/api/v1/support-packages/*`

For copy/paste workflows, see [API workflows](../user_guide/how_to_guides/api_workflows.md).

## Health & readiness

| Method | Path | Summary |
|---|---|---|
| `GET` | `/` | root_health_check |
| `GET` | `/api/v1/` | root_health_check |
| `GET` | `/api/v1/health` | detailed_health_check |
| `GET` | `/api/v1/metrics` | prometheus_metrics |
| `GET` | `/api/v1/metrics/health` | metrics_health |

## Clusters

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/clusters` | list_clusters |
| `POST` | `/api/v1/clusters` | create_cluster |
| `DELETE` | `/api/v1/clusters/{cluster_id}` | delete_cluster |
| `GET` | `/api/v1/clusters/{cluster_id}` | get_cluster |
| `PUT` | `/api/v1/clusters/{cluster_id}` | update_cluster |

## Instances

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/instances` | list_instances |
| `POST` | `/api/v1/instances` | create_instance |
| `POST` | `/api/v1/instances/test-admin-api` | test_admin_api_connection |
| `POST` | `/api/v1/instances/test-connection-url` | test_connection_url |
| `DELETE` | `/api/v1/instances/{instance_id}` | delete_instance |
| `GET` | `/api/v1/instances/{instance_id}` | get_instance |
| `PUT` | `/api/v1/instances/{instance_id}` | update_instance |
| `POST` | `/api/v1/instances/{instance_id}/test-connection` | test_instance_connection |

## Knowledge

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/knowledge/ingest/document` | ingest_single_document |
| `POST` | `/api/v1/knowledge/ingest/pipeline` | start_ingestion_pipeline |
| `POST` | `/api/v1/knowledge/ingest/source-documents` | ingest_source_documents |
| `GET` | `/api/v1/knowledge/jobs` | list_jobs |
| `DELETE` | `/api/v1/knowledge/jobs/{job_id}` | cancel_job |
| `GET` | `/api/v1/knowledge/jobs/{job_id}` | get_job_status |
| `GET` | `/api/v1/knowledge/search` | search_knowledge |
| `POST` | `/api/v1/knowledge/search` | search_knowledge_post |
| `GET` | `/api/v1/knowledge/settings` | get_knowledge_settings |
| `PUT` | `/api/v1/knowledge/settings` | update_knowledge_settings |
| `POST` | `/api/v1/knowledge/settings/reset` | reset_knowledge_settings |
| `GET` | `/api/v1/knowledge/stats` | get_knowledge_base_stats |

## Schedules

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/schedules/` | list_schedules |
| `POST` | `/api/v1/schedules/` | create_schedule |
| `POST` | `/api/v1/schedules/trigger-scheduler` | trigger_scheduler |
| `DELETE` | `/api/v1/schedules/{schedule_id}` | delete_schedule |
| `GET` | `/api/v1/schedules/{schedule_id}` | get_schedule |
| `PUT` | `/api/v1/schedules/{schedule_id}` | update_schedule |
| `GET` | `/api/v1/schedules/{schedule_id}/runs` | list_schedule_runs |
| `POST` | `/api/v1/schedules/{schedule_id}/trigger` | trigger_schedule_now |

## Support packages

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/support-packages` | list_packages |
| `POST` | `/api/v1/support-packages/upload` | upload_package |
| `DELETE` | `/api/v1/support-packages/{package_id}` | delete_package |
| `GET` | `/api/v1/support-packages/{package_id}` | get_package_info |
| `POST` | `/api/v1/support-packages/{package_id}/extract` | extract_package |

## Tasks, threads, and streaming

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/tasks` | create_task_endpoint |
| `DELETE` | `/api/v1/tasks/{task_id}` | delete_task |
| `GET` | `/api/v1/tasks/{task_id}` | get_task |
| `GET` | `/api/v1/tasks/{task_id}/approvals` | list_task_approvals |
| `POST` | `/api/v1/tasks/{task_id}/resume` | resume_task |
| `GET` | `/api/v1/tasks/{thread_id}/stream-info` | get_task_stream_info |
| `GET` | `/api/v1/threads` | list_threads |
| `POST` | `/api/v1/threads` | create_thread |
| `DELETE` | `/api/v1/threads/{thread_id}` | delete_thread |
| `GET` | `/api/v1/threads/{thread_id}` | get_thread |
| `PATCH` | `/api/v1/threads/{thread_id}` | update_thread |
| `POST` | `/api/v1/threads/{thread_id}/append-messages` | append_messages |

## OpenAPI & docs

| Method | Path | Summary |
|---|---|---|
| `GET` | `/docs` | swagger_ui_html |
| `GET` | `/docs/oauth2-redirect` | swagger_ui_redirect |
| `GET` | `/openapi.json` | openapi |
| `GET` | `/redoc` | redoc_html |
