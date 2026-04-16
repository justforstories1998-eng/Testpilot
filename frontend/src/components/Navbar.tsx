import React from 'react';
import { Link } from 'react-router-dom';
import { FiCommand } from 'react-icons/fi';
import './Navbar.css';

const Navbar: React.FC = () => {
  return (
    <nav className="navbar glass">
      <div className="navbar-brand">
        <div className="brand-logo">
          <FiCommand size={20} />
        </div>
        <Link to="/" className="brand-name">TestPilot</Link>
        <span className="brand-beta">v2.0</span>
      </div>
      
      <div className="navbar-actions">
        {/* Placeholder for future user profile or settings */}
        <div className="user-avatar-small">JS</div>
      </div>
    </nav>
  );
};

export default Navbar;