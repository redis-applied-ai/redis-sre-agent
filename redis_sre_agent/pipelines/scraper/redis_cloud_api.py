"""Scraper for Redis Cloud API documentation from Swagger/OpenAPI specs."""

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper, DocumentCategory, DocumentType, ScrapedDocument, SeverityLevel

logger = logging.getLogger(__name__)


class RedisCloudAPIScraper(BaseScraper):
    """Scraper for Redis Cloud API documentation from Swagger/OpenAPI specifications."""

    def __init__(self, storage, config: Optional[Dict[str, Any]] = None):
        super().__init__(storage, config)

        # Default configuration
        self.config = {
            "swagger_ui_url": "https://api.redislabs.com/v1/swagger-ui/index.html",
            "swagger_json_url": "https://api.redislabs.com/v1/api-docs",
            "timeout": 30,
            "delay_between_requests": 1.0,
            **self.config,
        }

        self.session: Optional[aiohttp.ClientSession] = None

    def get_source_name(self) -> str:
        return "redis_cloud_api"

    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape Redis Cloud API documentation."""
        documents = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config["timeout"])
        ) as session:
            self.session = session

            # Try to get the OpenAPI/Swagger JSON spec
            try:
                swagger_doc = await self._fetch_swagger_spec()
                if swagger_doc:
                    api_docs = await self._process_swagger_spec(swagger_doc)
                    documents.extend(api_docs)
                    self.logger.info(f"Processed {len(api_docs)} API endpoints from Swagger spec")
                else:
                    self.logger.warning("Could not fetch Swagger spec, falling back to UI scraping")
                    # Fallback to scraping the Swagger UI page
                    ui_docs = await self._scrape_swagger_ui()
                    documents.extend(ui_docs)

            except Exception as e:
                self.logger.error(f"Failed to scrape Redis Cloud API docs: {e}")

        self.logger.info(f"Scraped {len(documents)} Redis Cloud API documentation pages")
        return documents

    async def _fetch_swagger_spec(self) -> Optional[Dict[str, Any]]:
        """Fetch the OpenAPI/Swagger JSON specification."""
        try:
            async with self.session.get(self.config["swagger_json_url"]) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.warning(f"HTTP {response.status} for Swagger JSON: {self.config['swagger_json_url']}")
                    return None
        except Exception as e:
            self.logger.error(f"Failed to fetch Swagger JSON: {e}")
            return None

    async def _process_swagger_spec(self, swagger_doc: Dict[str, Any]) -> List[ScrapedDocument]:
        """Process OpenAPI/Swagger specification into documentation."""
        documents = []

        # Extract basic API info
        info = swagger_doc.get("info", {})
        api_title = info.get("title", "Redis Cloud API")
        api_version = info.get("version", "v1")
        api_description = info.get("description", "Redis Cloud Management API")

        # Create overview document
        overview_content = f"""# {api_title} {api_version}

{api_description}

## Base URL
{swagger_doc.get('host', 'api.redislabs.com')}{swagger_doc.get('basePath', '/v1')}

## Authentication
{self._extract_auth_info(swagger_doc)}

## Available Endpoints
{self._create_endpoints_summary(swagger_doc)}
"""

        overview_doc = ScrapedDocument(
            title=f"{api_title} Overview",
            content=overview_content,
            source_url=self.config["swagger_json_url"],
            category=DocumentCategory.ENTERPRISE,
            doc_type=DocumentType.REFERENCE,
            severity=SeverityLevel.HIGH,
            metadata={
                "api_version": api_version,
                "doc_type": "api_overview",
                "scraped_from": "redis_cloud_api_scraper",
            },
        )
        documents.append(overview_doc)

        # Process each endpoint
        paths = swagger_doc.get("paths", {})
        for path, methods in paths.items():
            for method, operation in methods.items():
                if isinstance(operation, dict):
                    endpoint_doc = self._create_endpoint_document(path, method, operation, swagger_doc)
                    if endpoint_doc:
                        documents.append(endpoint_doc)

        return documents

    def _extract_auth_info(self, swagger_doc: Dict[str, Any]) -> str:
        """Extract authentication information from Swagger spec."""
        security_definitions = swagger_doc.get("securityDefinitions", {})
        if not security_definitions:
            return "Authentication information not available in API specification."

        auth_info = []
        for auth_name, auth_config in security_definitions.items():
            auth_type = auth_config.get("type", "unknown")
            if auth_type == "apiKey":
                location = auth_config.get("in", "header")
                key_name = auth_config.get("name", "API-Key")
                auth_info.append(f"- **{auth_name}**: API Key in {location} as `{key_name}`")
            elif auth_type == "oauth2":
                auth_info.append(f"- **{auth_name}**: OAuth2 authentication")
            else:
                auth_info.append(f"- **{auth_name}**: {auth_type} authentication")

        return "\n".join(auth_info) if auth_info else "No authentication required."

    def _create_endpoints_summary(self, swagger_doc: Dict[str, Any]) -> str:
        """Create a summary of all available endpoints."""
        paths = swagger_doc.get("paths", {})
        summary_lines = []

        for path, methods in paths.items():
            for method, operation in methods.items():
                if isinstance(operation, dict):
                    summary = operation.get("summary", "No description")
                    summary_lines.append(f"- **{method.upper()} {path}**: {summary}")

        return "\n".join(summary_lines) if summary_lines else "No endpoints found."

    def _create_endpoint_document(
        self, path: str, method: str, operation: Dict[str, Any], swagger_doc: Dict[str, Any]
    ) -> Optional[ScrapedDocument]:
        """Create a document for a specific API endpoint."""
        try:
            operation_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")
            summary = operation.get("summary", f"{method.upper()} {path}")
            description = operation.get("description", "No description available.")

            # Build comprehensive endpoint documentation
            content = f"""# {summary}

