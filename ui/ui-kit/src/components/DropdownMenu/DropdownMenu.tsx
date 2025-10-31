import React, { useState, useRef, useEffect } from "react";
import { cn } from "../../utils/cn";

export interface DropdownMenuItem {
  label: string;
  icon?: React.ReactNode;
  href?: string;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "destructive";
}

export interface DropdownMenuProps {
  trigger: React.ReactNode;
  items: DropdownMenuItem[];
  className?: string;
  menuClassName?: string;
  placement?: "bottom-right" | "bottom-left" | "top-right" | "top-left";
}

export const DropdownMenu: React.FC<DropdownMenuProps> = ({
  trigger,
  items,
  className,
  menuClassName,
  placement = "bottom-right",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click or Escape
  useEffect(() => {
    if (!isOpen) return;
    const onDocumentClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        !dropdownRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setIsOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("click", onDocumentClick);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [isOpen]);

  const getMenuPositionClasses = () => {
    switch (placement) {
      case "bottom-left":
        return "left-0 mt-2";
      case "top-right":
        return "right-0 mb-2 bottom-full";
      case "top-left":
        return "left-0 mb-2 bottom-full";
      default: // bottom-right
        return "right-0 mt-2";
    }
  };

  // No portal positioning needed; we will anchor with absolute inside the wrapper

  const handleItemClick = (item: DropdownMenuItem) => {
    if (item.disabled) return;

    if (item.onClick) {
      item.onClick();
    }
    setIsOpen(false);
  };

  return (
    <div
      className={cn("relative z-40", className)}
      tabIndex={0}
      ref={dropdownRef}
      data-testid="dropdown-menu"
    >
      <div
        ref={buttonRef}
        role="button"
        tabIndex={0}
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setIsOpen((prev) => !prev);
          }
        }}
        className="inline-flex cursor-pointer items-center justify-center p-0"
      >
        {trigger}
      </div>

      {isOpen && (
        <div
          className={cn(
            "absolute right-0 mt-2 w-48 rounded-redis-sm border border-redis-dusk-08 bg-redis-midnight shadow-xl z-[9999]",
            getMenuPositionClasses(),
            menuClassName,
          )}
          ref={menuRef}
        >
          <div className="py-1">
            {items.map((item, index) => {
              const itemClasses = cn(
                "flex items-center gap-2 px-4 py-2 text-redis-sm transition-colors cursor-pointer",
                item.disabled
                  ? "opacity-50 cursor-not-allowed"
                  : item.variant === "destructive"
                    ? "text-redis-red hover:bg-redis-red/10"
                    : "text-redis-dusk-01 hover:bg-redis-dusk-09",
              );

              const content = (
                <>
                  {item.icon && (
                    <span className="flex-shrink-0">{item.icon}</span>
                  )}
                  <span>{item.label}</span>
                </>
              );

              if (item.href && !item.disabled) {
                return (
                  <a
                    key={index}
                    href={item.href}
                    className={itemClasses}
                    onClick={() => setIsOpen(false)}
                  >
                    {content}
                  </a>
                );
              }

              return (
                <button
                  key={index}
                  onClick={() => handleItemClick(item)}
                  className={cn(itemClasses, "w-full text-left")}
                  disabled={item.disabled}
                >
                  {content}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
