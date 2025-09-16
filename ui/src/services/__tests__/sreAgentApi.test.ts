import sreAgentApi from '../sreAgentApi';

// Mock fetch globally
global.fetch = jest.fn();

describe('SREAgentAPI', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });

  describe('clearConversation', () => {
    it('should successfully clear a conversation', async () => {
      const mockResponse = {
        session_id: 'test-thread-123',
        cleared: true,
        message: 'Conversation cleared successfully'
      };

      // Mock the cancelTask API call (which clearConversation calls internally)
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await sreAgentApi.clearConversation('test-thread-123');

      expect(result).toEqual({
        session_id: 'test-thread-123',
        cleared: true,
        message: 'Conversation cleared successfully'
      });

      // Verify the correct API endpoint was called
      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/tasks/test-thread-123',
        {
          method: 'DELETE',
        }
      );
    });

    it('should handle API errors gracefully', async () => {
      // Mock a failed API call
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => 'Thread not found',
      });

      const result = await sreAgentApi.clearConversation('nonexistent-thread');

      expect(result).toEqual({
        session_id: 'nonexistent-thread',
        cleared: false,
        message: 'Failed to clear conversation: Error: HTTP 404: Thread not found'
      });
    });

    it('should handle network errors gracefully', async () => {
      // Mock a network error
      (fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

      const result = await sreAgentApi.clearConversation('test-thread-123');

      expect(result).toEqual({
        session_id: 'test-thread-123',
        cleared: false,
        message: 'Failed to clear conversation: Error: Network error'
      });
    });
  });

  describe('cancelTask', () => {
    it('should successfully cancel a task', async () => {
      // Mock successful cancellation (204 No Content)
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 204,
      });

      await expect(sreAgentApi.cancelTask('test-thread-123')).resolves.toBeUndefined();

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/tasks/test-thread-123',
        {
          method: 'DELETE',
        }
      );
    });

    it('should throw error for failed cancellation', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => 'Thread not found',
      });

      await expect(sreAgentApi.cancelTask('nonexistent-thread')).rejects.toThrow(
        'HTTP 404: Thread not found'
      );
    });
  });

  describe('getTaskStatus', () => {
    it('should successfully get task status', async () => {
      const mockStatus = {
        thread_id: 'test-thread-123',
        status: 'completed',
        updates: [],
        result: 'Task completed successfully',
        metadata: {
          subject: 'Test query',
          created_at: '2023-01-01T00:00:00Z'
        }
      };

      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockStatus,
      });

      const result = await sreAgentApi.getTaskStatus('test-thread-123');

      expect(result).toEqual(mockStatus);
      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/tasks/test-thread-123'
      );
    });
  });
});
