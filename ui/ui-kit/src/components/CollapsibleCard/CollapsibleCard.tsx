import React, { useState } from "react";
import { Card } from "../Card/Card";
import { Button } from "../Button/Button";
import { ChevronDown, ChevronUp } from "../Icons/ChevronIcons";
import { cn } from "../../utils/cn";

export interface CollapsibleSection {
  id: string;
  title: string;
  icon?: React.ReactNode;
  content: React.ReactNode;
  disabled?: boolean;
}

export interface CollapsibleCardProps {
  title: string;
  description?: string;
  sections: CollapsibleSection[];
  defaultExpandedSection?: string;
  allowMultipleExpanded?: boolean;
  className?: string;
  headerActions?: React.ReactNode;
}

export const CollapsibleCard: React.FC<CollapsibleCardProps> = ({
  title,
  description,
  sections,
  defaultExpandedSection,
  allowMultipleExpanded = false,
  className,
  headerActions,
}) => {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (defaultExpandedSection) {
      initial.add(defaultExpandedSection);
    }
    return initial;
  });

  const toggleSection = (sectionId: string) => {
    setExpandedSections((prev) => {
      const newSet = new Set(prev);

      if (newSet.has(sectionId)) {
        newSet.delete(sectionId);
      } else {
        if (!allowMultipleExpanded) {
          newSet.clear();
        }
        newSet.add(sectionId);
      }

      return newSet;
    });
  };

  return (
    <Card
      className={cn("transition-all duration-200", className)}
      padding="none"
    >
      {/* Header */}
      <div className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-redis-dusk-01 text-redis-lg font-semibold">
              {title}
            </h2>
            {description && (
              <p className="text-redis-dusk-02 text-redis-sm mt-1">
                {description}
              </p>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2">
            {sections.map((section) => (
              <Button
                key={section.id}
                variant="primary"
                size="sm"
                onClick={() => toggleSection(section.id)}
                disabled={section.disabled}
                className="flex items-center gap-2"
              >
                {section.icon && (
                  <span className="h-4 w-4">{section.icon}</span>
                )}
                {section.title}
                {expandedSections.has(section.id) ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            ))}
            {headerActions}
          </div>
        </div>
      </div>

      {/* Separator */}
      <div className="border-redis-dusk-08 border-t" />

      {/* Sections */}
      {sections.map((section) =>
        expandedSections.has(section.id) ? (
          <div
            key={section.id}
            className="border-b border-redis-dusk-08 last:border-b-0"
          >
            {section.content}
          </div>
        ) : null,
      )}
    </Card>
  );
};