**Endpoint**: `{method.upper()} {path}`  
**Operation ID**: `{operation_id}`

## Description
{description}

{self._format_parameters(operation.get("parameters", []))}

{self._format_responses(operation.get("responses", {}))}

{self._format_examples(operation)}
"""

            # Determine severity based on operation type
            severity = SeverityLevel.HIGH
            if method.lower() in ["get"]:
                severity = SeverityLevel.MEDIUM
            elif "delete" in method.lower():
                severity = SeverityLevel.CRITICAL

            return ScrapedDocument(
                title=f"Redis Cloud API: {summary}",
                content=content,
                source_url=f"{self.config['swagger_json_url']}#{operation_id}",
                category=DocumentCategory.ENTERPRISE,
                doc_type=DocumentType.REFERENCE,
                severity=severity,
                metadata={
                    "endpoint_path": path,
                    "http_method": method.upper(),
                    "operation_id": operation_id,
                    "doc_type": "api_endpoint",
                    "scraped_from": "redis_cloud_api_scraper",
                },
            )

        except Exception as e:
            self.logger.error(f"Failed to create document for {method} {path}: {e}")
            return None

    def _format_parameters(self, parameters: List[Dict[str, Any]]) -> str:
        """Format API parameters documentation."""
        if not parameters:
            return "## Parameters\nNo parameters required."

        param_lines = ["## Parameters"]
        for param in parameters:
            name = param.get("name", "unknown")
            param_type = param.get("type", param.get("schema", {}).get("type", "unknown"))
            location = param.get("in", "unknown")
            required = "**Required**" if param.get("required", False) else "Optional"
            description = param.get("description", "No description")

            param_lines.append(f"- **{name}** ({param_type}, {location}): {required} - {description}")

        return "\n".join(param_lines)

    def _format_responses(self, responses: Dict[str, Any]) -> str:
        """Format API responses documentation."""
        if not responses:
            return "## Responses\nNo response information available."

        response_lines = ["## Responses"]
        for status_code, response_info in responses.items():
            description = response_info.get("description", "No description")
            response_lines.append(f"- **{status_code}**: {description}")

        return "\n".join(response_lines)

    def _format_examples(self, operation: Dict[str, Any]) -> str:
        """Format examples if available."""
        # This is a placeholder - real implementation would extract examples
        # from the Swagger spec if they exist
        return "## Examples\nRefer to the Redis Cloud API documentation for usage examples."

    async def _scrape_swagger_ui(self) -> List[ScrapedDocument]:
        """Fallback method to scrape Swagger UI page if JSON spec is not available."""
        documents = []

        try:
            async with self.session.get(self.config["swagger_ui_url"]) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for Swagger UI: {self.config['swagger_ui_url']}")
                    return documents

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Extract basic information from the Swagger UI page
                title = soup.find("title")
                title_text = title.get_text() if title else "Redis Cloud API Documentation"

                # Create a basic document from the UI page
                content = f"""# {title_text}

This documentation was scraped from the Redis Cloud API Swagger UI.

**Source**: {self.config['swagger_ui_url']}

For complete API documentation, please visit the Swagger UI directly.

## Note
This is a fallback scraping method. For detailed API endpoint documentation,
the system should ideally access the OpenAPI/Swagger JSON specification directly.
"""

                doc = ScrapedDocument(
                    title=title_text,
                    content=content,
                    source_url=self.config["swagger_ui_url"],
                    category=DocumentCategory.ENTERPRISE,
                    doc_type=DocumentType.REFERENCE,
                    severity=SeverityLevel.MEDIUM,
                    metadata={
                        "doc_type": "api_ui_fallback",
                        "scraped_from": "redis_cloud_api_scraper",
                    },
                )
                documents.append(doc)

        except Exception as e:
            self.logger.error(f"Failed to scrape Swagger UI: {e}")

        return documents
