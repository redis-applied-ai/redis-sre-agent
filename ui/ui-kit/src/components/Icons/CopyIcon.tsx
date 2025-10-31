import React from "react";

export interface CopyIconProps {
  className?: string;
  size?: number;
}

export const CopyIcon: React.FC<CopyIconProps> = ({
  className = "",
  size = 24,
}) => (
  <svg
    className={className}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={1.75}
    width={size}
    height={size}
  >
    <rect
      x="9"
      y="9"
      width="13"
      height="13"
      rx="2"
      className="fill-none stroke-current"
      strokeWidth={1.75}
    />
    <rect
      x="3"
      y="3"
      width="13"
      height="13"
      rx="2"
      className="fill-none stroke-current"
      strokeWidth={1.75}
    />
  </svg>
);
