import React from 'react';
import { NavLink } from 'react-router-dom';
import { FiGrid, FiFolder } from 'react-icons/fi';
import './Sidebar.css';

const Sidebar: React.FC = () => {
  return (
    <aside className="sidebar">
      <div className="sidebar-nav">
        <NavLink 
          to="/" 
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          end
        >
          <FiGrid size={18} />
          <span>Dashboard</span>
        </NavLink>
        
        <NavLink 
          to="/projects" 
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <FiFolder size={18} />
          <span>Projects</span>
        </NavLink>
      </div>
      
      <div className="sidebar-footer">
        <div className="status-indicator">
          <span className="dot connected"></span>
          <span>System Online</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;