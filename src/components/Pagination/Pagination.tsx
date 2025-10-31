import React from "react";
import {
  ChevronDoubleLeft,
  ChevronLeft,
  ChevronRight,
  ChevronDoubleRight,
} from "../Icons/ChevronIcons";
import { cn } from "../../utils/cn";

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  itemCount: number;
  onPageChange: (page: number) => void;
  itemLabel?: string;
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (pageSize: number) => void;
  className?: string;
  showPageSizeSelector?: boolean;
  showPageInput?: boolean;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  itemCount,
  onPageChange,
  itemLabel = "items",
  pageSize = 10,
  pageSizeOptions = [10, 25, 50, 100],
  onPageSizeChange,
  className,
  showPageSizeSelector = true,
  showPageInput = true,
}) => {
  const handlePageSizeChange = (newSize: number) => {
    if (onPageSizeChange) {
      onPageSizeChange(newSize);
      // Reset to first page when page size changes
      onPageChange(1);
    }
  };

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const page = parseInt(e.target.value);
    if (page >= 1 && page <= totalPages) {
      onPageChange(page);
    }
  };

  return (
    <div
      className={cn(
        "border-redis-dusk-08 rounded-b-redis-sm bg-redis-midnight flex items-center justify-between border border-t-0 px-4 py-3 min-h-12",
        className,
      )}
    >
      <div className="text-redis-xs text-redis-dusk-04">
        Showing {itemCount} {itemLabel}
      </div>

      <div className="flex items-center space-x-6">
        {showPageSizeSelector && onPageSizeChange && (
          <div className="flex items-center space-x-2.5">
            <span className="text-redis-xs text-redis-dusk-04">
              Items per page
            </span>
            <div className="relative">
              <select
                className="text-redis-dusk-01 text-redis-xs bg-redis-dusk-09 border-redis-dusk-07 h-7 w-16 rounded-md border pl-2 pr-7 focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                value={pageSize}
                onChange={(e) => handlePageSizeChange(parseInt(e.target.value))}
              >
                {pageSizeOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className="flex items-center space-x-1.5">
          <button
            className="hover:bg-redis-dusk-09 rounded-md p-1.5 disabled:opacity-50 disabled:hover:bg-transparent"
            onClick={() => onPageChange(Math.max(currentPage - 2, 1))}
            disabled={currentPage <= 2}
            aria-label="Go to first pages"
          >
            <ChevronDoubleLeft className="text-redis-dusk-01" />
          </button>
          <button
            className="hover:bg-redis-dusk-09 rounded-md p-1.5 disabled:opacity-50 disabled:hover:bg-transparent"
            onClick={() => onPageChange(Math.max(currentPage - 1, 1))}
            disabled={currentPage === 1}
            aria-label="Go to previous page"
          >
            <ChevronLeft className="text-redis-dusk-01" />
          </button>
          <span className="text-redis-xs mx-2 text-redis-dusk-01">
            {currentPage} of {totalPages || 1}
          </span>
          <button
            className="hover:bg-redis-dusk-09 rounded-md p-1.5 disabled:opacity-50 disabled:hover:bg-transparent"
            onClick={() => onPageChange(Math.min(currentPage + 1, totalPages))}
            disabled={currentPage === totalPages || totalPages === 0}
            aria-label="Go to next page"
          >
            <ChevronRight className="text-redis-dusk-01" />
          </button>
          <button
            className="hover:bg-redis-dusk-09 rounded-md p-1.5 disabled:opacity-50 disabled:hover:bg-transparent"
            onClick={() => onPageChange(Math.min(currentPage + 2, totalPages))}
            disabled={currentPage >= totalPages - 1}
            aria-label="Go to last pages"
          >
            <ChevronDoubleRight className="text-redis-dusk-01" />
          </button>
        </div>

        {showPageInput && (
          <div className="flex items-center space-x-2.5">
            <span className="text-redis-xs text-redis-dusk-04">Page</span>
            <div className="relative">
              <input
                type="number"
                min="1"
                max={totalPages}
                value={currentPage}
                onChange={handlePageInputChange}
                className="text-redis-xs bg-redis-dusk-09 border-redis-dusk-07 text-redis-dusk-01 h-7 w-12 rounded-md border px-2 focus:outline-none focus:ring-2 focus:ring-redis-blue-03 focus:border-transparent"
              />
            </div>
            <span className="text-redis-xs text-redis-dusk-04">
              of {totalPages || 1}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
