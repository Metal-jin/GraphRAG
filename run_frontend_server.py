from wsgiref.simple_server import make_server
import json
import sys
import os

# 把项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 把 src 目录也加入路径，让 service.py 里的 `from core.xxx` 能找到模块
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.generate.service import get_available_methods, ask_question


def application(environ, start_response):
    # 允许跨域，方便本地开发
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    ]

    # 处理预检请求
    if environ["REQUEST_METHOD"] == "OPTIONS":
        start_response("200 OK", headers)
        return [b""]

    path = environ["PATH_INFO"]

    # 获取方法列表
    if path == "/api/methods" and environ["REQUEST_METHOD"] == "GET":
        start_response("200 OK", headers)
        result = get_available_methods()
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    # 问答接口
    elif path == "/api/ask" and environ["REQUEST_METHOD"] == "POST":
        # 读取请求体
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ["wsgi.input"].read(content_length).decode("utf-8")
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            start_response("400 Bad Request", headers)
            return [json.dumps({"error": "请求格式错误"}).encode("utf-8")]

        result = ask_question(**params)
        start_response("200 OK", headers)
        return [json.dumps(result, ensure_ascii=False).encode("utf-8")]

    else:
        start_response("404 Not Found", headers)
        return [json.dumps({"error": "接口不存在"}).encode("utf-8")]


if __name__ == "__main__":
    port = 5000
    with make_server("", port, application) as httpd:
        print(f"前端服务已启动，端口: {port}")
        print(f"请打开 frontend/index.html 查看页面")
        httpd.serve_forever()
