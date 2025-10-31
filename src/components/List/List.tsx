import React from "react";
import { cn } from "../../utils/cn";

export interface ListProps {
  children: React.ReactNode;
  className?: string;
  divided?: boolean;
}

export const List: React.FC<ListProps> = ({
  children,
  className,
  divided = true,
}) => {
  return (
    <div
      className={cn(divided ? "divide-y divide-redis-dusk-08" : "", className)}
    >
      {children}
    </div>
  );
};
