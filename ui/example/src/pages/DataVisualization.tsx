import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  CollapsibleCard,
  Tooltip,
  type CollapsibleSection
} from '@radar/ui-kit';

// Mock data for visualizations
const generateTimeSeriesData = (days: number) => {
  const data = [];
  const now = new Date();
  for (let i = days; i >= 0; i--) {
    const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    data.push({
      date: date.toISOString().split('T')[0],
      operations: Math.floor(Math.random() * 50000) + 10000,
      memory: Math.floor(Math.random() * 30) + 50,
      connections: Math.floor(Math.random() * 200) + 100,
      latency: Math.random() * 5 + 0.5
    });
  }
  return data;
};

const performanceData = generateTimeSeriesData(30);

const distributionData = [
  { category: 'GET operations', value: 45, color: '#405bff' },
  { category: 'SET operations', value: 25, color: '#3cde67' },
  { category: 'DEL operations', value: 15, color: '#ff4438' },
  { category: 'HGET operations', value: 10, color: '#fbbf24' },
  { category: 'Other operations', value: 5, color: '#8b5cf6' }
];

const heatmapData = Array.from({ length: 24 }, (_, hour) =>
  Array.from({ length: 7 }, (_, day) => ({
    hour,
    day,
    value: Math.floor(Math.random() * 100),
    dayName: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][day]
  }))
).flat();

