import sreAgentApi from "../sreAgentApi";

// Mock fetch globally
global.fetch = jest.fn();

describe("SREAgentAPI", () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });

  describe("clearConversation", () => {
    it("should successfully clear a conversation", async () => {
      const mockResponse = {
        session_id: "test-thread-123",
        cleared: true,
        message: "Conversation cleared successfully",
      };

      // Mock the cancelTask API call (which clearConversation calls internally)
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await sreAgentApi.clearConversation("test-thread-123");

      expect(result).toEqual({
        session_id: "test-thread-123",
        cleared: true,
        message: "Conversation cleared successfully",
      });

      // Verify the correct API endpoint was called with delete parameter
      expect(fetch).toHaveBeenCalledWith(
        "http://localhost:8080/api/v1/threads/test-thread-123",
        {
          method: "DELETE",
        },
      );
    });

    it("should handle API errors gracefully", async () => {
      // Mock a failed API call
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => "Thread not found",
      });

      const result = await sreAgentApi.clearConversation("nonexistent-thread");

      expect(result).toEqual({
        session_id: "nonexistent-thread",
        cleared: false,
        message:
          "Failed to clear conversation: Error: HTTP 404: Thread not found",
      });
    });

    it("should handle network errors gracefully", async () => {
      // Mock a network error
      (fetch as jest.Mock).mockRejectedValueOnce(new Error("Network error"));

      const result = await sreAgentApi.clearConversation("test-thread-123");

      expect(result).toEqual({
        session_id: "test-thread-123",
        cleared: false,
        message: "Failed to clear conversation: Error: Network error",
      });
    });
  });

  describe("cancelTask", () => {
    it("cancels active tasks for a thread without deleting it", async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        text: async () => "",
      });

      await expect(
        sreAgentApi.cancelTask("test-thread-123"),
      ).resolves.toBeUndefined();

      expect(fetch).toHaveBeenNthCalledWith(
        1,
        "http://localhost:8080/api/v1/threads/test-thread-123/cancel",
        {
          method: "POST",
        },
      );
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("throws when thread cancellation fails", async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => "Thread not found",
      });

      await expect(sreAgentApi.cancelTask("test-thread-123")).rejects.toThrow(
        "HTTP 404: Thread not found",
      );

      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("should throw error for failed thread deletion", async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => "Thread not found",
      });

      await expect(
        sreAgentApi.cancelTask("nonexistent-thread", true),
      ).rejects.toThrow("HTTP 404: Thread not found");
    });
  });

  describe("getTaskStatus", () => {
    it("should successfully get task status", async () => {
      const mockThread = {
        thread_id: "test-thread-123",
        status: "completed",
        messages: [
          {
            role: "assistant",
            content: "Task completed successfully",
            metadata: { timestamp: "2023-01-01T00:01:00Z" },
          },
        ],
        updates: [],
        result: "Task completed successfully",
        metadata: {
          subject: "Test query",
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2023-01-01T00:01:00Z",
          priority: 0,
          tags: [],
        },
        context: {},
        resume_supported: false,
      };

      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockThread,
      });

      const result = await sreAgentApi.getTaskStatus("test-thread-123");

      expect(result).toMatchObject({
        thread_id: "test-thread-123",
        status: "completed",
        messages: [
          {
            role: "assistant",
            content: "Task completed successfully",
            metadata: { timestamp: "2023-01-01T00:01:00Z" },
          },
        ],
        updates: [],
        result: "Task completed successfully",
        resume_supported: false,
        metadata: {
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2023-01-01T00:01:00Z",
          priority: 0,
          tags: [],
          subject: "Test query",
        },
        context: {},
      });
      expect(fetch).toHaveBeenCalledWith(
        "http://localhost:8080/api/v1/threads/test-thread-123",
      );
    });
  });
});
