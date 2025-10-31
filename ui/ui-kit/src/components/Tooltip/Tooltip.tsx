import { useState, useRef, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  className?: string;
  placement?: "top" | "bottom" | "left" | "right";
}

export const Tooltip = ({
  content,
  children,
  className,
  placement = "top",
}: TooltipProps) => {
  const [isVisible, setIsVisible] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    if (triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();

      let top = 0;
      let left = 0;

      switch (placement) {
        case "top":
          top = triggerRect.top - tooltipRect.height - 8;
          left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2;
          break;
        case "bottom":
          top = triggerRect.bottom + 8;
          left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2;
          break;
        case "left":
          top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2;
          left = triggerRect.left - tooltipRect.width - 8;
          break;
        case "right":
          top = triggerRect.top + (triggerRect.height - tooltipRect.height) / 2;
          left = triggerRect.right + 8;
          break;
      }

      // Adjust for viewport boundaries
      if (top < 0) {
        top = triggerRect.bottom + 8;
      }
      if (left < 0) {
        left = 8;
      } else if (left + tooltipRect.width > window.innerWidth) {
        left = window.innerWidth - tooltipRect.width - 8;
      }

      setPosition({ top, left });
    }
  }, [placement]);

  useEffect(() => {
    if (isVisible) {
      updatePosition();
      window.addEventListener("scroll", updatePosition);
      window.addEventListener("resize", updatePosition);

      return () => {
        window.removeEventListener("scroll", updatePosition);
        window.removeEventListener("resize", updatePosition);
      };
    }
  }, [isVisible, updatePosition]);

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        className={cn("inline-block", className)}
      >
        {children}
      </div>

      {isVisible && (
        <div
          ref={tooltipRef}
          className="bg-redis-midnight border-redis-dusk-08 rounded-redis-sm text-redis-dusk-01 fixed z-50 max-w-xs border px-3 py-2 text-redis-sm shadow-lg"
          style={{
            top: `${position.top}px`,
            left: `${position.left}px`,
          }}
        >
          {content}
        </div>
      )}
    </>
  );
};
