import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Button, Card, CardContent } from "@radar/ui-kit";
import { ConfirmDialog } from "../components/Modal";
import sreAgentApi, {
  CreateClusterRequest,
  RedisCluster,
  UpdateClusterRequest,
} from "../services/sreAgentApi";

const Loader = ({ size = "md" }: { size?: "sm" | "md" | "lg" }) => (
  <div
    className={`animate-spin rounded-full border-2 border-redis-blue-03 border-t-transparent ${
      size === "sm" ? "h-4 w-4" : size === "lg" ? "h-8 w-8" : "h-6 w-6"
    }`}
  />
);

const ErrorMessage = ({
  message,
  title,
}: {
  message: string;
  title?: string;
}) => (
  <div className="bg-red-50 border border-red-200 rounded-redis-sm p-4">
    {title && <h4 className="font-semibold text-red-800 mb-2">{title}</h4>}
    <p className="text-red-700 text-redis-sm">{message}</p>
  </div>
);

const getClusterTypeLabel = (clusterType?: string) => {
  switch (clusterType) {
    case "redis_enterprise":
      return "Redis Enterprise";
    case "redis_cloud":
      return "Redis Cloud";
    case "oss_cluster":
      return "OSS Cluster";
    default:
      return "Unknown";
  }
};

const getEnvironmentColor = (environment: string) => {
  switch (environment) {
    case "production":
      return "bg-redis-red text-white";
    case "staging":
      return "bg-redis-yellow-500 text-redis-midnight";
    case "development":
      return "bg-redis-blue-03 text-white";
    default:
      return "bg-redis-dusk-06 text-white";
  }
};

interface ClusterFormProps {
  initialData?: RedisCluster;
  onCancel: () => void;
  onSubmit: (
    cluster: CreateClusterRequest | UpdateClusterRequest,
  ) => Promise<void>;
}

const ClusterForm = ({ initialData, onCancel, onSubmit }: ClusterFormProps) => {
  const [formData, setFormData] = useState({
    name: initialData?.name || "",
    clusterType: initialData?.cluster_type || "unknown",
    environment: initialData?.environment || "development",
    description: initialData?.description || "",
    notes: initialData?.notes || "",
    adminUrl: initialData?.admin_url || "",
    adminUsername: initialData?.admin_username || "",
    adminPassword: initialData?.admin_password || "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");

    if (!formData.name.trim()) {
      setFormError("Cluster name is required.");
      return;
    }
    if (!formData.description.trim()) {
      setFormError("Cluster description is required.");
      return;
    }
    if (
      formData.clusterType === "redis_enterprise" &&
      (!formData.adminUrl.trim() ||
        !formData.adminUsername.trim() ||
        !formData.adminPassword.trim())
    ) {
      setFormError("Redis Enterprise clusters require admin API credentials.");
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        name: formData.name.trim(),
        cluster_type:
          formData.clusterType as CreateClusterRequest["cluster_type"],
        environment: formData.environment,
        description: formData.description.trim(),
        notes: formData.notes.trim() || undefined,
        admin_url: formData.adminUrl.trim() || undefined,
        admin_username: formData.adminUsername.trim() || undefined,
        admin_password: formData.adminPassword.trim() || undefined,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {formError && <ErrorMessage message={formError} title="Cluster Error" />}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Cluster Name
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(event) =>
              setFormData((prev) => ({ ...prev, name: event.target.value }))
            }
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          />
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Environment
          </label>
          <select
            value={formData.environment}
            onChange={(event) =>
              setFormData((prev) => ({
                ...prev,
                environment: event.target.value,
              }))
            }
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          >
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Cluster Type
          </label>
          <select
            value={formData.clusterType}
            onChange={(event) =>
              setFormData((prev) => ({
                ...prev,
                clusterType: event.target.value,
              }))
            }
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          >
            <option value="unknown">Unknown</option>
            <option value="oss_cluster">OSS Cluster</option>
            <option value="redis_enterprise">Redis Enterprise</option>
            <option value="redis_cloud">Redis Cloud</option>
          </select>
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Admin API URL
          </label>
          <input
            type="url"
            value={formData.adminUrl}
            onChange={(event) =>
              setFormData((prev) => ({ ...prev, adminUrl: event.target.value }))
            }
            placeholder="https://cluster.example.com:9443"
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          />
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Admin Username
          </label>
          <input
            type="text"
            value={formData.adminUsername}
            onChange={(event) =>
              setFormData((prev) => ({
                ...prev,
                adminUsername: event.target.value,
              }))
            }
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          />
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-foreground mb-2">
            Admin Password
          </label>
          <input
            type="password"
            value={formData.adminPassword}
            onChange={(event) =>
              setFormData((prev) => ({
                ...prev,
                adminPassword: event.target.value,
              }))
            }
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          />
        </div>
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-foreground mb-2">
          Description
        </label>
        <textarea
          value={formData.description}
          onChange={(event) =>
            setFormData((prev) => ({
              ...prev,
              description: event.target.value,
            }))
          }
          rows={3}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
        />
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-foreground mb-2">
          Notes
        </label>
        <textarea
          value={formData.notes}
          onChange={(event) =>
            setFormData((prev) => ({ ...prev, notes: event.target.value }))
          }
          rows={2}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
        />
      </div>

      <div className="flex justify-end gap-3">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          disabled={isSubmitting}
        >
          {initialData ? "Update Cluster" : "Add Cluster"}
        </Button>
      </div>
    </form>
  );
};

