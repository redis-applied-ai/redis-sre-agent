import { useState, useEffect } from "react";
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

interface Schedule {
  id: string;
  name: string;
  description?: string;
  interval_type: string;
  interval_value: number;
  redis_instance_id?: string;
  instructions: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_run_at?: string;
  next_run_at?: string;
}

interface RedisInstance {
  id: string;
  name: string;
  connection_url: string;
  environment: string;
  usage: string;
}

interface ScheduledRun {
  id: string;
  schedule_id: string;
  status: string;
  scheduled_at: string;
  started_at?: string;
  completed_at?: string;
  triage_task_id?: string;
  error?: string;
  created_at: string;
}

const Schedules = () => {
  const navigate = useNavigate();
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [instances, setInstances] = useState<RedisInstance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [selectedScheduleRuns, setSelectedScheduleRuns] = useState<
    ScheduledRun[]
  >([]);
  const [showRunsModal, setShowRunsModal] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setError(null);
      const schedulesPromise = fetch("/api/v1/schedules/");
      const instancesPromise = sreAgentApi.listInstances();

      const [schedulesRes, instancesRes] = await Promise.allSettled([
        schedulesPromise,
        instancesPromise,
      ]);

      if (schedulesRes.status !== "fulfilled" || !schedulesRes.value.ok) {
        throw new Error("Failed to load schedules");
      }

      const schedulesData = await schedulesRes.value.json();
      setSchedules(schedulesData);

      if (instancesRes.status === "fulfilled") {
        // Map API instances to minimal shape used by this page
        const mapped = instancesRes.value.map((i: any) => ({
          id: i.id,
          name: i.name,
          connection_url: i.connection_url,
          environment: i.environment,
          usage: i.usage,
        }));
        setInstances(mapped);
      } else {
        setInstances([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateSchedule = async (formData: FormData) => {
    try {
      setError(null);
      const scheduleData = {
        name: formData.get("name") as string,
        description: (formData.get("description") as string) || undefined,
        interval_type: formData.get("interval_type") as string,
        interval_value: parseInt(formData.get("interval_value") as string),
        redis_instance_id:
          (formData.get("redis_instance_id") as string) || undefined,
        instructions: formData.get("instructions") as string,
        enabled: formData.get("enabled") === "on",
      };

      const response = await fetch("/api/v1/schedules/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(scheduleData),
      });

      if (!response.ok) {
        throw new Error("Failed to create schedule");
      }

      await loadData();
      setShowCreateForm(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create schedule",
      );
    }
  };

  const handleUpdateSchedule = async (
    scheduleId: string,
    formData: FormData,
  ) => {
    try {
      setError(null);
      const updateData = {
        name: formData.get("name") as string,
        description: (formData.get("description") as string) || undefined,
        interval_type: formData.get("interval_type") as string,
        interval_value: parseInt(formData.get("interval_value") as string),
        redis_instance_id:
          (formData.get("redis_instance_id") as string) || undefined,
        instructions: formData.get("instructions") as string,
        enabled: formData.get("enabled") === "on",
      };

      const response = await fetch(`/api/v1/schedules/${scheduleId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(updateData),
      });

      if (!response.ok) {
        throw new Error("Failed to update schedule");
      }

      await loadData();
      setEditingSchedule(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update schedule",
      );
    }
  };

  const handleDeleteSchedule = async (
    scheduleId: string,
    scheduleName: string,
  ) => {
    if (
      !confirm(
        `Are you sure you want to delete the schedule "${scheduleName}"?`,
      )
    ) {
      return;
    }

    try {
      setError(null);
      const response = await fetch(`/api/v1/schedules/${scheduleId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete schedule");
      }

      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete schedule",
      );
    }
  };

  const handleTriggerSchedule = async (scheduleId: string) => {
    try {
      setError(null);
      const response = await fetch(`/api/v1/schedules/${scheduleId}/trigger`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Failed to trigger schedule");
      }

      alert("Schedule triggered successfully!");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to trigger schedule",
      );
    }
  };

  const handleViewRuns = async (schedule: Schedule) => {
    try {
      setError(null);
      const response = await fetch(`/api/v1/schedules/${schedule.id}/runs`);

      if (!response.ok) {
        throw new Error("Failed to load schedule runs");
      }

      const runs = await response.json();
      setSelectedScheduleRuns(runs);
      setShowRunsModal(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load schedule runs",
      );
    }
  };

  const formatInterval = (type: string, value: number) => {
    const unit = value === 1 ? type.slice(0, -1) : type;
    return `Every ${value} ${unit}`;
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "pending":
        return "text-redis-yellow-500";
      case "running":
        return "text-redis-blue-03";
      case "completed":
        return "text-redis-green";
      case "failed":
        return "text-redis-red";
      default:
        return "text-muted-foreground";
    }
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-foreground">Schedules</h1>
          <p className="text-redis-sm text-muted-foreground mt-1">
            Manage automated agent runs and monitoring schedules
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateForm(true)}>
          Create Schedule
        </Button>
      </div>

      {error && <ErrorMessage message={error} title="Error" />}

      {/* Schedules List */}
      <div className="grid grid-cols-1 gap-4">
        {schedules.length === 0 ? (
          <Card>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                <div className="text-lg mb-2">📅</div>
                <div className="text-sm mb-3">No schedules configured</div>
                <Button
                  variant="outline"
                  onClick={() => setShowCreateForm(true)}
                >
                  Create First Schedule
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          schedules.map((schedule) => (
            <Card key={schedule.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h3 className="text-redis-lg font-semibold text-foreground">
                      {schedule.name}
                    </h3>
                    <span
                      className={`text-redis-xs px-2 py-1 rounded ${
                        schedule.enabled
                          ? "bg-redis-green text-white"
                          : "bg-redis-dusk-06 text-muted-foreground"
                      }`}
                    >
                      {schedule.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTriggerSchedule(schedule.id)}
                    >
                      Trigger Now
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleViewRuns(schedule)}
                    >
                      View Runs
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingSchedule(schedule)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleDeleteSchedule(schedule.id, schedule.name)
                      }
                      className="text-redis-red hover:bg-redis-red hover:text-white"
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {schedule.description && (
                    <p className="text-redis-sm text-muted-foreground">
                      {schedule.description}
                    </p>
                  )}

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-redis-sm">
                    <div>
                      <div className="font-medium text-foreground">
                        Interval
                      </div>
                      <div className="text-muted-foreground">
                        {formatInterval(
                          schedule.interval_type,
                          schedule.interval_value,
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="font-medium text-foreground">
                        Redis Instance
                      </div>
                      <div className="text-muted-foreground">
                        {schedule.redis_instance_id
                          ? instances.find(
                              (i) => i.id === schedule.redis_instance_id,
                            )?.name || "Unknown"
                          : "Any/Knowledge-only"}
                      </div>
                    </div>

                    <div>
                      <div className="font-medium text-foreground">
                        Last Run
                      </div>
                      <div className="text-muted-foreground">
                        {schedule.last_run_at
                          ? formatTimestamp(schedule.last_run_at)
                          : "Never"}
                      </div>
                    </div>

                    <div>
                      <div className="font-medium text-foreground">
                        Next Run
                      </div>
                      <div className="text-muted-foreground">
                        {schedule.next_run_at
                          ? formatTimestamp(schedule.next_run_at)
                          : "Not scheduled"}
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="font-medium text-foreground text-redis-sm mb-1">
                      Instructions
                    </div>
                    <div className="text-redis-sm text-muted-foreground bg-redis-dusk-09 p-3 rounded">
                      {schedule.instructions}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Create Schedule Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className="rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto"
            style={{
              backgroundColor: "var(--card)",
              color: "var(--card-foreground)",
            }}
          >
            <h3
              className="text-lg font-semibold mb-4"
              style={{ color: "var(--foreground)" }}
            >
              Create New Schedule
            </h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                handleCreateSchedule(formData);
              }}
            >
              <div className="space-y-4">
                <div>
                  <label
                    className="block text-redis-sm font-medium mb-2"
                    style={{ color: "var(--foreground)" }}
                  >
                    Schedule Name *
                  </label>
                  <input
                    type="text"
                    name="name"
                    required
                    className="w-full px-3 py-2 border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    style={{
                      backgroundColor: "var(--input)",
                      color: "var(--input-foreground)",
                      borderColor: "var(--border)",
                    }}
                    placeholder="e.g., Daily Health Check"
                  />
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Description
                  </label>
                  <input
                    type="text"
                    name="description"
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    placeholder="Optional description"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-redis-sm font-medium text-foreground mb-2">
                      Interval Type *
                    </label>
                    <select
                      name="interval_type"
                      required
                      className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    >
                      <option value="minutes">Minutes</option>
                      <option value="hours">Hours</option>
                      <option value="days">Days</option>
                      <option value="weeks">Weeks</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-redis-sm font-medium text-foreground mb-2">
                      Interval Value *
                    </label>
                    <input
                      type="number"
                      name="interval_value"
                      min="1"
                      required
                      className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                      placeholder="e.g., 30"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Redis Instance
                  </label>
                  <select
                    name="redis_instance_id"
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  >
                    <option value="">Any/Knowledge-only queries</option>
                    {instances.length === 0
                      ? null
                      : instances.map((instance) => (
                          <option key={instance.id} value={instance.id}>
                            {instance.name} ({instance.environment})
                          </option>
                        ))}
                  </select>
                  {instances.length === 0 && (
                    <div className="text-redis-xs text-muted-foreground mt-1">
                      No Redis instances found. Create one on the Instances page
                      and come back.
                    </div>
                  )}
                  <p className="text-redis-xs text-muted-foreground mt-1">
                    Leave empty to allow knowledge-only queries without a
                    specific Redis instance
                  </p>
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Instructions *
                  </label>
                  <textarea
                    name="instructions"
                    required
                    rows={4}
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    placeholder="Instructions for the agent to execute..."
                  />
                  <p className="text-redis-xs text-muted-foreground mt-1">
                    Describe what the agent should do when this schedule runs
                  </p>
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    name="enabled"
                    id="create_enabled"
                    defaultChecked
                    className="h-4 w-4 text-redis-blue-03 focus:ring-redis-blue-03 border rounded"
                  />
                  <label
                    htmlFor="create_enabled"
                    className="ml-2 text-redis-sm text-foreground"
                  >
                    Enable schedule immediately
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowCreateForm(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Create Schedule
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Schedule Modal */}
      {editingSchedule && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Edit Schedule: {editingSchedule.name}
            </h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                handleUpdateSchedule(editingSchedule.id, formData);
              }}
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Schedule Name *
                  </label>
                  <input
                    type="text"
                    name="name"
                    required
                    defaultValue={editingSchedule.name}
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  />
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Description
                  </label>
                  <input
                    type="text"
                    name="description"
                    defaultValue={editingSchedule.description || ""}
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-redis-sm font-medium text-foreground mb-2">
                      Interval Type *
                    </label>
                    <select
                      name="interval_type"
                      required
                      defaultValue={editingSchedule.interval_type}
                      className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    >
                      <option value="minutes">Minutes</option>
                      <option value="hours">Hours</option>
                      <option value="days">Days</option>
                      <option value="weeks">Weeks</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-redis-sm font-medium text-foreground mb-2">
                      Interval Value *
                    </label>
                    <input
                      type="number"
                      name="interval_value"
                      min="1"
                      required
                      defaultValue={editingSchedule.interval_value}
                      className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Redis Instance
                  </label>
                  <select
                    name="redis_instance_id"
                    defaultValue={editingSchedule.redis_instance_id || ""}
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  >
                    <option value="">Any/Knowledge-only queries</option>
                    {instances.length === 0
                      ? null
                      : instances.map((instance) => (
                          <option key={instance.id} value={instance.id}>
                            {instance.name} ({instance.environment})
                          </option>
                        ))}
                  </select>
                  {instances.length === 0 && (
                    <div className="text-redis-xs text-muted-foreground mt-1">
                      No Redis instances found. Create one on the Instances page
                      and come back.
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-redis-sm font-medium text-foreground mb-2">
                    Instructions *
                  </label>
                  <textarea
                    name="instructions"
                    required
                    rows={4}
                    defaultValue={editingSchedule.instructions}
                    className="w-full px-3 py-2 border border rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                  />
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    name="enabled"
                    id="edit_enabled"
                    defaultChecked={editingSchedule.enabled}
                    className="h-4 w-4 text-redis-blue-03 focus:ring-redis-blue-03 border rounded"
                  />
                  <label
                    htmlFor="edit_enabled"
                    className="ml-2 text-redis-sm text-foreground"
                  >
                    Schedule enabled
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingSchedule(null)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Update Schedule
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Schedule Runs Modal */}
      {showRunsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">
                Schedule Runs
              </h3>
              <Button variant="outline" onClick={() => setShowRunsModal(false)}>
                Close
              </Button>
            </div>

            {selectedScheduleRuns.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <div className="text-lg mb-2">📋</div>
                <div className="text-sm">No runs found for this schedule</div>
              </div>
            ) : (
              <div className="space-y-3">
                {selectedScheduleRuns.map((run) => (
                  <div
                    key={run.id}
                    className="p-4 border border rounded-redis-sm"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span
                          className={`text-redis-sm font-medium ${getStatusColor(run.status)}`}
                        >
                          {run.status.toUpperCase()}
                        </span>
                        <span className="text-redis-sm text-muted-foreground">
                          Scheduled: {formatTimestamp(run.scheduled_at)}
                        </span>
                      </div>
                      {run.triage_task_id && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            navigate(`/triage?thread=${run.triage_task_id}`)
                          }
                        >
                          View Conversation
                        </Button>
                      )}
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-redis-sm">
                      {run.started_at && (
                        <div>
                          <div className="font-medium text-foreground">
                            Started
                          </div>
                          <div className="text-muted-foreground">
                            {formatTimestamp(run.started_at)}
                          </div>
                        </div>
                      )}

                      {run.completed_at && (
                        <div>
                          <div className="font-medium text-foreground">
                            Completed
                          </div>
                          <div className="text-muted-foreground">
                            {formatTimestamp(run.completed_at)}
                          </div>
                        </div>
                      )}

                      {run.error && (
                        <div className="md:col-span-3">
                          <div className="font-medium text-redis-red mb-1">
                            Error
                          </div>
                          <div className="text-redis-sm text-redis-red bg-redis-red bg-opacity-10 p-2 rounded">
                            {run.error}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Schedules;
