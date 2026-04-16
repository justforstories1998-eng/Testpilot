import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'rgba(20, 20, 40, 0.95)',
            color: '#e2e8f0',
            border: '1px solid rgba(99, 102, 241, 0.2)',
            backdropFilter: 'blur(20px)',
            borderRadius: '12px',
            fontSize: '0.85rem',
            padding: '12px 16px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
          },
          success: {
            iconTheme: { primary: '#22c55e', secondary: '#0a0a1a' },
          },
          error: {
            iconTheme: { primary: '#ef4444', secondary: '#0a0a1a' },
          },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>
);