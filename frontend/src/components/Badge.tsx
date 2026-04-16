import React from 'react';

interface BadgeProps {
  status: string;
}

export const StatusBadge: React.FC<BadgeProps> = ({ status }) => {
  let type = 'neutral';
  
  switch (status.toLowerCase()) {
    case 'passed':
    case 'completed':
    case 'success':
      type = 'success';
      break;
    case 'failed':
    case 'error':
      type = 'error';
      break;
    case 'running':
    case 'pending':
      type = 'warning';
      break;
    case 'skipped':
      type = 'neutral';
      break;
  }

  return (
    <span className={`badge badge--${type}`}>
      {status}
    </span>
  );
};