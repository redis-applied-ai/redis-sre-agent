import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  Form,
  CollapsibleCard,
  type FormFieldConfig,
  type CollapsibleSection
} from '@radar/ui-kit';

// Modal Component
interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  showCloseButton?: boolean;
  closeOnOverlayClick?: boolean;
  closeOnEsc?: boolean;
}

const Modal = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnOverlayClick = true,
  closeOnEsc = true
}: ModalProps) => {
  useEffect(() => {
    if (!closeOnEsc) return;

    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose, closeOnEsc]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const getSizeClasses = () => {
    switch (size) {
      case 'sm': return 'max-w-sm';
      case 'md': return 'max-w-md';
      case 'lg': return 'max-w-2xl';
      case 'xl': return 'max-w-4xl';
      case 'full': return 'max-w-full mx-4';
      default: return 'max-w-md';
    }
  };

  const modalContent = (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={closeOnOverlayClick ? onClose : undefined}
      />

      {/* Modal */}
      <div className={`
        relative bg-redis-midnight border border-redis-dusk-08 rounded-redis-lg shadow-xl
        transform transition-all w-full ${getSizeClasses()}
        animate-in slide-in-from-bottom-4 fade-in duration-200
      `}>
        {/* Header */}
        {(title || showCloseButton) && (
          <div className="flex items-center justify-between p-6 border-b border-redis-dusk-08">
            {title && (
              <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
                {title}
              </h3>
            )}
            {showCloseButton && (
              <button
                onClick={onClose}
                className="text-redis-dusk-04 hover:text-redis-dusk-01 transition-colors p-1"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        )}

        {/* Content */}
        <div className="p-6">
          {children}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

// Confirmation Dialog Component
interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'default' | 'destructive';
}

const ConfirmDialog = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'default'
}: ConfirmDialogProps) => {
  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className="space-y-4">
        <p className="text-redis-sm text-redis-dusk-04">{message}</p>
        <div className="flex gap-3 justify-end">
          <Button variant="outline" onClick={onClose}>
            {cancelText}
          </Button>
          <Button
            variant={variant === 'destructive' ? 'destructive' : 'primary'}
            onClick={handleConfirm}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

// Alert Dialog Component
interface AlertDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  message: string;
  type?: 'success' | 'error' | 'warning' | 'info';
}

const AlertDialog = ({
  isOpen,
  onClose,
  title,
  message,
  type = 'info'
}: AlertDialogProps) => {
  const getIcon = () => {
    switch (type) {
      case 'success':
        return (
          <div className="w-12 h-12 bg-redis-green/20 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-redis-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        );
      case 'error':
        return (
          <div className="w-12 h-12 bg-redis-red/20 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-redis-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        );
      case 'warning':
        return (
          <div className="w-12 h-12 bg-redis-yellow-500/20 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-redis-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0l-5.898 6.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
        );
      default:
        return (
          <div className="w-12 h-12 bg-redis-blue-03/20 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-redis-blue-03" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        );
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="sm" showCloseButton={false}>
      <div className="text-center space-y-4">
        <div className="flex justify-center">
          {getIcon()}
        </div>
        <div>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">{title}</h3>
          <p className="text-redis-sm text-redis-dusk-04">{message}</p>
        </div>
        <Button variant="primary" onClick={onClose} className="w-full">
          OK
        </Button>
      </div>
    </Modal>
  );
};

// Drawer/Slide-out Component
interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  position?: 'left' | 'right';
  size?: 'sm' | 'md' | 'lg';
}

const Drawer = ({
  isOpen,
  onClose,
  title,
  children,
  position = 'right',
  size = 'md'
}: DrawerProps) => {
  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getSizeClasses = () => {
    switch (size) {
      case 'sm': return 'max-w-sm';
      case 'md': return 'max-w-md';
      case 'lg': return 'max-w-lg';
      default: return 'max-w-md';
    }
  };

  const getPositionClasses = () => {
    return position === 'left' ? 'left-0' : 'right-0';
  };

  const drawerContent = (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className={`
        relative bg-redis-midnight border-redis-dusk-08 shadow-xl h-full w-full
        ${getSizeClasses()} ${getPositionClasses()}
        ${position === 'left' ? 'border-r' : 'border-l'}
        transform transition-transform duration-300 ease-in-out
        ${position === 'left' ? 'animate-in slide-in-from-left' : 'animate-in slide-in-from-right'}
      `}>
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between p-6 border-b border-redis-dusk-08">
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              {title}
            </h3>
            <button
              onClick={onClose}
              className="text-redis-dusk-04 hover:text-redis-dusk-01 transition-colors p-1"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Content */}
        <div className="p-6 overflow-y-auto h-full">
          {children}
        </div>
      </div>
    </div>
  );

  return createPortal(drawerContent, document.body);
};

const Modals = () => {
  // Basic modals
  const [showBasicModal, setShowBasicModal] = useState(false);
  const [showLargeModal, setShowLargeModal] = useState(false);
  const [showFullModal, setShowFullModal] = useState(false);

  // Form modal
  const [showFormModal, setShowFormModal] = useState(false);

  // Dialogs
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showAlertDialog, setShowAlertDialog] = useState(false);
  const [alertType, setAlertType] = useState<'success' | 'error' | 'warning' | 'info'>('info');

  // Drawers
  const [showDrawer, setShowDrawer] = useState(false);
  const [showLeftDrawer, setShowLeftDrawer] = useState(false);

  // Form configuration
  const userFormFields: FormFieldConfig[] = [
    {
      name: 'name',
      label: 'Full Name',
      type: 'text',
      required: true
    },
    {
      name: 'email',
      label: 'Email Address',
      type: 'email',
      required: true
    },
    {
      name: 'role',
      label: 'Role',
      type: 'select',
      required: true,
      options: [
        { label: 'Admin', value: 'admin' },
        { label: 'User', value: 'user' },
        { label: 'Viewer', value: 'viewer' }
      ]
    },
    {
      name: 'department',
      label: 'Department',
      type: 'select',
      options: [
        { label: 'Engineering', value: 'engineering' },
        { label: 'Marketing', value: 'marketing' },
        { label: 'Sales', value: 'sales' },
        { label: 'Support', value: 'support' }
      ]
    }
  ];

  const handleFormSubmit = async (data: Record<string, any>) => {
    console.log('Form submitted:', data);
    await new Promise(resolve => setTimeout(resolve, 1000));
    setShowFormModal(false);
    setAlertType('success');
    setShowAlertDialog(true);
  };

  const basicModalsSection: CollapsibleSection = {
    id: 'basic',
    title: 'Basic Modals',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Modal Examples
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Button variant="outline" onClick={() => setShowBasicModal(true)}>
            Basic Modal
          </Button>
          <Button variant="outline" onClick={() => setShowLargeModal(true)}>
            Large Modal
          </Button>
          <Button variant="outline" onClick={() => setShowFullModal(true)}>
            Full Screen Modal
          </Button>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Form Modal Example</h5>
          </CardHeader>
          <CardContent>
            <Button variant="primary" onClick={() => setShowFormModal(true)}>
              Open User Form Modal
            </Button>
          </CardContent>
        </Card>

        {/* Basic Modal */}
        <Modal
          isOpen={showBasicModal}
          onClose={() => setShowBasicModal(false)}
          title="Basic Modal"
        >
          <div className="space-y-4">
            <p className="text-redis-sm text-redis-dusk-04">
              This is a basic modal with a title, content, and close button.
              You can close it by clicking the X button, pressing Escape, or clicking outside the modal.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowBasicModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => setShowBasicModal(false)}>
                OK
              </Button>
            </div>
          </div>
        </Modal>

        {/* Large Modal */}
        <Modal
          isOpen={showLargeModal}
          onClose={() => setShowLargeModal(false)}
          title="Large Modal with More Content"
          size="lg"
        >
          <div className="space-y-6">
            <p className="text-redis-sm text-redis-dusk-04">
              This is a larger modal that can accommodate more content. It's useful for complex forms,
              detailed information, or multi-step processes.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-2">Left Column</h5>
                <p className="text-redis-sm text-redis-dusk-04 mb-4">
                  This modal demonstrates how you can organize content in multiple columns
                  when you have more space available.
                </p>
                <div className="space-y-2">
                  <div className="p-3 bg-redis-dusk-09 rounded-redis-sm">
                    <span className="text-redis-sm text-redis-dusk-01">Feature 1</span>
                  </div>
                  <div className="p-3 bg-redis-dusk-09 rounded-redis-sm">
                    <span className="text-redis-sm text-redis-dusk-01">Feature 2</span>
                  </div>
                  <div className="p-3 bg-redis-dusk-09 rounded-redis-sm">
                    <span className="text-redis-sm text-redis-dusk-01">Feature 3</span>
                  </div>
                </div>
              </div>
              <div>
                <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-2">Right Column</h5>
                <p className="text-redis-sm text-redis-dusk-04 mb-4">
                  You can also include interactive elements like forms, buttons,
                  and other components in larger modals.
                </p>
                <div className="space-y-3">
                  <Input placeholder="Example input field" />
                  <textarea
                    className="redis-input-base w-full h-20 resize-none"
                    placeholder="Example textarea"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-redis-dusk-08">
              <Button variant="outline" onClick={() => setShowLargeModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => setShowLargeModal(false)}>
                Save Changes
              </Button>
            </div>
          </div>
        </Modal>

        {/* Full Screen Modal */}
        <Modal
          isOpen={showFullModal}
          onClose={() => setShowFullModal(false)}
          title="Full Screen Modal"
          size="full"
        >
          <div className="space-y-6">
            <p className="text-redis-sm text-redis-dusk-04">
              This is a full-screen modal that takes up the entire viewport. It's useful for
              complex workflows, data entry forms, or when you need maximum screen real estate.
            </p>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <Card>
                <CardHeader>
                  <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Section 1</h5>
                </CardHeader>
                <CardContent>
                  <p className="text-redis-sm text-redis-dusk-04">
                    Full-screen modals can contain multiple cards and complex layouts.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Section 2</h5>
                </CardHeader>
                <CardContent>
                  <p className="text-redis-sm text-redis-dusk-04">
                    They're particularly useful for admin interfaces and data management.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Section 3</h5>
                </CardHeader>
                <CardContent>
                  <p className="text-redis-sm text-redis-dusk-04">
                    You can organize content just like you would on a regular page.
                  </p>
                </CardContent>
              </Card>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-redis-dusk-08">
              <Button variant="outline" onClick={() => setShowFullModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>

        {/* Form Modal */}
        <Modal
          isOpen={showFormModal}
          onClose={() => setShowFormModal(false)}
          title="Create New User"
          size="md"
        >
          <Form
            fields={userFormFields}
            onSubmit={handleFormSubmit}
            onCancel={() => setShowFormModal(false)}
            submitLabel="Create User"
            layout="vertical"
          />
        </Modal>
      </div>
    )
  };

  const dialogsSection: CollapsibleSection = {
    id: 'dialogs',
    title: 'Confirmation & Alert Dialogs',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Dialog Examples
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Confirmation Dialogs</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Button variant="outline" onClick={() => setShowConfirmDialog(true)}>
                  Basic Confirmation
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => setShowDeleteDialog(true)}
                >
                  Delete Confirmation
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Alert Dialogs</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Button
                  variant="outline"
                  className="w-full text-redis-green border-redis-green"
                  onClick={() => {
                    setAlertType('success');
                    setShowAlertDialog(true);
                  }}
                >
                  Success Alert
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-red border-redis-red"
                  onClick={() => {
                    setAlertType('error');
                    setShowAlertDialog(true);
                  }}
                >
                  Error Alert
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-yellow-500 border-redis-yellow-500"
                  onClick={() => {
                    setAlertType('warning');
                    setShowAlertDialog(true);
                  }}
                >
                  Warning Alert
                </Button>
                <Button
                  variant="outline"
                  className="w-full text-redis-blue-03 border-redis-blue-03"
                  onClick={() => {
                    setAlertType('info');
                    setShowAlertDialog(true);
                  }}
                >
                  Info Alert
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Confirmation Dialog */}
        <ConfirmDialog
          isOpen={showConfirmDialog}
          onClose={() => setShowConfirmDialog(false)}
          onConfirm={() => alert('Action confirmed!')}
          title="Confirm Action"
          message="Are you sure you want to proceed with this action? This will update your settings."
        />

        {/* Delete Confirmation Dialog */}
        <ConfirmDialog
          isOpen={showDeleteDialog}
          onClose={() => setShowDeleteDialog(false)}
          onConfirm={() => alert('Item deleted!')}
          title="Delete Item"
          message="Are you sure you want to delete this item? This action cannot be undone."
          confirmText="Delete"
          variant="destructive"
        />

        {/* Alert Dialog */}
        <AlertDialog
          isOpen={showAlertDialog}
          onClose={() => setShowAlertDialog(false)}
          title={
            alertType === 'success' ? 'Success!' :
            alertType === 'error' ? 'Error Occurred' :
            alertType === 'warning' ? 'Warning' :
            'Information'
          }
          message={
            alertType === 'success' ? 'Your action was completed successfully.' :
            alertType === 'error' ? 'Something went wrong. Please try again.' :
            alertType === 'warning' ? 'Please review your settings before proceeding.' :
            'Here is some important information for you.'
          }
          type={alertType}
        />
      </div>
    )
  };

  const drawersSection: CollapsibleSection = {
    id: 'drawers',
    title: 'Drawers & Side Panels',
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Drawer Examples
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Button variant="outline" onClick={() => setShowDrawer(true)}>
            Right Drawer
          </Button>
          <Button variant="outline" onClick={() => setShowLeftDrawer(true)}>
            Left Drawer
          </Button>
        </div>

        {/* Right Drawer */}
        <Drawer
          isOpen={showDrawer}
          onClose={() => setShowDrawer(false)}
          title="Settings Panel"
          position="right"
          size="md"
        >
          <div className="space-y-6">
            <div>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                User Preferences
              </h5>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-redis-sm text-redis-dusk-01">Dark Mode</span>
                  <input type="checkbox" className="rounded border-redis-dusk-08" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-redis-sm text-redis-dusk-01">Email Notifications</span>
                  <input type="checkbox" className="rounded border-redis-dusk-08" defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-redis-sm text-redis-dusk-01">Push Notifications</span>
                  <input type="checkbox" className="rounded border-redis-dusk-08" />
                </div>
              </div>
            </div>

            <div>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                Account Settings
              </h5>
              <div className="space-y-3">
                <Input label="Display Name" defaultValue="John Doe" />
                <div>
                  <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                    Language
                  </label>
                  <select className="redis-input-base w-full">
                    <option>English</option>
                    <option>Spanish</option>
                    <option>French</option>
                    <option>German</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-redis-dusk-08">
              <div className="flex gap-2">
                <Button variant="primary" className="flex-1">
                  Save Changes
                </Button>
                <Button variant="outline" onClick={() => setShowDrawer(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </Drawer>

        {/* Left Drawer */}
        <Drawer
          isOpen={showLeftDrawer}
          onClose={() => setShowLeftDrawer(false)}
          title="Navigation Menu"
          position="left"
          size="sm"
        >
          <div className="space-y-4">
            <div>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                Main Navigation
              </h5>
              <nav className="space-y-2">
                <a href="#" className="block p-2 text-redis-sm text-redis-dusk-01 hover:bg-redis-dusk-09 rounded-redis-sm">
                  Dashboard
                </a>
                <a href="#" className="block p-2 text-redis-sm text-redis-dusk-01 hover:bg-redis-dusk-09 rounded-redis-sm">
                  Users
                </a>
                <a href="#" className="block p-2 text-redis-sm text-redis-dusk-01 hover:bg-redis-dusk-09 rounded-redis-sm">
                  Settings
                </a>
                <a href="#" className="block p-2 text-redis-sm text-redis-dusk-01 hover:bg-redis-dusk-09 rounded-redis-sm">
                  Analytics
                </a>
              </nav>
            </div>

            <div className="pt-4 border-t border-redis-dusk-08">
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">
                Quick Actions
              </h5>
              <div className="space-y-2">
                <Button variant="outline" size="sm" className="w-full justify-start">
                  Create New User
                </Button>
                <Button variant="outline" size="sm" className="w-full justify-start">
                  Generate Report
                </Button>
                <Button variant="outline" size="sm" className="w-full justify-start">
                  Export Data
                </Button>
              </div>
            </div>
          </div>
        </Drawer>
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Modals & Dialogs</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Modal dialogs, confirmation prompts, and side panels for user interactions
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Modal Settings</Button>
          <Button variant="primary">Create Modal</Button>
        </div>
      </div>

      {/* Modal Examples */}
      <CollapsibleCard
        title="Modal & Dialog Examples"
        description="Different modal patterns for various user interaction scenarios"
        sections={[basicModalsSection, dialogsSection, drawersSection]}
        defaultExpandedSection="basic"
        allowMultipleExpanded={true}
      />

      {/* Implementation Guidelines */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Modal Design Guidelines</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Best Practices</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Use modals sparingly - consider inline editing first</li>
                <li>• Always provide a clear way to close the modal</li>
                <li>• Use appropriate sizes for content complexity</li>
                <li>• Implement proper focus management and keyboard navigation</li>
                <li>• Handle loading states and form validation gracefully</li>
                <li>• Use confirmation dialogs for destructive actions</li>
                <li>• Consider mobile responsiveness and touch interactions</li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Accessibility</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Trap focus within the modal when open</li>
                <li>• Use ARIA attributes (role="dialog", aria-modal="true")</li>
                <li>• Provide descriptive labels and titles</li>
                <li>• Support Escape key for closing</li>
                <li>• Announce modal opening to screen readers</li>
                <li>• Return focus to trigger element when closed</li>
                <li>• Ensure sufficient color contrast for all elements</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Modals;
