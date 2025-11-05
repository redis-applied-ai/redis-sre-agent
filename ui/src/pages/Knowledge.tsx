import { useState, useEffect } from "react";
import { Card, CardHeader, CardContent, Button } from "@radar/ui-kit";

interface KnowledgeStats {
  total_documents: number;
  total_chunks: number;
  last_ingestion: string | null;
  ingestion_status: "idle" | "running" | "error";
  document_types: Record<string, number>;
  storage_size_mb: number;
}

interface SearchResult {
  title: string;
  content: string;
  source: string;
  category: string;
  severity: string;
  score?: number;
}

interface SearchResponse {
  query: string;
  category_filter?: string;
  results_count: number;
  results: SearchResult[];
  formatted_output: string;
}

interface IngestionJob {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  documents_processed: number;
  total_documents: number;
  started_at: string;
  completed_at?: string;
  error_message?: string;
  config: IngestionConfig;
}

interface IngestionConfig {
  chunk_size: number;
  chunk_overlap: number;
  splitting_strategy: "recursive" | "semantic" | "fixed";
  embedding_model: string;
  source_type: "file" | "url" | "text";
  source_path?: string;
  source_urls?: string[];
  source_text?: string;
}

const Knowledge = () => {
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showIngestionForm, setShowIngestionForm] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchCategory, setSearchCategory] = useState("");
  const [expandedResults, setExpandedResults] = useState<Set<number>>(
    new Set(),
  );
  const [distanceThreshold, setDistanceThreshold] = useState<number>(2.0);

  // Simple ingestion form state
  const [ingestionText, setIngestionText] = useState("");

  useEffect(() => {
    // Check for search query in URL parameters
    const urlParams = new URLSearchParams(
      window.location.hash.split("?")[1] || "",
    );
    const searchParam = urlParams.get("search");
    if (searchParam) {
      setSearchQuery(searchParam);
      // Trigger search after data loads
      setTimeout(() => {
        handleSearch(searchParam);
      }, 500);
    }

    // Add a small delay to ensure the dev server proxy is ready
    const timer = setTimeout(() => {
      loadKnowledgeData();
    }, 100);

    // Set up polling for ingestion status
    const interval = setInterval(loadKnowledgeData, 5000);

    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, []);

  const loadKnowledgeData = async () => {
    try {
      setError(null);

      console.log("Loading knowledge data...");

      // Load real knowledge base data
      const [statsResponse, jobsResponse] = await Promise.all([
        fetch("/api/v1/knowledge/stats"),
        fetch("/api/v1/knowledge/jobs"),
      ]);

      console.log("Response status:", {
        stats: statsResponse.status,
        jobs: jobsResponse.status,
      });

      if (!statsResponse.ok || !jobsResponse.ok) {
        const errorDetails = {
          stats: statsResponse.ok
            ? "OK"
            : `${statsResponse.status} ${statsResponse.statusText}`,
          jobs: jobsResponse.ok
            ? "OK"
            : `${jobsResponse.status} ${jobsResponse.statusText}`,
        };
        throw new Error(
          `Failed to load knowledge data: ${JSON.stringify(errorDetails)}`,
        );
      }

      const [statsData, jobsData] = await Promise.all([
        statsResponse.json(),
        jobsResponse.json(),
      ]);

      console.log("Data loaded successfully:", { statsData, jobsData });

      setStats(statsData);
      setIngestionJobs(jobsData.jobs || []);
    } catch (err) {
      console.error("Error loading knowledge data:", err);
      setError(err instanceof Error ? err.message : "Unknown error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  const startIngestion = async () => {
    if (!ingestionText.trim()) {
      setError("Please enter some text to ingest");
      return;
    }

    try {
      const response = await fetch("/api/v1/knowledge/ingest/document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "User Added Content",
          content: ingestionText,
          source: "web_ui",
          category: "general",
          severity: "info",
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to ingest document");
      }

      const result = await response.json();
      console.log("Ingestion result:", result);

      setShowIngestionForm(false);
      setIngestionText("");
      loadKnowledgeData(); // Refresh data
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to ingest document",
      );
    }
  };

  const searchKnowledgeBase = async (
    query?: string,
    thresholdOverride?: number,
  ) => {
    const queryToUse = query || searchQuery;
    if (!queryToUse.trim()) {
      setSearchResults([]);
      return;
    }

    try {
      setIsSearching(true);
      setError(null);

      const thresholdToUse =
        typeof thresholdOverride === "number"
          ? thresholdOverride
          : distanceThreshold;
      const params = new URLSearchParams({
        query: queryToUse,
        limit: "10",
        distance_threshold: String(thresholdToUse),
      });

      if (searchCategory) {
        params.append("category", searchCategory);
      }

      const response = await fetch(`/api/v1/knowledge/search?${params}`);

      if (!response.ok) {
        throw new Error("Failed to search knowledge base");
      }

      const result: SearchResponse = await response.json();
      console.log("Search result:", result);

      setSearchResults(result.results || []);
      setExpandedResults(new Set()); // Clear expanded state on new search
    } catch (err) {
      console.error("Search error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to search knowledge base",
      );
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    searchKnowledgeBase(query);
  };

  // Trigger search when query changes
  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    if (value.trim()) {
      // Debounce search
      const timer = setTimeout(() => {
        searchKnowledgeBase();
      }, 500);
      return () => clearTimeout(timer);
    } else {
      setSearchResults([]);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-redis-blue-03 mx-auto"></div>
          <p className="mt-2 text-redis-dusk-04">Loading knowledge base...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">
            Knowledge Base
          </h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Manage documents, monitor ingestion, and configure knowledge base
            settings.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={loadKnowledgeData}
            disabled={isLoading}
          >
            {isLoading ? "Loading..." : "Refresh"}
          </Button>
          <Button variant="primary" onClick={() => setShowIngestionForm(true)}>
            Add Content
          </Button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                Knowledge Base Error
              </h3>
              <div className="mt-2 text-sm text-red-700">
                <p>{error}</p>
              </div>
              <div className="mt-4">
                <Button
                  variant="outline"
                  onClick={() => setError(null)}
                  className="text-red-800 border-red-300 hover:bg-red-50"
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Knowledge Base Statistics */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-redis-sm text-redis-dusk-04">
                    Total Documents
                  </p>
                  <p className="text-redis-2xl font-bold text-redis-dusk-01">
                    {stats.total_documents}
                  </p>
                </div>
                <div className="h-12 w-12 bg-redis-blue-03 rounded-redis-lg flex items-center justify-center">
                  <svg
                    className="h-6 w-6 text-white"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                  </svg>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-redis-sm text-redis-dusk-04">
                    Total Chunks
                  </p>
                  <p className="text-redis-2xl font-bold text-redis-dusk-01">
                    {stats.total_chunks}
                  </p>
                </div>
                <div className="h-12 w-12 bg-redis-green-03 rounded-redis-lg flex items-center justify-center">
                  <svg
                    className="h-6 w-6 text-white"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3M19,19H5V5H19V19Z" />
                  </svg>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-redis-sm text-redis-dusk-04">
                    Storage Size
                  </p>
                  <p className="text-redis-2xl font-bold text-redis-dusk-01">
                    {stats.storage_size_mb.toFixed(1)} MB
                  </p>
                </div>
                <div className="h-12 w-12 bg-redis-orange-03 rounded-redis-lg flex items-center justify-center">
                  <svg
                    className="h-6 w-6 text-white"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z" />
                  </svg>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-redis-sm text-redis-dusk-04">
                    Ingestion Status
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        stats.ingestion_status === "running"
                          ? "bg-yellow-100 text-yellow-800"
                          : stats.ingestion_status === "error"
                            ? "bg-red-100 text-red-800"
                            : "bg-green-100 text-green-800"
                      }`}
                    >
                      {stats.ingestion_status}
                    </span>
                  </div>
                </div>
                <div className="h-12 w-12 bg-redis-purple-03 rounded-redis-lg flex items-center justify-center">
                  <svg
                    className="h-6 w-6 text-white"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z" />
                  </svg>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Simple Ingestion Form */}
      {showIngestionForm && (
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              Add Content to Knowledge Base
            </h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-redis-dusk-01 mb-2">
                  Text Content
                </label>
                <textarea
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-md focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  rows={6}
                  placeholder="Paste your text content here..."
                  value={ingestionText}
                  onChange={(e) => setIngestionText(e.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowIngestionForm(false);
                    setIngestionText("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={startIngestion}
                  disabled={!ingestionText.trim()}
                >
                  Add to Knowledge Base
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ingestion Jobs */}
      {ingestionJobs.length > 0 && (
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              Recent Ingestion Jobs
            </h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {ingestionJobs.slice(0, 5).map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-md"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        job.status === "running"
                          ? "bg-yellow-100 text-yellow-800"
                          : job.status === "failed"
                            ? "bg-red-100 text-red-800"
                            : job.status === "completed"
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {job.status}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-redis-dusk-01">
                        {job.config?.source_type || "text"} ingestion
                      </p>
                      <p className="text-xs text-redis-dusk-04">
                        Started {new Date(job.started_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    {job.status === "running" && (
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-redis-blue-03 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${job.progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-redis-dusk-04">
                          {job.progress}%
                        </span>
                      </div>
                    )}
                    {job.status === "completed" && (
                      <p className="text-xs text-redis-dusk-04">
                        {job.documents_processed} documents processed
                      </p>
                    )}
                    {job.status === "failed" && job.error_message && (
                      <p className="text-xs text-red-500 max-w-48 truncate">
                        {job.error_message}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Knowledge Base Search */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              Search Knowledge Base
            </h3>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex gap-2 items-center">
              <input
                type="text"
                placeholder="Search knowledge base..."
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                className="flex-1 px-3 py-2 border border-redis-dusk-06 rounded-md focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
              />
              <select
                value={searchCategory}
                onChange={(e) => setSearchCategory(e.target.value)}
                className="px-3 py-2 border border-redis-dusk-06 rounded-md focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
              >
                <option value="">All Categories</option>
                <option value="general">General</option>
                <option value="troubleshooting">Troubleshooting</option>
                <option value="configuration">Configuration</option>
                <option value="performance">Performance</option>
                <option value="security">Security</option>
              </select>
              <div className="hidden md:flex items-center gap-2 w-64 px-2">
                <span className="text-xs text-redis-dusk-04 whitespace-nowrap">
                  Threshold: {distanceThreshold.toFixed(2)}
                </span>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={distanceThreshold}
                  aria-label="Vector distance threshold"
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    setDistanceThreshold(v);
                    if (searchQuery.trim()) {
                      // Re-run search with the updated threshold
                      void searchKnowledgeBase(undefined, v);
                    }
                  }}
                  className="w-full"
                />
              </div>
              <Button
                variant="primary"
                onClick={() => searchKnowledgeBase()}
                disabled={isSearching || !searchQuery.trim()}
              >
                {isSearching ? "Searching..." : "Search"}
              </Button>
            </div>

            {isSearching && (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-redis-blue-03"></div>
                <span className="ml-2 text-redis-dusk-04">
                  Searching knowledge base...
                </span>
              </div>
            )}

            {!isSearching && searchResults.length === 0 && searchQuery && (
              <div className="text-center py-8">
                <p className="text-redis-dusk-04">
                  No results found for "{searchQuery}"
                </p>
                <p className="text-redis-dusk-04 text-sm mt-1">
                  Try different keywords or add content to the knowledge base
                </p>
              </div>
            )}

            {!isSearching && searchResults.length === 0 && !searchQuery && (
              <div className="text-center py-8">
                <p className="text-redis-dusk-04">
                  Enter a search query to find relevant information
                </p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => setShowIngestionForm(true)}
                >
                  Add content to knowledge base
                </Button>
              </div>
            )}

            {searchResults.length > 0 && (
              <div className="space-y-4">
                <p className="text-sm text-redis-dusk-04">
                  Found {searchResults.length} results for "{searchQuery}"
                </p>
                {searchResults.map((result, index) => (
                  <div
                    key={index}
                    className="p-4 border border-redis-dusk-06 rounded-md hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="text-sm font-medium text-redis-dusk-01">
                        {result.title}
                      </h4>
                      <div className="flex gap-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {result.category}
                        </span>
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            result.severity === "critical"
                              ? "bg-red-100 text-red-800"
                              : result.severity === "warning"
                                ? "bg-yellow-100 text-yellow-800"
                                : "bg-green-100 text-green-800"
                          }`}
                        >
                          {result.severity}
                        </span>
                        {result.score && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            {(result.score * 100).toFixed(0)}% match
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-sm text-redis-dusk-01 mb-2">
                      <p
                        className={
                          expandedResults.has(index) ? "" : "line-clamp-4"
                        }
                      >
                        {result.content}
                      </p>
                      {result.content.length > 200 && (
                        <button
                          className="text-xs text-redis-blue-03 hover:text-redis-blue-02 font-medium mt-1"
                          onClick={() => {
                            const newExpanded = new Set(expandedResults);
                            if (expandedResults.has(index)) {
                              newExpanded.delete(index);
                            } else {
                              newExpanded.add(index);
                            }
                            setExpandedResults(newExpanded);
                          }}
                        >
                          {expandedResults.has(index)
                            ? "Show less"
                            : "Show more..."}
                        </button>
                      )}
                    </div>
                    <p className="text-xs text-redis-dusk-04">
                      Source: {result.source}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Knowledge;
