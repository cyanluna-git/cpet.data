import { Link } from 'react-router-dom';
import './Dashboard.css';

interface StatsCardProps {
  title: string;
  value: string | number;
  description: string;
  link: string;
}

function StatsCard({ title, value, description, link }: StatsCardProps) {
  return (
    <Link to={link} className="stats-card">
      <h3>{title}</h3>
      <div className="stats-value">{value}</div>
      <p className="stats-description">{description}</p>
    </Link>
  );
}

function Dashboard() {
  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>CPET Platform</h1>
        <p>Cardiopulmonary Exercise Testing Management System</p>
      </header>

      <div className="stats-grid">
        <StatsCard
          title="Total Subjects"
          value="24"
          description="Registered subjects in the system"
          link="/subjects"
        />
        <StatsCard
          title="Active Tests"
          value="3"
          description="Currently running CPET tests"
          link="/tests"
        />
        <StatsCard
          title="Completed Tests"
          value="156"
          description="Total completed tests"
          link="/results"
        />
        <StatsCard
          title="Pending Analysis"
          value="7"
          description="Tests awaiting analysis"
          link="/analysis"
        />
      </div>

      <div className="quick-actions">
        <h2>Quick Actions</h2>
        <div className="action-buttons">
          <Link to="/subjects/new" className="action-button primary">
            + New Subject
          </Link>
          <Link to="/tests/new" className="action-button secondary">
            Start CPET Test
          </Link>
          <Link to="/results" className="action-button secondary">
            View Results
          </Link>
        </div>
      </div>

      <div className="recent-activity">
        <h2>Recent Activity</h2>
        <div className="activity-list">
          <div className="activity-item">
            <div className="activity-icon">✓</div>
            <div className="activity-content">
              <p className="activity-title">CPET Test Completed</p>
              <p className="activity-meta">Subject: John Doe • 2 hours ago</p>
            </div>
          </div>
          <div className="activity-item">
            <div className="activity-icon">+</div>
            <div className="activity-content">
              <p className="activity-title">New Subject Registered</p>
              <p className="activity-meta">Subject: Jane Smith • 5 hours ago</p>
            </div>
          </div>
          <div className="activity-item">
            <div className="activity-icon">📊</div>
            <div className="activity-content">
              <p className="activity-title">Analysis Report Generated</p>
              <p className="activity-meta">Test ID: #1234 • 1 day ago</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
