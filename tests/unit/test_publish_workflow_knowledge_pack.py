from pathlib import Path

import yaml


def test_publish_workflow_builds_and_uploads_knowledge_packs():
    workflow = yaml.safe_load(Path(".github/workflows/publish-docker.yml").read_text("utf-8"))
    jobs = workflow["jobs"]

    assert "publish-knowledge-pack" in jobs
    job = jobs["publish-knowledge-pack"]

    assert job["services"]["redis"]["image"] == "redis:8"

    step_names = [step.get("name", "") for step in job["steps"]]
    assert "Build standard knowledge pack" in step_names
    assert "Build air-gap knowledge pack" in step_names
    assert "Smoke-test knowledge pack restores" in step_names
    assert "Upload knowledge-pack workflow artifacts" in step_names
    assert "Upload knowledge packs to release" in step_names
