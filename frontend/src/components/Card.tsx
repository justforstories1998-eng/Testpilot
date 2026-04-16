import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
  glass?: boolean;
  hover3d?: boolean;
}

const Card: React.FC<CardProps> = ({
  children,
  className = '',
  noPadding = false,
  glass = true,
  hover3d = false,
}) => {
  const baseClass = glass ? 'glass' : 'card-basic';
  const hoverClass = hover3d ? 'card-3d' : '';
  const paddingClass = noPadding ? 'p-0' : 'p-6';

  return (
    <div className={`${baseClass} ${hoverClass} ${paddingClass} ${className}`}>
      {children}
    </div>
  );
};

export default Card;