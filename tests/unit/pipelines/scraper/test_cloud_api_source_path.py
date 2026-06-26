"""Cloud API scraper assigns explicit, collision-free source_document_path values."""

from redis_sre_agent.pipelines.scraper.base import ArtifactStorage
from redis_sre_agent.pipelines.scraper.redis_cloud_api import RedisCloudAPIScraper

SWAGGER = {
    "info": {"title": "Redis Cloud API", "version": "v1", "description": "x"},
    "host": "api.redislabs.com",
    "basePath": "/v1",
    "paths": {
        "/subscriptions": {
            "get": {"operationId": "getSubs", "summary": "List subscriptions"},
            "post": {"operationId": "createSub", "summary": "Create subscription"},
        },
        "/subscriptions/{id}": {
            "get": {"operationId": "getSub", "summary": "Get subscription"},
            "delete": {"operationId": "deleteSub", "summary": "Delete subscription"},
        },
    },
}


def _scraper(tmp_path):
    return RedisCloudAPIScraper(ArtifactStorage(tmp_path / "artifacts"))


def test_endpoint_path_is_method_and_template(tmp_path):
    scraper = _scraper(tmp_path)
    doc = scraper._create_endpoint_document(
        "/subscriptions/{id}", "get", SWAGGER["paths"]["/subscriptions/{id}"]["get"], SWAGGER
    )
    assert doc.metadata["source_document_path"] == "redis-cloud-api/GET /subscriptions/{id}"


def test_endpoints_sharing_swagger_url_do_not_collide(tmp_path):
    scraper = _scraper(tmp_path)
    docs = []
    for path, methods in SWAGGER["paths"].items():
        for method, operation in methods.items():
            docs.append(scraper._create_endpoint_document(path, method, operation, SWAGGER))

    paths = [d.metadata["source_document_path"] for d in docs]
    # All endpoints share the same swagger source_url; identities must be distinct.
    assert len(paths) == 4
    assert len(set(paths)) == 4
    # And none of them collapsed onto the swagger URL host (the default would have).
    assert all(p.startswith("redis-cloud-api/") for p in paths)


def test_endpoint_identity_is_content_independent(tmp_path):
    scraper = _scraper(tmp_path)
    op = dict(SWAGGER["paths"]["/subscriptions"]["get"])
    doc_a = scraper._create_endpoint_document("/subscriptions", "get", op, SWAGGER)
    op2 = dict(op, summary="A completely different summary")
    doc_b = scraper._create_endpoint_document("/subscriptions", "get", op2, SWAGGER)
    assert (
        doc_a.metadata["source_document_path"]
        == doc_b.metadata["source_document_path"]
        == "redis-cloud-api/GET /subscriptions"
    )
