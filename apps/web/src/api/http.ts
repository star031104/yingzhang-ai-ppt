export const base = import.meta.env.VITE_API_URL ?? "/api/v1";

export async function json<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${url}`, init);
  } catch {
    throw new Error("无法连接本地服务。请双击项目中的“启动项目.cmd”，等待启动成功后刷新页面再试；已保存的内容不会丢失。");
  }
  if (!response.ok) {
    const message = await response.text();
    const contentType = response.headers.get("content-type") || "";
    const htmlError = contentType.includes("text/html") || /^\s*<!doctype html/i.test(message);
    if (response.status === 524 || /error code\s*524|a timeout occurred/i.test(message)) {
      throw new Error("公网连接等待超时。任务可能仍在后台执行，请稍后打开项目查看；若未完成可重新生成。");
    }
    if (htmlError) {
      throw new Error(`公网服务暂时不可用（${response.status}），请稍后重试。`);
    }
    try {
      const parsed = JSON.parse(message) as { detail?: string };
      throw new Error(parsed.detail || `请求失败（${response.status}）`);
    } catch (error) {
      if (error instanceof Error && error.message !== "Unexpected end of JSON input") {
        if (!error.message.startsWith("Unexpected token")) throw error;
      }
      throw new Error(message || `请求失败（${response.status}）`);
    }
  }
  return response.json();
}

export const jsonHeaders = { "Content-Type": "application/json" };