const DataVisualization = () => {
  const [selectedMetric, setSelectedMetric] = useState<'operations' | 'memory' | 'connections' | 'latency'>('operations');
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d'>('30d');

  // Simple Chart Components (since we don't have a chart library)
  const LineChart = ({ data, metric, height = 200 }: { data: any[], metric: string, height?: number }) => {
    const values = data.map(d => d[metric]);
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    const range = maxValue - minValue;

    const points = data.map((d, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = ((maxValue - d[metric]) / range) * 80 + 10;
      return `${x},${y}`;
    }).join(' ');

    return (
      <div className="relative" style={{ height }}>
        <svg className="w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline
            fill="none"
            stroke="#405bff"
            strokeWidth="0.5"
            points={points}
          />
          <defs>
            <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#405bff" stopOpacity="0.3"/>
              <stop offset="100%" stopColor="#405bff" stopOpacity="0"/>
            </linearGradient>
          </defs>
          <polygon
            fill="url(#gradient)"
            points={`0,100 ${points} 100,100`}
          />
        </svg>
        <div className="absolute top-2 left-2 text-redis-xs text-redis-dusk-04">
          Max: {maxValue.toLocaleString()}
        </div>
        <div className="absolute bottom-2 left-2 text-redis-xs text-redis-dusk-04">
          Min: {minValue.toLocaleString()}
        </div>
      </div>
    );
  };

  const BarChart = ({ data, height = 200 }: { data: any[], height?: number }) => {
    const maxValue = Math.max(...data.map(d => d.value));

    return (
      <div className="space-y-3" style={{ height }}>
        {data.map((item, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-24 text-redis-xs text-redis-dusk-04 text-right">
              {item.category}
            </div>
            <div className="flex-1 relative">
              <div className="bg-redis-dusk-08 h-6 rounded-redis-sm">
                <div
                  className="h-6 rounded-redis-sm transition-all duration-500"
                  style={{
                    width: `${(item.value / maxValue) * 100}%`,
                    backgroundColor: item.color
                  }}
                />
              </div>
              <span className="absolute right-2 top-0 text-redis-xs text-redis-dusk-01 leading-6">
                {item.value}%
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const PieChart = ({ data }: { data: any[] }) => {
    const total = data.reduce((sum, item) => sum + item.value, 0);
    let currentAngle = 0;

    const segments = data.map(item => {
      const percentage = (item.value / total) * 100;
      const angle = (item.value / total) * 360;
      const startAngle = currentAngle;
      currentAngle += angle;

      const startX = 50 + 40 * Math.cos((startAngle - 90) * Math.PI / 180);
      const startY = 50 + 40 * Math.sin((startAngle - 90) * Math.PI / 180);
      const endX = 50 + 40 * Math.cos((currentAngle - 90) * Math.PI / 180);
      const endY = 50 + 40 * Math.sin((currentAngle - 90) * Math.PI / 180);

      const largeArc = angle > 180 ? 1 : 0;

      return {
        ...item,
        percentage,
        path: `M 50 50 L ${startX} ${startY} A 40 40 0 ${largeArc} 1 ${endX} ${endY} Z`
      };
    });

    return (
      <div className="flex items-center gap-6">
        <svg width="200" height="200" viewBox="0 0 100 100">
          {segments.map((segment, i) => (
            <path
              key={i}
              d={segment.path}
              fill={segment.color}
              stroke="#091a23"
              strokeWidth="0.5"
            />
          ))}
        </svg>
        <div className="space-y-2">
          {segments.map((segment, i) => (
            <div key={i} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-redis-xs"
                style={{ backgroundColor: segment.color }}
              />
              <span className="text-redis-sm text-redis-dusk-01">
                {segment.category}
              </span>
              <span className="text-redis-xs text-redis-dusk-04">
                ({segment.percentage.toFixed(1)}%)
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const Heatmap = ({ data }: { data: any[] }) => {
    const maxValue = Math.max(...data.map(d => d.value));
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    return (
      <div className="space-y-2">
        <div className="grid grid-cols-25 gap-1 text-redis-xs text-redis-dusk-04">
          <div></div>
          {hours.map(hour => (
            <div key={hour} className="text-center">
              {hour % 6 === 0 ? hour : ''}
            </div>
          ))}
        </div>
        {days.map((day, dayIndex) => (
          <div key={day} className="grid grid-cols-25 gap-1">
            <div className="text-redis-xs text-redis-dusk-04 pr-2 text-right">
              {day}
            </div>
            {hours.map(hour => {
              const dataPoint = data.find(d => d.day === dayIndex && d.hour === hour);
              const intensity = dataPoint ? dataPoint.value / maxValue : 0;
              return (
                <Tooltip key={hour} content={`${day} ${hour}:00 - ${dataPoint?.value || 0} ops`}>
                  <div
                    className="w-3 h-3 rounded-redis-xs cursor-pointer hover:scale-110 transition-transform"
                    style={{
                      backgroundColor: `rgba(64, 91, 255, ${intensity})`
                    }}
                  />
                </Tooltip>
              );
            })}
          </div>
        ))}
      </div>
    );
  };

  const Gauge = ({ value, max, label, color = '#405bff' }: { value: number, max: number, label: string, color?: string }) => {
    const percentage = (value / max) * 100;
    // const angle = (percentage / 100) * 180 - 90; // Unused for now

    return (
      <div className="flex flex-col items-center">
        <div className="relative w-32 h-16">
          <svg width="128" height="64" viewBox="0 0 128 64">
            <path
              d="M 10 54 A 54 54 0 0 1 118 54"
              fill="none"
              stroke="#2a2f3a"
              strokeWidth="4"
            />
            <path
              d="M 10 54 A 54 54 0 0 1 118 54"
              fill="none"
              stroke={color}
              strokeWidth="4"
              strokeDasharray={`${percentage * 1.7} 170`}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-2">
            <div className="text-redis-lg font-bold" style={{ color }}>
              {value.toFixed(1)}
            </div>
            <div className="text-redis-xs text-redis-dusk-04">
              {label}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const timeSeriesSection: CollapsibleSection = {
    id: 'timeseries',
    title: 'Time Series Charts',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            Performance Metrics Over Time
          </h4>
          <div className="flex gap-2">
            <div className="flex gap-1">
              {(['7d', '30d', '90d'] as const).map(range => (
                <Button
                  key={range}
                  variant={timeRange === range ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => setTimeRange(range)}
                >
                  {range}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {[
            { key: 'operations', label: 'Operations/sec', color: '#405bff' },
            { key: 'memory', label: 'Memory %', color: '#3cde67' },
            { key: 'connections', label: 'Connections', color: '#fbbf24' },
            { key: 'latency', label: 'Latency (ms)', color: '#ff4438' }
          ].map(metric => (
            <button
              key={metric.key}
              onClick={() => setSelectedMetric(metric.key as any)}
              className={`p-4 rounded-redis-sm border transition-colors text-left ${
                selectedMetric === metric.key
                  ? 'border-redis-blue-03 bg-redis-blue-03/10'
                  : 'border-redis-dusk-08 hover:border-redis-dusk-07'
              }`}
            >
              <div className="text-redis-sm font-medium text-redis-dusk-01">
                {metric.label}
              </div>
              <div className="text-redis-lg font-bold mt-1" style={{ color: metric.color }}>
                {(performanceData[performanceData.length - 1][metric.key as keyof typeof performanceData[0]]).toLocaleString()}
              </div>
            </button>
          ))}
        </div>

        <Card>
          <CardContent>
            <LineChart data={performanceData} metric={selectedMetric} height={300} />
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Average</h5>
            </CardHeader>
            <CardContent>
              <div className="text-redis-xl font-bold text-redis-blue-03">
                {(performanceData.reduce((sum, d) => sum + d[selectedMetric], 0) / performanceData.length).toFixed(2)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Peak</h5>
            </CardHeader>
            <CardContent>
              <div className="text-redis-xl font-bold text-redis-green">
                {Math.max(...performanceData.map(d => d[selectedMetric])).toFixed(2)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Minimum</h5>
            </CardHeader>
            <CardContent>
              <div className="text-redis-xl font-bold text-redis-red">
                {Math.min(...performanceData.map(d => d[selectedMetric])).toFixed(2)}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  };

  const distributionSection: CollapsibleSection = {
    id: 'distribution',
    title: 'Distribution Charts',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Operation Type Distribution
        </h4>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Bar Chart</h5>
            </CardHeader>
            <CardContent>
              <BarChart data={distributionData} height={250} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Pie Chart</h5>
            </CardHeader>
            <CardContent>
              <PieChart data={distributionData} />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Summary Statistics</h5>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {distributionData.map((item, i) => (
                <div key={i} className="text-center">
                  <div
                    className="w-4 h-4 rounded-redis-xs mx-auto mb-2"
                    style={{ backgroundColor: item.color }}
                  />
                  <div className="text-redis-sm font-medium text-redis-dusk-01">
                    {item.value}%
                  </div>
                  <div className="text-redis-xs text-redis-dusk-04">
                    {item.category}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  };

  const heatmapSection: CollapsibleSection = {
    id: 'heatmap',
    title: 'Activity Heatmap',
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            Weekly Activity Pattern
          </h4>
          <div className="flex items-center gap-2 text-redis-xs text-redis-dusk-04">
            <span>Less</span>
            <div className="flex gap-1">
              {[0.2, 0.4, 0.6, 0.8, 1.0].map(opacity => (
                <div
                  key={opacity}
                  className="w-3 h-3 rounded-redis-xs"
                  style={{ backgroundColor: `rgba(64, 91, 255, ${opacity})` }}
                />
              ))}
            </div>
            <span>More</span>
          </div>
        </div>

        <Card>
          <CardContent>
            <Heatmap data={heatmapData} />
          </CardContent>
        </Card>

        <div className="text-redis-sm text-redis-dusk-04">
          <p>
            This heatmap shows the distribution of Redis operations throughout the week.
            Darker squares indicate higher activity levels during those time periods.
          </p>
        </div>
      </div>
    )
  };

  const gaugesSection: CollapsibleSection = {
    id: 'gauges',
    title: 'Gauge Charts',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          System Health Gauges
        </h4>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          <Card>
            <CardContent className="pt-6">
              <Gauge value={67.3} max={100} label="CPU %" color="#ff4438" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <Gauge value={84.2} max={100} label="Memory %" color="#fbbf24" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <Gauge value={1247} max={2000} label="Connections" color="#405bff" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <Gauge value={2.8} max={10} label="Latency (ms)" color="#3cde67" />
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Performance Score</h5>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center">
                <div className="relative w-48 h-24">
                  <svg width="192" height="96" viewBox="0 0 192 96">
                    <path
                      d="M 20 76 A 76 76 0 0 1 172 76"
                      fill="none"
                      stroke="#2a2f3a"
                      strokeWidth="6"
                    />
                    <path
                      d="M 20 76 A 76 76 0 0 1 172 76"
                      fill="none"
                      stroke="#3cde67"
                      strokeWidth="6"
                      strokeDasharray="185 240"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-end pb-4">
                    <div className="text-3xl font-bold text-redis-green">
                      92
                    </div>
                    <div className="text-redis-sm text-redis-dusk-04">
                      Excellent
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Thresholds</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { label: 'CPU Usage', value: 67.3, threshold: 80, status: 'good' },
                  { label: 'Memory Usage', value: 84.2, threshold: 90, status: 'warning' },
                  { label: 'Connection Pool', value: 62.4, threshold: 90, status: 'good' },
                  { label: 'Response Time', value: 2.8, threshold: 10, status: 'good' }
                ].map((metric, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-redis-sm text-redis-dusk-01">{metric.label}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-redis-sm text-redis-dusk-04">{metric.value}%</span>
                      <div className={`w-2 h-2 rounded-full ${
                        metric.status === 'good' ? 'bg-redis-green' :
                        metric.status === 'warning' ? 'bg-redis-yellow-500' :
                        'bg-redis-red'
                      }`} />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Data Visualization</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Interactive charts and visual analytics for monitoring Redis performance
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Export Data</Button>
          <Button variant="outline">Configure Dashboard</Button>
          <Button variant="primary">Create Report</Button>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Operations', value: '2.4M', change: '+12.3%', positive: true },
          { label: 'Avg Response Time', value: '1.2ms', change: '-8.7%', positive: true },
          { label: 'Memory Usage', value: '67.3%', change: '+2.1%', positive: false },
          { label: 'Active Connections', value: '1,247', change: '+5.9%', positive: true }
        ].map((stat, index) => (
          <Card key={index}>
            <CardContent>
              <div className="flex items-center justify-between mb-2">
                <span className="text-redis-xs text-redis-dusk-04 font-medium">{stat.label}</span>
                <span className={`text-redis-xs font-medium ${
                  stat.positive ? 'text-redis-green' : 'text-redis-red'
                }`}>
                  {stat.change}
                </span>
              </div>
              <div className="text-redis-lg font-bold text-redis-dusk-01">
                {stat.value}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Chart Sections */}
      <CollapsibleCard
        title="Interactive Charts"
        description="Comprehensive data visualization examples using different chart types"
        sections={[timeSeriesSection, distributionSection, heatmapSection, gaugesSection]}
        defaultExpandedSection="timeseries"
        allowMultipleExpanded={true}
      />

      {/* Chart Implementation Notes */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Implementation Notes</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Chart Libraries</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• These examples use SVG and CSS for simplicity</li>
                <li>• For production, consider Chart.js, D3.js, or Recharts</li>
                <li>• Ensure charts are accessible with proper ARIA labels</li>
                <li>• Add keyboard navigation for interactive elements</li>
                <li>• Consider responsive design for mobile devices</li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Performance Tips</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Use React.memo for expensive chart components</li>
                <li>• Implement virtualization for large datasets</li>
                <li>• Debounce real-time updates to prevent excessive renders</li>
                <li>• Cache processed data using useMemo hooks</li>
                <li>• Consider using Canvas for high-frequency updates</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DataVisualization;
