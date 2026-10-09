export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    const init: RequestInit = { method, credentials: "same-origin", headers: {} };
    if (body instanceof FormData) {
      init.body = body;
    } else if (body !== undefined) {
      init.body = JSON.stringify(body);
      (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    }
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "اتصال به سرور برقرار نشد. اینترنت خود را بررسی کنید و دوباره تلاش کنید.");
  }
  if (res.ok) return (await res.json()) as T;
  let message = "خطای غیرمنتظره رخ داد. دوباره تلاش کنید.";
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") message = data.detail;
  } catch {
    if (res.status === 502 || res.status === 504) message = "سرور در حال به‌روزرسانی است. چند ثانیه بعد دوباره تلاش کنید.";
  }
  throw new ApiError(res.status, message);
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body),
  put: <T>(url: string, body?: unknown) => request<T>("PUT", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
};

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "خطای غیرمنتظره رخ داد.";
}
