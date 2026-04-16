import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FiFolder, FiPlus, FiSearch, FiTrash2,
  FiExternalLink, FiClock
} from 'react-icons/fi';
import Modal from '../components/Modal';
import Input from '../components/Input';
import Button from '../components/Button';
import {
  listProjects,
  createProject,
  deleteProject,
  extractError
} from '../services/api';
import type { Project } from '../types';
import toast from 'react-hot-toast';
import './Projects.css';

const Projects: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const data = await listProjects({ search: search || undefined });
      setProjects(data.items);
    } catch {
      toast.error('Failed to load projects');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(fetchProjects, 300);
    return () => clearTimeout(t);
  }, [search]);

  const handleCreate = async () => {
    if (!newName || !newUrl) {
      toast.error('Name and URL are required');
      return;
    }
    setCreating(true);
    try {
      await createProject({ name: newName, base_url: newUrl });
      toast.success('Project created');
      setShowCreate(false);
      setNewName('');
      setNewUrl('');
      fetchProjects();
    } catch (err) {
      toast.error(extractError(err));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this project and all its data?')) return;
    try {
      await deleteProject(id);
      toast.success('Project deleted');
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch {
      toast.error('Failed to delete');
    }
  };

  return (
    <div className="projects-page animate-fade">
      <div className="projects-header">
        <div>
          <h1 className="heading-1">Projects</h1>
          <p className="text-muted text-sm">Manage your testing projects</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          <FiPlus size={16} />
          <span>New Project</span>
        </button>
      </div>

      <div className="projects-toolbar">
        <div className="search-box glass">
          <FiSearch className="search-icon" />
          <input
            type="text"
            placeholder="Search projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : projects.length === 0 ? (
        <div className="empty-state glass">
          <FiFolder size={48} />
          <h3>No projects found</h3>
          <p>Create a new project to start testing</p>
          <button className="btn-secondary" onClick={() => setShowCreate(true)}>
            Create Project
          </button>
        </div>
      ) : (
        <div className="projects-list">
          {projects.map((project) => (
            <div
              key={project.id}
              className="project-row glass card-3d"
              onClick={() => navigate(`/project/${project.id}`)}
            >
              <div className="project-icon">
                <FiFolder size={20} />
              </div>

              <div className="project-info">
                <h3 className="project-title">{project.name}</h3>
                <a
                  href={project.base_url}
                  target="_blank"
                  rel="noreferrer"
                  className="project-url"
                  onClick={(e) => e.stopPropagation()}
                >
                  {project.base_url} <FiExternalLink size={10} />
                </a>
              </div>

              <div className="project-meta">
                {project.last_pass_rate !== undefined && project.last_pass_rate !== null && (
                  <div className="meta-item">
                    <span className="meta-label">Pass Rate</span>
                    <span className={`meta-value ${
                      project.last_pass_rate >= 80 ? 'text-success' : 'text-warning'
                    }`}>
                      {project.last_pass_rate}%
                    </span>
                  </div>
                )}
                <div className="meta-item">
                  <span className="meta-label">Updated</span>
                  <span className="meta-value">
                    <FiClock size={12} />
                    {new Date(project.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </div>

              <button
                className="btn-icon-danger project-delete"
                onClick={(e) => handleDelete(project.id, e)}
                title="Delete project"
              >
                <FiTrash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      <Modal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        title="Create New Project"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} loading={creating}>Create Project</Button>
          </div>
        }
      >
        <div className="form-stack">
          <Input
            label="Project Name"
            placeholder="e.g., E-Commerce Platform"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            autoFocus
          />
          <Input
            label="Base URL"
            placeholder="https://example.com"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
          />
        </div>
      </Modal>
    </div>
  );
};

export default Projects;