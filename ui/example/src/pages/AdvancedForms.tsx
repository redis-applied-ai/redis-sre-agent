import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Form,
  CollapsibleCard,
  ErrorMessage,
  type FormFieldConfig,
  type CollapsibleSection
} from '@radar/ui-kit';

const AdvancedForms = () => {
  const [formResults, setFormResults] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // User Registration Form
  const userRegistrationFields: FormFieldConfig[] = [
    {
      name: 'firstName',
      label: 'First Name',
      type: 'text',
      required: true,
      validation: (value) => {
        if (!value || value.length < 2) return 'First name must be at least 2 characters';
        if (!/^[a-zA-Z\s]+$/.test(value)) return 'First name can only contain letters and spaces';
        return undefined;
      }
    },
    {
      name: 'lastName',
      label: 'Last Name',
      type: 'text',
      required: true,
      validation: (value) => {
        if (!value || value.length < 2) return 'Last name must be at least 2 characters';
        if (!/^[a-zA-Z\s]+$/.test(value)) return 'Last name can only contain letters and spaces';
        return undefined;
      }
    },
    {
      name: 'email',
      label: 'Email Address',
      type: 'email',
      required: true,
      validation: (value) => {
        if (!value) return 'Email is required';
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) return 'Please enter a valid email address';
        return undefined;
      }
    },
    {
      name: 'phone',
      label: 'Phone Number',
      type: 'tel',
      required: false,
      helperText: 'Format: (555) 123-4567',
      validation: (value) => {
        if (value && !/^\(\d{3}\)\s\d{3}-\d{4}$/.test(value)) {
          return 'Phone number must be in format (555) 123-4567';
        }
        return undefined;
      }
    },
    {
      name: 'dateOfBirth',
      label: 'Date of Birth',
      type: 'date',
      required: true,
      validation: (value) => {
        if (!value) return 'Date of birth is required';
        const birthDate = new Date(value);
        const today = new Date();
        const age = today.getFullYear() - birthDate.getFullYear();
        if (age < 18) return 'You must be at least 18 years old';
        if (age > 120) return 'Please enter a valid date of birth';
        return undefined;
      }
    },
    {
      name: 'country',
      label: 'Country',
      type: 'select',
      required: true,
      options: [
        { label: 'United States', value: 'us' },
        { label: 'Canada', value: 'ca' },
        { label: 'United Kingdom', value: 'uk' },
        { label: 'Germany', value: 'de' },
        { label: 'France', value: 'fr' },
        { label: 'Japan', value: 'jp' },
        { label: 'Australia', value: 'au' }
      ]
    },
    {
      name: 'interests',
      label: 'Interests',
      type: 'checkbox',
      options: [
        { label: 'Technology', value: 'tech' },
        { label: 'Sports', value: 'sports' },
        { label: 'Music', value: 'music' },
        { label: 'Travel', value: 'travel' },
        { label: 'Reading', value: 'reading' },
        { label: 'Gaming', value: 'gaming' }
      ]
    },
    {
      name: 'newsletter',
      label: 'Newsletter Subscription',
      type: 'checkbox',
      options: [
        { label: 'Subscribe to weekly newsletter', value: 'weekly' },
        { label: 'Subscribe to product updates', value: 'products' }
      ]
    },
    {
      name: 'bio',
      label: 'Short Bio',
      type: 'textarea',
      required: false,
      helperText: 'Tell us a bit about yourself (max 500 characters)',
      validation: (value) => {
        if (value && value.length > 500) return 'Bio must be 500 characters or less';
        return undefined;
      }
    }
  ];

  // Redis Configuration Form
  const redisConfigFields: FormFieldConfig[] = [
    {
      name: 'instanceName',
      label: 'Instance Name',
      type: 'text',
      required: true,
      validation: (value) => {
        if (!value) return 'Instance name is required';
        if (!/^[a-zA-Z0-9-_]+$/.test(value)) return 'Only letters, numbers, hyphens, and underscores allowed';
        if (value.length < 3) return 'Instance name must be at least 3 characters';
        return undefined;
      }
    },
    {
      name: 'environment',
      label: 'Environment',
      type: 'select',
      required: true,
      options: [
        { label: 'Development', value: 'dev' },
        { label: 'Staging', value: 'staging' },
        { label: 'Production', value: 'prod' }
      ]
    },
    {
      name: 'host',
      label: 'Host',
      type: 'text',
      required: true,
      validation: (value) => {
        if (!value) return 'Host is required';
        // Basic hostname/IP validation
        const hostRegex = /^([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+$|^(\d{1,3}\.){3}\d{1,3}$/;
        if (!hostRegex.test(value)) return 'Please enter a valid hostname or IP address';
        return undefined;
      }
    },
    {
      name: 'port',
      label: 'Port',
      type: 'number',
      required: true,
      validation: (value) => {
        const port = parseInt(value);
        if (!port || port < 1 || port > 65535) return 'Port must be between 1 and 65535';
        return undefined;
      }
    },
    {
      name: 'password',
      label: 'Password',
      type: 'password',
      required: false,
      helperText: 'Leave empty if no authentication required'
    },
    {
      name: 'database',
      label: 'Database Number',
      type: 'number',
      required: false,
      validation: (value) => {
        if (value !== undefined && value !== '') {
          const db = parseInt(value);
          if (db < 0 || db > 15) return 'Database number must be between 0 and 15';
        }
        return undefined;
      }
    },
    {
      name: 'ssl',
      label: 'SSL/TLS Configuration',
      type: 'checkbox',
      options: [
        { label: 'Enable SSL/TLS', value: 'enabled' },
        { label: 'Verify SSL certificates', value: 'verify' }
      ]
    },
    {
      name: 'timeout',
      label: 'Connection Timeout (seconds)',
      type: 'number',
      required: false,
      validation: (value) => {
        if (value !== undefined && value !== '') {
          const timeout = parseInt(value);
          if (timeout < 1 || timeout > 300) return 'Timeout must be between 1 and 300 seconds';
        }
        return undefined;
      }
    },
    {
      name: 'maxConnections',
      label: 'Max Connections',
      type: 'number',
      required: false,
      validation: (value) => {
        if (value !== undefined && value !== '') {
          const max = parseInt(value);
          if (max < 1 || max > 1000) return 'Max connections must be between 1 and 1000';
        }
        return undefined;
      }
    },
    {
      name: 'notes',
      label: 'Configuration Notes',
      type: 'textarea',
      required: false,
      helperText: 'Any additional notes about this configuration'
    }
  ];

  // Complex Survey Form
  const surveyFields: FormFieldConfig[] = [
    {
      name: 'overallSatisfaction',
      label: 'Overall Satisfaction',
      type: 'select',
      required: true,
      options: [
        { label: 'Very Satisfied', value: '5' },
        { label: 'Satisfied', value: '4' },
        { label: 'Neutral', value: '3' },
        { label: 'Dissatisfied', value: '2' },
        { label: 'Very Dissatisfied', value: '1' }
      ]
    },
    {
      name: 'features',
      label: 'Which features do you use most?',
      type: 'checkbox',
      required: true,
      options: [
        { label: 'Dashboard & Analytics', value: 'dashboard' },
        { label: 'User Management', value: 'users' },
        { label: 'API Integration', value: 'api' },
        { label: 'Monitoring & Alerts', value: 'monitoring' },
        { label: 'Data Export', value: 'export' },
        { label: 'Custom Reports', value: 'reports' }
      ],
      validation: (value) => {
        if (!value || value.length === 0) return 'Please select at least one feature';
        return undefined;
      }
    },
    {
      name: 'usageFrequency',
      label: 'How often do you use our platform?',
      type: 'select',
      required: true,
      options: [
        { label: 'Daily', value: 'daily' },
        { label: 'Weekly', value: 'weekly' },
        { label: 'Monthly', value: 'monthly' },
        { label: 'Rarely', value: 'rarely' }
      ]
    },
    {
      name: 'improvements',
      label: 'What improvements would you like to see?',
      type: 'textarea',
      required: true,
      helperText: 'Please be specific about features or changes you would like',
      validation: (value) => {
        if (!value || value.length < 10) return 'Please provide at least 10 characters of feedback';
        return undefined;
      }
    },
    {
      name: 'recommend',
      label: 'Would you recommend us to others?',
      type: 'select',
      required: true,
      options: [
        { label: 'Definitely', value: 'definitely' },
        { label: 'Probably', value: 'probably' },
        { label: 'Not sure', value: 'not_sure' },
        { label: 'Probably not', value: 'probably_not' },
        { label: 'Definitely not', value: 'definitely_not' }
      ]
    },
    {
      name: 'contactPermission',
      label: 'Follow-up Contact',
      type: 'checkbox',
      options: [
        { label: 'You may contact me about my feedback', value: 'contact_ok' },
        { label: 'I would like to participate in beta testing', value: 'beta_testing' }
      ]
    }
  ];

  const handleFormSubmit = async (formName: string, data: Record<string, any>) => {
    setErrors({ ...errors, [formName]: '' });
    console.log(`${formName} submitted:`, data);

    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Random success/failure for demo
    if (Math.random() > 0.2) {
      setFormResults({ ...formResults, [formName]: data });
      alert(`${formName} submitted successfully!`);
    } else {
      setErrors({ ...errors, [formName]: 'Submission failed. Please try again.' });
      throw new Error('Submission failed');
    }
  };

  const registrationSection: CollapsibleSection = {
    id: 'registration',
    title: 'User Registration Form',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6">
        <div className="mb-6">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
            Complete User Registration
          </h4>
          <p className="text-redis-sm text-redis-dusk-04">
            This form demonstrates complex validation, different field types, and conditional logic.
          </p>
        </div>

        {errors.registration && (
          <div className="mb-6">
            <ErrorMessage message={errors.registration} title="Registration Error" />
          </div>
        )}

        <Form
          fields={userRegistrationFields}
          onSubmit={(data) => handleFormSubmit('registration', data)}
          submitLabel="Create Account"
          layout="vertical"
          initialData={{
            country: 'us',
            newsletter: ['weekly']
          }}
        />

        {formResults.registration && (
          <div className="mt-6 p-4 bg-redis-green/10 border border-redis-green/30 rounded-redis-sm">
            <h5 className="text-redis-sm font-semibold text-redis-green mb-2">Registration Successful!</h5>
            <pre className="text-redis-xs text-redis-dusk-04 overflow-x-auto">
              {JSON.stringify(formResults.registration, null, 2)}
            </pre>
          </div>
        )}
      </div>
    )
  };

  const configurationSection: CollapsibleSection = {
    id: 'configuration',
    title: 'Redis Configuration Form',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6">
        <div className="mb-6">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
            Redis Instance Configuration
          </h4>
          <p className="text-redis-sm text-redis-dusk-04">
            Configure connection settings for a new Redis instance with validation for technical fields.
          </p>
        </div>

        {errors.configuration && (
          <div className="mb-6">
            <ErrorMessage message={errors.configuration} title="Configuration Error" />
          </div>
        )}

        <Form
          fields={redisConfigFields}
          onSubmit={(data) => handleFormSubmit('configuration', data)}
          submitLabel="Save Configuration"
          layout="horizontal"
          initialData={{
            port: 6379,
            environment: 'dev',
            database: 0,
            timeout: 30,
            maxConnections: 100
          }}
        />

        {formResults.configuration && (
          <div className="mt-6 p-4 bg-redis-green/10 border border-redis-green/30 rounded-redis-sm">
            <h5 className="text-redis-sm font-semibold text-redis-green mb-2">Configuration Saved!</h5>
            <pre className="text-redis-xs text-redis-dusk-04 overflow-x-auto">
              {JSON.stringify(formResults.configuration, null, 2)}
            </pre>
          </div>
        )}
      </div>
    )
  };

  const surveySection: CollapsibleSection = {
    id: 'survey',
    title: 'Customer Feedback Survey',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6">
        <div className="mb-6">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
            Help Us Improve
          </h4>
          <p className="text-redis-sm text-redis-dusk-04">
            Your feedback is valuable to us. This survey demonstrates complex form logic and validation.
          </p>
        </div>

        {errors.survey && (
          <div className="mb-6">
            <ErrorMessage message={errors.survey} title="Survey Error" />
          </div>
        )}

        <Form
          fields={surveyFields}
          onSubmit={(data) => handleFormSubmit('survey', data)}
          submitLabel="Submit Feedback"
          layout="vertical"
        />

        {formResults.survey && (
          <div className="mt-6 p-4 bg-redis-green/10 border border-redis-green/30 rounded-redis-sm">
            <h5 className="text-redis-sm font-semibold text-redis-green mb-2">Thank you for your feedback!</h5>
            <pre className="text-redis-xs text-redis-dusk-04 overflow-x-auto">
              {JSON.stringify(formResults.survey, null, 2)}
            </pre>
          </div>
        )}
      </div>
    )
  };

  const dynamicFormSection: CollapsibleSection = {
    id: 'dynamic',
    title: 'Dynamic Form Builder',
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6">
        <div className="mb-6">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
            Dynamic Form Example
          </h4>
          <p className="text-redis-sm text-redis-dusk-04">
            This example shows how forms can be built dynamically with conditional fields.
          </p>
        </div>

        <DynamicFormExample />
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Advanced Forms</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Complex form examples with validation, different field types, and dynamic behavior
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Clear All Forms</Button>
          <Button variant="primary">Form Builder</Button>
        </div>
      </div>

      {/* Form Examples */}
      <CollapsibleCard
        title="Form Examples"
        description="Comprehensive examples showcasing different form patterns and validation strategies"
        sections={[registrationSection, configurationSection, surveySection, dynamicFormSection]}
        defaultExpandedSection="registration"
        allowMultipleExpanded={false}
      />

      {/* Form Guidelines */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Form Design Guidelines</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Validation Best Practices</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Validate on blur and submit, not on every keystroke</li>
                <li>• Provide clear, specific error messages</li>
                <li>• Use client-side validation for immediate feedback</li>
                <li>• Always validate on the server side as well</li>
                <li>• Group related validation errors together</li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Accessibility Features</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Proper label associations for screen readers</li>
                <li>• ARIA attributes for validation states</li>
                <li>• Keyboard navigation support</li>
                <li>• High contrast error states</li>
                <li>• Focus management and visual indicators</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Dynamic Form Example Component
const DynamicFormExample = () => {
  const [formType] = useState<'user' | 'organization' | 'api'>('user');
  const [conditionalFields, setConditionalFields] = useState<FormFieldConfig[]>([]);

  const baseFields: FormFieldConfig[] = [
    {
      name: 'formType',
      label: 'Form Type',
      type: 'select',
      required: true,
      options: [
        { label: 'User Account', value: 'user' },
        { label: 'Organization', value: 'organization' },
        { label: 'API Configuration', value: 'api' }
      ]
    }
  ];

  const userFields: FormFieldConfig[] = [
    {
      name: 'username',
      label: 'Username',
      type: 'text',
      required: true
    },
    {
      name: 'email',
      label: 'Email',
      type: 'email',
      required: true
    }
  ];

  const organizationFields: FormFieldConfig[] = [
    {
      name: 'orgName',
      label: 'Organization Name',
      type: 'text',
      required: true
    },
    {
      name: 'industry',
      label: 'Industry',
      type: 'select',
      required: true,
      options: [
        { label: 'Technology', value: 'tech' },
        { label: 'Finance', value: 'finance' },
        { label: 'Healthcare', value: 'healthcare' },
        { label: 'Education', value: 'education' }
      ]
    }
  ];

  const apiFields: FormFieldConfig[] = [
    {
      name: 'apiName',
      label: 'API Name',
      type: 'text',
      required: true
    },
    {
      name: 'rateLimit',
      label: 'Rate Limit (per minute)',
      type: 'number',
      required: true
    }
  ];

  const handleFormTypeChange = (data: Record<string, any>) => {
    const type = data.formType as 'user' | 'organization' | 'api';
    setFormType(type);

    switch (type) {
      case 'user':
        setConditionalFields(userFields);
        break;
      case 'organization':
        setConditionalFields(organizationFields);
        break;
      case 'api':
        setConditionalFields(apiFields);
        break;
    }
  };

  const allFields = [...baseFields, ...conditionalFields];

  return (
    <div>
      <Form
        fields={allFields}
        onSubmit={(data) => {
          console.log('Dynamic form submitted:', data);
          alert('Dynamic form submitted successfully!');
        }}
        submitLabel="Submit Dynamic Form"
        layout="vertical"
        initialData={{ formType: 'user' }}
      />
    </div>
  );
};

export default AdvancedForms;
