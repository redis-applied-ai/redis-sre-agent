import {
  useState,
  useEffect,
  createContext,
  useContext,
  useCallback,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  CollapsibleCard,
  type CollapsibleSection,
} from "@radar/ui-kit";

// Notification types
type NotificationType = "success" | "error" | "warning" | "info";

interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
  onClose?: () => void;
}

// Notification Context
const NotificationContext = createContext<{
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, "id">) => void;
  removeNotification: (id: string) => void;
  clearAll: () => void;
}>({
  notifications: [],
  addNotification: () => {},
  removeNotification: () => {},
  clearAll: () => {},
});

// Notification Provider
const NotificationProvider = ({ children }: { children: React.ReactNode }) => {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = useCallback(
    (notification: Omit<Notification, "id">) => {
      const id = Math.random().toString(36).substring(2, 9);
      const newNotification = { ...notification, id };

      setNotifications((prev) => [...prev, newNotification]);

      // Auto-remove after duration (default 5 seconds)
      if (notification.duration !== 0) {
        setTimeout(() => {
          removeNotification(id);
        }, notification.duration || 5000);
      }
    },
    [],
  );

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        addNotification,
        removeNotification,
        clearAll,
      }}
    >
      {children}
      <NotificationContainer />
    </NotificationContext.Provider>
  );
};

// Hook to use notifications
const useNotifications = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error(
      "useNotifications must be used within a NotificationProvider",
    );
  }
  return context;
};

// Individual Notification Component
const NotificationComponent = ({
  notification,
}: {
  notification: Notification;
}) => {
  const { removeNotification } = useNotifications();
  const [isVisible, setIsVisible] = useState(false);
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    // Trigger entrance animation
    const timer = setTimeout(() => setIsVisible(true), 10);
    return () => clearTimeout(timer);
  }, []);

  const handleClose = () => {
    setIsExiting(true);
    setTimeout(() => {
      removeNotification(notification.id);
      notification.onClose?.();
    }, 300);
  };

  const getTypeStyles = (type: NotificationType) => {
    switch (type) {
      case "success":
        return "border-redis-green bg-redis-green text-white";
      case "error":
        return "border-redis-red bg-redis-red text-white";
      case "warning":
        return "border-redis-yellow-500 bg-redis-yellow-500 text-black";
      case "info":
        return "border-redis-blue-03 bg-redis-blue-03 text-white";
      default:
        return "border-redis-dusk-08 bg-redis-dusk-09 text-redis-dusk-01";
    }
  };

  const getIcon = (type: NotificationType) => {
    switch (type) {
      case "success":
        return "✓";
      case "error":
        return "✕";
      case "warning":
        return "⚠";
      case "info":
        return "ℹ";
      default:
        return "•";
    }
  };

  return (
    <div
      className={`
        transform transition-all duration-300 ease-in-out border rounded-redis-sm p-4 shadow-lg
        ${getTypeStyles(notification.type)}
        ${isVisible && !isExiting ? "translate-x-0 opacity-100" : "translate-x-full opacity-0"}
        ${isExiting ? "scale-95" : ""}
      `}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
          <span className="text-sm font-bold">
            {getIcon(notification.type)}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-redis-sm font-semibold">
            {notification.title}
          </div>
          {notification.message && (
            <div className="text-redis-xs mt-1 opacity-90">
              {notification.message}
            </div>
          )}
          {notification.action && (
            <button
              onClick={notification.action.onClick}
              className="text-redis-xs font-medium underline mt-2 hover:no-underline"
            >
              {notification.action.label}
            </button>
          )}
        </div>
        <button
          onClick={handleClose}
          className={`flex-shrink-0 transition-opacity ${notification.type === "warning" ? "text-black" : "text-white"} hover:opacity-80`}
        >
          ✕
        </button>
      </div>
    </div>
  );
};

// Notification Container
const NotificationContainer = () => {
  const { notifications } = useNotifications();

  if (notifications.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm w-full">
      {notifications.map((notification) => (
        <NotificationComponent
          key={notification.id}
          notification={notification}
        />
      ))}
    </div>
  );
};

