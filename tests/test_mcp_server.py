import json
import os
import queue
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "integrations" / "mcp" / "yingzhang_mcp.py"
GATE_MESSAGE = "请先确认大纲与代表样张，再批量生成"


def _proxy(test_client):
    """Expose the in-process FastAPI TestClient over real HTTP for the subprocess."""

    class Handler(BaseHTTPRequestHandler):
        def _forward(self):
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() in {"content-type", "accept"}}
            response = test_client.request(self.command, self.path, content=body, headers=headers)
            self.send_response(response.status_code)
            for key in ("content-type", "content-disposition"):
                if key in response.headers:
                    self.send_header(key, response.headers[key])
            self.send_header("content-length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _forward

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class McpProcess:
    def __init__(self, env):
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.next_id = 0

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)

    def send(self, payload):
        self.process.stdin.write((payload if isinstance(payload, str) else json.dumps(payload)) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout=120):
        return json.loads(self.lines.get(timeout=timeout))

    def request(self, method, params=None):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        response = self.receive()
        assert response["id"] == self.next_id
        return response

    def tool(self, name, **arguments):
        response = self.request("tools/call", {"name": name, "arguments": arguments})
        return response["result"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)


@pytest.fixture
def mcp(client, tmp_path):
    proxy = _proxy(client)
    env = {**os.environ, "YINGZHANG_API_URL": f"http://127.0.0.1:{proxy.server_port}",
           "YINGZHANG_MCP_EXPORT_DIR": str(tmp_path / "exports"), "YINGZHANG_MCP_POLL_SECONDS": "0.2",
           "NO_PROXY": "*"}
    process = McpProcess(env)
    try:
        yield process
    finally:
        process.close()
        proxy.shutdown()


def test_protocol_handshake_and_errors(mcp):
    init = mcp.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "pytest", "version": "1"}})["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["capabilities"] == {"tools": {"listChanged": False}}
    assert init["serverInfo"]["name"] == "yingzhang" and "instructions" in init
    mcp.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert mcp.request("ping")["result"] == {}
    legacy = mcp.request("initialize", {"protocolVersion": "2024-11-05"})["result"]
    assert legacy["protocolVersion"] == "2024-11-05" and "title" not in legacy["serverInfo"]
    future = mcp.request("initialize", {"protocolVersion": "2099-01-01"})["result"]
    assert future["protocolVersion"] == "2025-06-18"

    tools = {tool["name"]: tool for tool in mcp.request("tools/list")["result"]["tools"]}
    assert set(tools) == {
        "list_projects", "create_project", "upload_sources", "plan_outline", "generate_deck",
        "get_job_status", "list_slides", "edit_slide", "evaluate", "export",
    }
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools.values())
    assert mcp.request("resources/list")["error"]["code"] == -32601
    assert mcp.request("tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602
    assert mcp.request("tools/call", {"name": "list_slides", "arguments": {}})["error"]["code"] == -32602
    mcp.send("{not json")
    assert mcp.receive()["error"]["code"] == -32700
    mcp.send([{"jsonrpc": "2.0", "id": 99, "method": "ping"}])
    assert mcp.receive()["error"]["code"] == -32600


def test_end_to_end_gated_workflow_through_rest_api(mcp, tmp_path):
    mcp.request("initialize", {"protocolVersion": "2025-06-18"})
    created = mcp.tool("create_project", title="区域零售复盘", preset="review", slide_count=6,
                       audience="经营管理层", instructions="突出结论与行动建议")
    assert created["isError"] is False
    project_id = created["structuredContent"]["project_id"]
    listed = mcp.tool("list_projects")["structuredContent"]["projects"]
    assert any(item["project_id"] == project_id for item in listed)

    material = tmp_path / "复盘材料.md"
    material.write_text(
        "# 区域零售复盘\n\n## 核心结论\n\n华东区销售额同比增长 12%，主要来自会员复购。\n\n"
        "## 风险\n\n库存周转天数上升到 45 天，需要优化补货。\n", encoding="utf-8")
    uploaded = mcp.tool("upload_sources", project_id=project_id,
                        paths=[str(material), str(tmp_path / "missing.pdf")])["structuredContent"]
    assert len(uploaded["uploaded"]) == 1 and uploaded["failed"][0]["path"].endswith("missing.pdf")

    planned = mcp.tool("plan_outline", project_id=project_id, wait_seconds=120)
    assert planned["isError"] is False, planned
    plan = planned["structuredContent"]
    assert plan["job"]["status"] == "completed"
    assert plan["outline"]["gates"]["enabled"] is True
    assert len(plan["outline"]["slides"]) >= 6
    status = mcp.tool("get_job_status", job_id=plan["job"]["job_id"])["structuredContent"]
    assert status["status"] == "completed" and status["kind"] == "outline"

    gated = mcp.tool("generate_deck", project_id=project_id)["structuredContent"]
    assert gated["status"] == "awaiting_outline_confirmation"
    assert GATE_MESSAGE in gated["message"]

    slides = mcp.tool("list_slides", project_id=project_id)["structuredContent"]["slides"]
    edited = mcp.tool("edit_slide", project_id=project_id, position=slides[1]["position"],
                      instruction="把标题改为会员复购驱动增长", value="会员复购驱动增长", rerender=False)
    assert edited["isError"] is False, edited
    assert edited["structuredContent"]["slide"]["title"] == "会员复购驱动增长"
    assert edited["structuredContent"]["change"]["operation"] == "replace"
    missing_value = mcp.tool("edit_slide", project_id=project_id, position=1, instruction="改标题")
    assert missing_value["isError"] is True

    evaluation = mcp.tool("evaluate", project_id=project_id)["structuredContent"]
    assert evaluation["available"] is True and isinstance(evaluation["passed"], bool)

    not_rendered = mcp.tool("export", project_id=project_id, format="pdf")
    assert not_rendered["isError"] is True and "HTTP 409" in not_rendered["content"][0]["text"]
    exported = mcp.tool("export", project_id=project_id, format="pptx", wait_seconds=0)
    assert exported["isError"] is False, exported
    path = Path(exported["structuredContent"]["path"])
    assert path.is_file() and path.suffix == ".pptx" and path.parent == tmp_path / "exports"
    assert path.read_bytes()[:2] == b"PK"


def test_unreachable_api_is_a_tool_error(tmp_path):
    env = {**os.environ, "YINGZHANG_API_URL": "http://127.0.0.1:9", "NO_PROXY": "*"}
    process = McpProcess(env)
    try:
        process.request("initialize", {"protocolVersion": "2025-03-26"})
        result = process.tool("list_projects")
        assert result["isError"] is True and "无法连接映章服务" in result["content"][0]["text"]
        assert "structuredContent" not in result
    finally:
        process.close()
