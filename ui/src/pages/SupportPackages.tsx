import { useState, useEffect, useRef, KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Loader,
  ErrorMessage,
} from "@radar/ui-kit";
import sreAgentApi from "../services/sreAgentApi";

interface SupportPackage {
  package_id: string;
  filename: string;
  size_bytes: number;
  uploaded_at: string;
  is_extracted: boolean;
  storage_path?: string;
  checksum?: string;
  tags: string[];
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
};

const formatTimestamp = (ts: string): string =>
  new Date(ts).toLocaleString();

const SupportPackages = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [packages, setPackages] = useState<SupportPackage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPackageId, setUploadPackageId] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const [extractingId, setExtractingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Tag editing state: packageId -> current draft input value
  const [tagInputs, setTagInputs] = useState<Record<string, string>>({});
  // Which package has its tag input open
  const [tagEditingId, setTagEditingId] = useState<string | null>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadPackages();
  }, []);

  const loadPackages = async () => {
    try {
      setError(null);
      const data = await sreAgentApi.listSupportPackages();
      setPackages(
        [...data.packages]
          .sort(
            (a, b) =>
              new Date(b.uploaded_at).getTime() -
              new Date(a.uploaded_at).getTime(),
          )
          .map((p) => ({ ...p, tags: p.tags ?? [] })),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load support packages",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;
    try {
      setIsUploading(true);
      setError(null);
      await sreAgentApi.uploadSupportPackage(
        uploadFile,
        uploadPackageId || undefined,
      );
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadPackageId("");
      await loadPackages();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to upload support package",
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleExtract = async (pkg: SupportPackage) => {
    try {
      setError(null);
      setExtractingId(pkg.package_id);
      await sreAgentApi.extractSupportPackage(pkg.package_id);
      await loadPackages();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to extract support package",
      );
    } finally {
      setExtractingId(null);
    }
  };

  const handleDelete = async (pkg: SupportPackage) => {
    if (
      !confirm(
        `Are you sure you want to delete "${pkg.filename}"? This cannot be undone.`,
      )
    )
      return;
    try {
      setError(null);
      setDeletingId(pkg.package_id);
      await sreAgentApi.deleteSupportPackage(pkg.package_id);
      await loadPackages();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete support package",
      );
    } finally {
      setDeletingId(null);
    }
  };

  const openTagInput = (packageId: string) => {
    setTagEditingId(packageId);
    setTagInputs((prev) => ({ ...prev, [packageId]: "" }));
    // Focus after render
    setTimeout(() => tagInputRef.current?.focus(), 0);
  };

  const commitTag = async (packageId: string, currentTags: string[], raw: string) => {
    const newTag = raw.trim().toLowerCase();
    setTagInputs((prev) => ({ ...prev, [packageId]: "" }));
    setTagEditingId(null);

    if (!newTag || currentTags.includes(newTag)) return;

    const newTags = [...currentTags, newTag];
    setPackages((prev) =>
      prev.map((p) => (p.package_id === packageId ? { ...p, tags: newTags } : p)),
    );
    try {
      await sreAgentApi.updateSupportPackageTags(packageId, newTags);
    } catch {
      setPackages((prev) =>
        prev.map((p) => (p.package_id === packageId ? { ...p, tags: currentTags } : p)),
      );
    }
  };

  const removeTag = async (pkg: SupportPackage, tag: string) => {
    const newTags = pkg.tags.filter((t) => t !== tag);
    // Optimistic update
    setPackages((prev) =>
      prev.map((p) =>
        p.package_id === pkg.package_id ? { ...p, tags: newTags } : p,
      ),
    );
    try {
      await sreAgentApi.updateSupportPackageTags(pkg.package_id, newTags);
    } catch {
      setPackages((prev) =>
        prev.map((p) =>
          p.package_id === pkg.package_id ? { ...p, tags: pkg.tags } : p,
        ),
      );
    }
  };

  const handleTagKeyDown = (
    e: KeyboardEvent<HTMLInputElement>,
    pkg: SupportPackage,
  ) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitTag(pkg.package_id, pkg.tags, tagInputs[pkg.package_id] ?? "");
    } else if (e.key === "Escape") {
      setTagEditingId(null);
    }
  };

  const handleAnalyze = (pkg: SupportPackage) => {
    navigate(
      `/chat?support_package_id=${encodeURIComponent(pkg.package_id)}&subject=${encodeURIComponent(`Analyze support package: ${pkg.filename}`)}`,
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-foreground">
            Support Packages
          </h1>
          <p className="text-redis-sm text-muted-foreground mt-1">
            Upload, extract, and analyze Redis support packages
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowUploadModal(true)}>
          Upload Package
        </Button>
      </div>

      {error && <ErrorMessage message={error} title="Error" />}

      {/* Package List */}
      <div className="grid grid-cols-1 gap-4">
        {packages.length === 0 ? (
          <Card>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                <div className="text-lg mb-2">📦</div>
                <div className="text-sm mb-3">No support packages uploaded</div>
                <Button
                  variant="outline"
                  onClick={() => setShowUploadModal(true)}
                >
                  Upload First Package
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          packages.map((pkg) => (
            <Card key={pkg.package_id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <h3 className="text-redis-lg font-semibold text-foreground truncate max-w-sm">
                      {pkg.filename}
                    </h3>
                    <span
                      className={`shrink-0 text-redis-xs px-2 py-1 rounded border ${
                        pkg.is_extracted
                          ? "bg-redis-green text-white border-transparent"
                          : "bg-white text-gray-600 border-gray-300"
                      }`}
                    >
                      {pkg.is_extracted ? "Extracted" : "Uploaded"}
                    </span>

                    {/* Tags inline after Extracted badge */}
                    {pkg.tags.map((tag) => (
                      <span
                        key={tag}
                        className="shrink-0 inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full text-redis-xs font-medium bg-orange-500 text-white"
                      >
                        {tag}
                        <button
                          onClick={() => removeTag(pkg, tag)}
                          aria-label={`Remove tag ${tag}`}
                          className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-white text-gray-400 hover:text-gray-600 leading-none transition-colors"
                        >
                          ×
                        </button>
                      </span>
                    ))}

                    {tagEditingId === pkg.package_id ? (
                      <span className="shrink-0 inline-flex items-center gap-1">
                        <input
                          ref={tagInputRef}
                          type="text"
                          value={tagInputs[pkg.package_id] ?? ""}
                          onChange={(e) =>
                            setTagInputs((prev) => ({
                              ...prev,
                              [pkg.package_id]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => handleTagKeyDown(e, pkg)}
                          onBlur={() => setTagEditingId(null)}
                          placeholder="new tag…"
                          className="px-2 py-0.5 text-redis-xs border rounded-full w-24 focus:outline-none focus:ring-1 focus:ring-redis-blue-03"
                          style={{
                            backgroundColor: "var(--input)",
                            color: "var(--input-foreground)",
                            borderColor: "var(--border)",
                          }}
                        />
                        <button
                          onMouseDown={(e) => {
                            e.preventDefault(); // keep input focused so blur doesn't fire
                            commitTag(pkg.package_id, pkg.tags, tagInputs[pkg.package_id] ?? "");
                          }}
                          className="text-redis-xs text-redis-green font-bold hover:opacity-70"
                          aria-label="Confirm tag"
                        >
                          ✓
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => openTagInput(pkg.package_id)}
                        className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-redis-xs border border-dashed text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
                        style={{ borderColor: "var(--border)" }}
                      >
                        + Tag
                      </button>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {!pkg.is_extracted && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleExtract(pkg)}
                        disabled={extractingId === pkg.package_id}
                      >
                        {extractingId === pkg.package_id
                          ? "Extracting…"
                          : "Extract"}
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleAnalyze(pkg)}
                      disabled={!pkg.is_extracted}
                      title={
                        !pkg.is_extracted
                          ? "Extract the package first"
                          : "Open chat with this package loaded"
                      }
                    >
                      Analyze
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDelete(pkg)}
                      disabled={deletingId === pkg.package_id}
                      className="text-redis-red hover:bg-redis-red hover:text-white"
                    >
                      {deletingId === pkg.package_id ? "Deleting…" : "Delete"}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-redis-sm">
                  <div>
                    <div className="font-medium text-foreground">Package ID</div>
                    <div
                      className="text-muted-foreground font-mono text-redis-xs truncate"
                      title={pkg.package_id}
                    >
                      {pkg.package_id}
                    </div>
                  </div>
                  <div>
                    <div className="font-medium text-foreground">Size</div>
                    <div className="text-muted-foreground">
                      {formatBytes(pkg.size_bytes)}
                    </div>
                  </div>
                  <div>
                    <div className="font-medium text-foreground">Uploaded</div>
                    <div className="text-muted-foreground">
                      {formatTimestamp(pkg.uploaded_at)}
                    </div>
                  </div>
                  {pkg.checksum && (
                    <div>
                      <div className="font-medium text-foreground">Checksum</div>
                      <div
                        className="text-muted-foreground font-mono text-redis-xs truncate"
                        title={pkg.checksum}
                      >
                        {pkg.checksum.slice(0, 16)}…
                      </div>
                    </div>
                  )}
                </div>

              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className="rounded-lg p-6 max-w-lg w-full mx-4"
            style={{
              backgroundColor: "var(--card)",
              color: "var(--card-foreground)",
            }}
          >
            <h3
              className="text-lg font-semibold mb-4"
              style={{ color: "var(--foreground)" }}
            >
              Upload Support Package
            </h3>

            <div className="space-y-4">
              <div>
                <label
                  className="block text-redis-sm font-medium mb-2"
                  style={{ color: "var(--foreground)" }}
                >
                  Package file (.tar.gz) *
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".tar.gz,.tgz,.gz,.zip"
                  className="hidden"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                />
                <div
                  className="flex items-center gap-3 w-full px-3 py-2 border rounded-redis-sm text-redis-sm"
                  style={{
                    backgroundColor: "var(--input)",
                    borderColor: "var(--border)",
                  }}
                >
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploadFile ? "Change File" : "Choose File"}
                  </Button>
                  <span
                    className="truncate"
                    style={{ color: "var(--input-foreground)" }}
                  >
                    {uploadFile
                      ? `${uploadFile.name} — ${formatBytes(uploadFile.size)}`
                      : "No file selected"}
                  </span>
                </div>
              </div>

              <div>
                <label
                  className="block text-redis-sm font-medium mb-2"
                  style={{ color: "var(--foreground)" }}
                >
                  Custom Package ID{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </label>
                <input
                  type="text"
                  value={uploadPackageId}
                  onChange={(e) => setUploadPackageId(e.target.value)}
                  placeholder="Auto-generated if left empty"
                  className="w-full px-3 py-2 border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  style={{
                    backgroundColor: "var(--input)",
                    color: "var(--input-foreground)",
                    borderColor: "var(--border)",
                  }}
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowUploadModal(false);
                  setUploadFile(null);
                  setUploadPackageId("");
                }}
                disabled={isUploading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleUpload}
                disabled={!uploadFile || isUploading}
              >
                {isUploading ? "Uploading…" : "Upload"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SupportPackages;