// Inline Notification Component
const InlineNotification = ({
  type,
  title,
  message,
  onClose,
  action,
  className = "",
}: {
  type: NotificationType;
  title: string;
  message?: string;
  onClose?: () => void;
  action?: { label: string; onClick: () => void };
  className?: string;
}) => {
  const getTypeStyles = (type: NotificationType) => {
    switch (type) {
      case "success":
        return "border-redis-green bg-redis-green text-white";
      case "error":
        return "border-redis-red bg-redis-red text-white";
      case "warning":
        return "border-redis-yellow-500 bg-redis-yellow-500 text-black";
      case "info":
        return "border-redis-blue-03 bg-redis-blue-03 text-white";
      default:
        return "border-redis-dusk-08 bg-redis-dusk-09";
    }
  };

  const getIcon = (type: NotificationType) => {
    switch (type) {
      case "success":
        return "✓";
      case "error":
        return "✕";
      case "warning":
        return "⚠";
      case "info":
        return "ℹ";
      default:
        return "•";
    }
  };

  return (
    <div
      className={`border rounded-redis-sm p-4 ${getTypeStyles(type)} ${className}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
          <span
            className={`text-sm font-bold ${
              type === "success"
                ? "text-redis-green"
                : type === "error"
                  ? "text-redis-red"
                  : type === "warning"
                    ? "text-redis-yellow-500"
                    : type === "info"
                      ? "text-redis-blue-03"
                      : "text-redis-dusk-01"
            }`}
          >
            {getIcon(type)}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-redis-sm font-semibold text-redis-dusk-01">
            {title}
          </div>
          {message && (
            <div className="text-redis-xs text-redis-dusk-04 mt-1">
              {message}
            </div>
          )}
          {action && (
            <button
              onClick={action.onClick}
              className={`text-redis-xs font-medium underline mt-2 hover:no-underline ${
                type === "success"
                  ? "text-redis-green"
                  : type === "error"
                    ? "text-redis-red"
                    : type === "warning"
                      ? "text-redis-yellow-500"
                      : type === "info"
                        ? "text-redis-blue-03"
                        : "text-redis-dusk-01"
              }`}
            >
              {action.label}
            </button>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="flex-shrink-0 text-redis-dusk-04 hover:text-redis-dusk-01 transition-colors"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
};

// Banner Notification Component
const BannerNotification = ({
  type,
  title,
  message,
  onClose,
  action,
}: {
  type: NotificationType;
  title: string;
  message?: string;
  onClose?: () => void;
  action?: { label: string; onClick: () => void };
}) => {
  const getTypeStyles = (type: NotificationType) => {
    switch (type) {
      case "success":
        return "bg-redis-green text-white";
      case "error":
        return "bg-redis-red text-white";
      case "warning":
        return "bg-redis-yellow-500 text-black";
      case "info":
        return "bg-redis-blue-03 text-white";
      default:
        return "bg-redis-dusk-08 text-redis-dusk-01";
    }
  };

  return (
    <div className={`px-6 py-4 ${getTypeStyles(type)}`}>
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="text-lg font-bold">
            {type === "success" && "✓"}
            {type === "error" && "✕"}
            {type === "warning" && "⚠"}
            {type === "info" && "ℹ"}
          </div>
          <div>
            <div className="text-sm font-semibold">{title}</div>
            {message && (
              <div className="text-xs opacity-90 mt-1">{message}</div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4">
          {action && (
            <button
              onClick={action.onClick}
              className="text-sm font-medium underline hover:no-underline"
            >
              {action.label}
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="text-lg hover:opacity-75 transition-opacity"
            >
              ✕
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const Notifications = () => {
  const { addNotification, clearAll, notifications } = useNotifications();
  const navigate = useNavigate();
  const [showInlineSuccess, setShowInlineSuccess] = useState(false);
  const [showInlineError, setShowInlineError] = useState(false);
  const [showInlineWarning, setShowInlineWarning] = useState(false);
  const [showInlineInfo, setShowInlineInfo] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  const toastExamplesSection: CollapsibleSection = {
    id: "toast",
    title: "Toast Notifications",
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            Toast Notification Examples
          </h4>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={clearAll}>
              Clear All
            </Button>
            <span className="text-redis-xs text-redis-dusk-04 px-3 py-2">
              Active: {notifications.length}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
                Basic Notifications
              </h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Button
                  variant="outline"
                  className="w-full text-redis-green border-redis-green"
                  onClick={() =>
                    addNotification({
                      type: "success",
                      title: "Success!",
                      message: "Your action was completed successfully.",
                    })
                  }
                >
                  Show Success Toast
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-red border-redis-red"
                  onClick={() =>
                    addNotification({
                      type: "error",
                      title: "Error occurred",
                      message: "Something went wrong. Please try again.",
                    })
                  }
                >
                  Show Error Toast
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-yellow-500 border-redis-yellow-500"
                  onClick={() =>
                    addNotification({
                      type: "warning",
                      title: "Warning",
                      message: "Please review your settings before proceeding.",
                    })
                  }
                >
                  Show Warning Toast
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-blue-03 border-redis-blue-03"
                  onClick={() =>
                    addNotification({
                      type: "info",
                      title: "Information",
                      message: "Here's some helpful information for you.",
                    })
                  }
                >
                  Show Info Toast
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
                Advanced Notifications
              </h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    addNotification({
                      type: "success",
                      title: "Deployment successful",
                      message: "Redis instance deployed to production.",
                      action: {
                        label: "View Details",
                        onClick: () => alert("Opening deployment details..."),
                      },
                    })
                  }
                >
                  With Action Button
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    addNotification({
                      type: "info",
                      title: "System update",
                      message: "Maintenance scheduled for tonight.",
                      duration: 10000,
                    })
                  }
                >
                  Extended Duration (10s)
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    addNotification({
                      type: "warning",
                      title: "Persistent warning",
                      message:
                        "This notification will stay until manually closed.",
                      duration: 0,
                    })
                  }
                >
                  Persistent (No Auto-close)
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    addNotification({
                      type: "error",
                      title: "Critical system error",
                      message:
                        "Database connection lost. Attempting to reconnect...",
                      duration: 0,
                      action: {
                        label: "Retry Now",
                        onClick: () => {
                          addNotification({
                            type: "success",
                            title: "Reconnected",
                            message: "Database connection restored.",
                          });
                        },
                      },
                    })
                  }
                >
                  Complex Notification
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
              Bulk Actions
            </h5>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  ["User created", "Email sent", "Permissions updated"].forEach(
                    (title, i) => {
                      setTimeout(() => {
                        addNotification({
                          type: "success",
                          title,
                          message: `Step ${i + 1} completed successfully.`,
                        });
                      }, i * 500);
                    },
                  );
                }}
              >
                Sequential Notifications
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  const types: NotificationType[] = [
                    "success",
                    "info",
                    "warning",
                  ];
                  types.forEach((type, i) => {
                    addNotification({
                      type,
                      title: `${type.charAt(0).toUpperCase() + type.slice(1)} notification`,
                      message: `This is a ${type} message #${i + 1}.`,
                    });
                  });
                }}
              >
                Multiple Types
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    ),
  };

  const inlineExamplesSection: CollapsibleSection = {
    id: "inline",
    title: "Inline Notifications",
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Inline Notification Examples
        </h4>
        <p className="text-redis-sm text-redis-dusk-04">
          These notifications appear inline with content and are useful for form
          validation, status updates, and contextual messages.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
                Toggle Inline Notifications
              </h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Button
                  variant={showInlineSuccess ? "primary" : "outline"}
                  className="w-full"
                  onClick={() => setShowInlineSuccess(!showInlineSuccess)}
                >
                  Toggle Success Message
                </Button>
                <Button
                  variant={showInlineError ? "primary" : "outline"}
                  className="w-full"
                  onClick={() => setShowInlineError(!showInlineError)}
                >
                  Toggle Error Message
                </Button>
                <Button
                  variant={showInlineWarning ? "primary" : "outline"}
                  className="w-full"
                  onClick={() => setShowInlineWarning(!showInlineWarning)}
                >
                  Toggle Warning Message
                </Button>
                <Button
                  variant={showInlineInfo ? "primary" : "outline"}
                  className="w-full"
                  onClick={() => setShowInlineInfo(!showInlineInfo)}
                >
                  Toggle Info Message
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-4">
            {showInlineSuccess && (
              <InlineNotification
                type="success"
                title="Form submitted successfully"
                message="Your changes have been saved and will take effect immediately."
                onClose={() => setShowInlineSuccess(false)}
                action={{
                  label: "View Changes",
                  onClick: () => alert("Viewing changes..."),
                }}
              />
            )}
            {showInlineError && (
              <InlineNotification
                type="error"
                title="Validation failed"
                message="Please fix the errors below and try again."
                onClose={() => setShowInlineError(false)}
              />
            )}
            {showInlineWarning && (
              <InlineNotification
                type="warning"
                title="Unsaved changes"
                message="You have unsaved changes that will be lost if you navigate away."
                onClose={() => setShowInlineWarning(false)}
                action={{
                  label: "Save Now",
                  onClick: () => {
                    setShowInlineWarning(false);
                    setShowInlineSuccess(true);
                  },
                }}
              />
            )}
            {showInlineInfo && (
              <InlineNotification
                type="info"
                title="New feature available"
                message="Check out our new dashboard analytics feature."
                onClose={() => setShowInlineInfo(false)}
                action={{
                  label: "Learn More",
                  onClick: () => alert("Opening feature tour..."),
                }}
              />
            )}
          </div>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
              Form Integration Example
            </h5>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                  Email Address
                </label>
                <input
                  type="email"
                  className="redis-input-base w-full"
                  placeholder="Enter your email"
                />
                <InlineNotification
                  type="error"
                  title="Invalid email format"
                  message="Please enter a valid email address."
                  className="mt-2"
                />
              </div>
              <div>
                <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                  Password
                </label>
                <input
                  type="password"
                  className="redis-input-base w-full"
                  placeholder="Enter your password"
                />
                <InlineNotification
                  type="warning"
                  title="Weak password"
                  message="Consider using a stronger password with numbers and symbols."
                  className="mt-2"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    ),
  };

  const bannerExamplesSection: CollapsibleSection = {
    id: "banner",
    title: "Banner Notifications",
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Banner Notification Examples
        </h4>
        <p className="text-redis-sm text-redis-dusk-04">
          Banner notifications are full-width alerts that appear at the top of
          the page for important system-wide messages.
        </p>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
              Toggle Banner
            </h5>
          </CardHeader>
          <CardContent>
            <Button
              variant={showBanner ? "primary" : "outline"}
              onClick={() => setShowBanner(!showBanner)}
            >
              {showBanner ? "Hide Banner" : "Show Banner"}
            </Button>
          </CardContent>
        </Card>

        {showBanner && (
          <div className="space-y-4">
            <BannerNotification
              type="warning"
              title="Scheduled Maintenance"
              message="System maintenance is scheduled for tonight from 2:00 AM to 4:00 AM EST. Service may be temporarily unavailable."
              onClose={() => setShowBanner(false)}
              action={{
                label: "Learn More",
                onClick: () => alert("Opening maintenance details..."),
              }}
            />
          </div>
        )}

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">
              Banner Variations
            </h5>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <BannerNotification
                type="success"
                title="New Features Released"
                message="Check out our latest dashboard improvements and API enhancements."
                action={{
                  label: "View Release Notes",
                  onClick: () => alert("Opening release notes..."),
                }}
              />
              <BannerNotification
                type="error"
                title="Service Disruption"
                message="We're experiencing issues with our authentication service. Our team is working on a fix."
                action={{
                  label: "Status Page",
                  onClick: () => alert("Opening status page..."),
                }}
              />
              <BannerNotification
                type="info"
                title="Account Verification Required"
                message="Please verify your email address to access all features."
                action={{
                  label: "Resend Email",
                  onClick: () => alert("Verification email sent!"),
                }}
              />
            </div>
          </CardContent>
        </Card>
      </div>
    ),
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">
            Notifications
          </h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Toast notifications, inline alerts, and banner messages for user
            feedback
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/settings")}>
            Notification Settings
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              addNotification({
                type: "success",
                title: "Success",
                message: "Action completed successfully.",
              });
              addNotification({
                type: "info",
                title: "Information",
                message: "This is an informational message.",
              });
              addNotification({
                type: "warning",
                title: "Warning",
                message: "Please review your settings.",
              });
              addNotification({
                type: "error",
                title: "Error",
                message: "Something went wrong. Please try again.",
              });
            }}
          >
            Test All Types
          </Button>
        </div>
      </div>

      {/* Notification Examples */}
      <CollapsibleCard
        title="Notification Examples"
        description="Different notification patterns for various use cases and contexts"
        sections={[
          toastExamplesSection,
          inlineExamplesSection,
          bannerExamplesSection,
        ]}
        defaultExpandedSection="toast"
        allowMultipleExpanded={true}
      />

      {/* Implementation Guide */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
            Implementation Guidelines
          </h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                When to Use Each Type
              </h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>
                  • <strong>Toast:</strong> Brief confirmations, status updates
                </li>
                <li>
                  • <strong>Inline:</strong> Form validation, contextual
                  feedback
                </li>
                <li>
                  • <strong>Banner:</strong> System-wide alerts, important
                  announcements
                </li>
                <li>
                  • <strong>Success:</strong> Completed actions, confirmations
                </li>
                <li>
                  • <strong>Error:</strong> Failed actions, validation errors
                </li>
                <li>
                  • <strong>Warning:</strong> Cautions, unsaved changes
                </li>
                <li>
                  • <strong>Info:</strong> General information, feature
                  announcements
                </li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                Best Practices
              </h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Keep messages concise and actionable</li>
                <li>
                  • Use appropriate timing (3-5s for success, longer for errors)
                </li>
                <li>• Provide clear actions when needed</li>
                <li>• Don't overwhelm users with too many notifications</li>
                <li>• Use consistent positioning and styling</li>
                <li>• Ensure notifications are accessible to screen readers</li>
                <li>• Test notification behavior on mobile devices</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Wrap the Notifications component with the provider
const NotificationsPage = () => (
  <NotificationProvider>
    <Notifications />
  </NotificationProvider>
);

export default NotificationsPage;