const Clusters = () => {
  const [clusters, setClusters] = useState<RedisCluster[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selectedEnvironment, setSelectedEnvironment] = useState("all");
  const [selectedType, setSelectedType] = useState("all");
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingCluster, setEditingCluster] = useState<RedisCluster | null>(
    null,
  );
  const [deletingCluster, setDeletingCluster] = useState<RedisCluster | null>(
    null,
  );

  const loadClusters = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const response = await sreAgentApi.listClusters({ limit: 1000 });
      setClusters(response.clusters || []);
    } catch (err) {
      setClusters([]);
      setError(
        err instanceof Error ? err.message : "Failed to load Redis clusters.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClusters();
  }, [loadClusters]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await loadClusters();
    setIsRefreshing(false);
  };

  const saveCluster = async (
    cluster: CreateClusterRequest | UpdateClusterRequest,
  ) => {
    setError("");
    try {
      if (editingCluster) {
        await sreAgentApi.updateCluster(editingCluster.id, cluster);
      } else {
        await sreAgentApi.createCluster(cluster as CreateClusterRequest);
      }
      setShowAddForm(false);
      setEditingCluster(null);
      await loadClusters();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save Redis cluster.",
      );
      throw err;
    }
  };

  const deleteCluster = async () => {
    if (!deletingCluster) return;
    setError("");
    try {
      await sreAgentApi.deleteCluster(deletingCluster.id);
      setDeletingCluster(null);
      await loadClusters();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete Redis cluster.",
      );
      setDeletingCluster(null);
    }
  };

  const filteredClusters = clusters.filter((cluster) => {
    const environmentMatch =
      selectedEnvironment === "all" ||
      cluster.environment === selectedEnvironment;
    const typeMatch =
      selectedType === "all" || cluster.cluster_type === selectedType;
    return environmentMatch && typeMatch;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-foreground">
            Redis Clusters
          </h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Manage cluster-level targets that the SRE agent can use for
            diagnostics and chat.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleRefresh}
            isLoading={isRefreshing}
          >
            {isRefreshing ? <Loader size="sm" /> : "Refresh"}
          </Button>
          <Button variant="primary" onClick={() => setShowAddForm(true)}>
            Add Cluster
          </Button>
        </div>
      </div>

      {error && <ErrorMessage message={error} title="Redis Clusters Error" />}

      {clusters.length > 0 && (
        <Card>
          <CardContent>
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <label className="text-redis-sm text-redis-dusk-04">
                  Environment:
                </label>
                <select
                  value={selectedEnvironment}
                  onChange={(event) =>
                    setSelectedEnvironment(event.target.value)
                  }
                  className="px-3 py-1 border rounded-redis-sm text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                >
                  <option value="all">All</option>
                  <option value="production">Production</option>
                  <option value="staging">Staging</option>
                  <option value="development">Development</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-redis-sm text-redis-dusk-04">
                  Type:
                </label>
                <select
                  value={selectedType}
                  onChange={(event) => setSelectedType(event.target.value)}
                  className="px-3 py-1 border rounded-redis-sm text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                >
                  <option value="all">All</option>
                  <option value="oss_cluster">OSS Cluster</option>
                  <option value="redis_enterprise">Redis Enterprise</option>
                  <option value="redis_cloud">Redis Cloud</option>
                  <option value="unknown">Unknown</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <div className="text-center">
              <Loader size="lg" />
              <p className="text-redis-sm text-redis-dusk-04 mt-4">
                Loading Redis clusters...
              </p>
            </div>
          </CardContent>
        </Card>
      ) : filteredClusters.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <div className="text-center max-w-md">
              <h3 className="text-redis-xl font-semibold text-foreground mb-3">
                No Redis clusters configured
              </h3>
              <p className="text-redis-sm text-redis-dusk-04 mb-6">
                Add a cluster when you want the agent to diagnose Redis
                Enterprise, Redis Cloud, or OSS cluster targets at cluster
                scope.
              </p>
              <Button
                variant="primary"
                size="lg"
                onClick={() => setShowAddForm(true)}
              >
                Add Your First Cluster
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredClusters.map((cluster) => (
            <Card
              key={cluster.id}
              className="hover:shadow-lg transition-shadow"
            >
              <CardContent>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-3 mb-2">
                      <span className="text-redis-sm font-mono text-redis-dusk-04">
                        {cluster.id}
                      </span>
                      <span
                        className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getEnvironmentColor(
                          cluster.environment,
                        )}`}
                      >
                        {cluster.environment.toUpperCase()}
                      </span>
                      <span className="px-2 py-1 rounded-redis-xs text-redis-xs font-medium bg-redis-dusk-06 text-white">
                        {getClusterTypeLabel(cluster.cluster_type)}
                      </span>
                      {cluster.status && (
                        <span className="text-redis-xs text-redis-dusk-04 capitalize">
                          {cluster.status}
                        </span>
                      )}
                    </div>
                    <h3 className="text-redis-lg font-semibold text-foreground mb-2">
                      {cluster.name}
                    </h3>
                    <p className="text-redis-sm text-redis-dusk-04 mb-3">
                      {cluster.description}
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-redis-xs text-redis-dusk-05">
                      <div>
                        <strong>Type:</strong>{" "}
                        {getClusterTypeLabel(cluster.cluster_type)}
                      </div>
                      <div>
                        <strong>Environment:</strong> {cluster.environment}
                      </div>
                      {cluster.admin_url && (
                        <div className="truncate">
                          <strong>Admin API:</strong> {cluster.admin_url}
                        </div>
                      )}
                      {cluster.version && (
                        <div>
                          <strong>Version:</strong> {cluster.version}
                        </div>
                      )}
                    </div>
                    {cluster.notes && (
                      <div className="mt-3 p-2 bg-redis-dusk-09 rounded-redis-sm text-redis-xs">
                        <span className="text-redis-dusk-04">Notes: </span>
                        <span className="text-foreground">{cluster.notes}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingCluster(cluster)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setDeletingCluster(cluster)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {(showAddForm || editingCluster) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className="rounded-redis-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
            style={{
              backgroundColor: "var(--card)",
              color: "var(--card-foreground)",
            }}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-redis-xl font-bold text-foreground">
                {editingCluster ? "Edit Redis Cluster" : "Add Redis Cluster"}
              </h2>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowAddForm(false);
                  setEditingCluster(null);
                }}
              >
                Close
              </Button>
            </div>
            <ClusterForm
              initialData={editingCluster || undefined}
              onSubmit={saveCluster}
              onCancel={() => {
                setShowAddForm(false);
                setEditingCluster(null);
              }}
            />
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={!!deletingCluster}
        title="Delete Redis Cluster"
        message={
          deletingCluster
            ? `Delete "${deletingCluster.name}"? This removes the saved cluster target, but does not delete any Redis infrastructure.`
            : ""
        }
        confirmText="Delete Cluster"
        cancelText="Cancel"
        onConfirm={deleteCluster}
        onClose={() => setDeletingCluster(null)}
        variant="danger"
      />
    </div>
  );
};

export default Clusters;
