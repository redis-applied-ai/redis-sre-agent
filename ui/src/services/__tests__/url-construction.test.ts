/**
 * Test URL construction for different environments
 */

// Mock window.location for testing
const mockLocation = (
  hostname: string,
  port: string,
  protocol: string = "http:",
) => {
  Object.defineProperty(window, "location", {
    value: {
      hostname,
      port,
      protocol,
      origin: `${protocol}//${hostname}${port ? `:${port}` : ""}`,
    },
    writable: true,
  });
};

// Import the API class
import { SREAgentAPI } from "../sreAgentApi";

describe("URL Construction", () => {
  beforeEach(() => {
    // Reset any environment variables
    delete (import.meta as any).env;
  });

  test("should use relative URLs in production", () => {
    mockLocation("example.com", "80");
    const api = new (SREAgentAPI as any)();

    // Access private method for testing
    const baseUrl = api.getApiBaseUrl();
    expect(baseUrl).toBe("/api/v1");
  });

  test("should use current hostname with port 8080 in development", () => {
    mockLocation("localhost", "3000");
    const api = new (SREAgentAPI as any)();

    const baseUrl = api.getApiBaseUrl();
    expect(baseUrl).toBe("http://localhost:8080/api/v1");
  });

  test("should handle different development ports", () => {
    mockLocation("localhost", "3001");
    const api = new (SREAgentAPI as any)();

    const baseUrl = api.getApiBaseUrl();
    expect(baseUrl).toBe("http://localhost:8080/api/v1");
  });

  test("should use environment variable when provided", () => {
    mockLocation("localhost", "3000");

    // Mock import.meta.env
    (import.meta as any).env = {
      VITE_API_BASE_URL: "https://custom-api.example.com/api/v1",
    };

    const api = new (SREAgentAPI as any)();
    const baseUrl = api.getApiBaseUrl();
    expect(baseUrl).toBe("https://custom-api.example.com/api/v1");
  });

  test("should handle remote hosts correctly", () => {
    mockLocation("my-server.example.com", "3000");
    const api = new (SREAgentAPI as any)();

    const baseUrl = api.getApiBaseUrl();
    expect(baseUrl).toBe("http://my-server.example.com:8080/api/v1");
  });
});
