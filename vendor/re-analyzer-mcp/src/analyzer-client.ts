import axios, {
  AxiosBasicCredentials,
  AxiosInstance,
  AxiosRequestConfig,
} from "axios";
import { AnalyzerApi, AnalyzerConfig } from "./types";

export class AnalyzerClient implements AnalyzerApi {
  private readonly http: AxiosInstance;

  constructor(
    private readonly config: AnalyzerConfig,
    http?: AxiosInstance,
  ) {
    this.http =
      http ??
      axios.create({
        baseURL: this.config.analyzerBaseUrl,
        timeout: this.config.requestTimeoutMs,
      });
  }

  public async getApi<T>(
    path: string,
    params?: Record<string, unknown>,
  ): Promise<T> {
    const response = await this.http.request<T>({
      ...this.buildApiRequest("GET", path),
      params,
    });

    return response.data;
  }

  public async postApi<T>(
    path: string,
    data?: Record<string, unknown>,
  ): Promise<T> {
    const response = await this.http.request<T>({
      ...this.buildApiRequest("POST", path),
      data,
    });

    return response.data;
  }

  public async getPrivate<T>(
    path: string,
    params?: Record<string, unknown>,
  ): Promise<T> {
    const response = await this.http.request<T>({
      ...this.buildPrivateRequest("GET", path),
      params,
    });

    return response.data;
  }

  private buildApiRequest(
    method: AxiosRequestConfig["method"],
    url: string,
  ): AxiosRequestConfig {
    return {
      method,
      baseURL: this.config.analyzerBaseUrl,
      url,
      timeout: this.config.requestTimeoutMs,
      headers: {
        Authorization: `Bearer ${this.config.analyzerApiToken}`,
      },
    };
  }

  private buildPrivateRequest(
    method: AxiosRequestConfig["method"],
    url: string,
  ): AxiosRequestConfig {
    return {
      ...this.buildApiRequest(method, url),
      auth: this.getReportAuth(),
    };
  }

  private getReportAuth(): AxiosBasicCredentials {
    if (
      !this.config.analyzerReportUser ||
      !this.config.analyzerReportPassword
    ) {
      throw new Error(
        "Analyzer report credentials are required for private endpoints",
      );
    }

    return {
      username: this.config.analyzerReportUser,
      password: this.config.analyzerReportPassword,
    };
  }
}
