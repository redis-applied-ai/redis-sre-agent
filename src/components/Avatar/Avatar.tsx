import React from "react";
import { cn } from "../../utils/cn";

export interface AvatarProps {
  src?: string;
  alt?: string;
  size?: "sm" | "md" | "lg";
  fallback?: string;
  className?: string;
  onClick?: () => void;
}

const sizeClasses = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-12 w-12 text-base",
};

export const Avatar: React.FC<AvatarProps> = ({
  src,
  alt = "",
  size = "md",
  fallback,
  className,
  onClick,
}) => {
  const [imageError, setImageError] = React.useState(false);

  const handleImageError = () => {
    setImageError(true);
  };

  const getFallbackContent = () => {
    if (fallback) {
      return fallback.charAt(0).toUpperCase();
    }
    if (alt) {
      return alt.charAt(0).toUpperCase();
    }
    return "?";
  };

  const baseClasses = cn(
    "inline-flex items-center justify-center rounded-full overflow-hidden select-none leading-none bg-redis-dusk-08 text-redis-dusk-01 font-medium border border-redis-dusk-03",
    sizeClasses[size],
    onClick && "cursor-pointer hover:bg-redis-dusk-07 transition-colors",
    className,
  );

  if (src && !imageError) {
    return (
      <div className={baseClasses} onClick={onClick}>
        <img
          src={src}
          alt={alt}
          onError={handleImageError}
          className="h-full w-full rounded-full object-cover"
        />
      </div>
    );
  }

  return (
    <div className={baseClasses} onClick={onClick}>
      <span className="flex h-full w-full items-center justify-center">
        {getFallbackContent()}
      </span>
    </div>
  );
};
