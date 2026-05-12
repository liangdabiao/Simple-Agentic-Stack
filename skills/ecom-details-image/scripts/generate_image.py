#!/usr/bin/env python3
"""使用 apimart.ai 图像生成接口生成图片（异步轮询模式）。

配置来自环境变量或项目根目录 `.env`：
- IMG_BASE_URL: API 根地址，例如 https://api.apimart.ai/v1
- IMG_MODEL: 图片模型名，例如 gpt-image-2
- IMG_API_KEY: API key
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ENV_BASE_URL = "IMG_BASE_URL"
ENV_MODEL = "IMG_MODEL"
ENV_API_KEY = "IMG_API_KEY"
ENV_ALIASES = {
    ENV_BASE_URL: ("OPENAI_BASE_URL", "OPENAI_API_BASE", "BASE_URL"),
    ENV_MODEL: ("OPENAI_IMAGE_MODEL", "IMAGE_MODEL", "OPENAI_MODEL"),
    ENV_API_KEY: ("OPENAI_API_KEY", "API_KEY"),
}

VALID_SIZES = ("auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
               "16:9", "9:16", "2:1", "1:2", "21:9", "9:21")
VALID_RESOLUTIONS = ("1k", "2k", "4k")


def fail(message: str, exit_code: int = 1) -> None:
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(exit_code)


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        prompt = args.prompt.strip()
    else:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            fail(f"无法读取 prompt 文件：{exc}")
    if not prompt:
        fail("prompt 不能为空。")
    return prompt


def strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def find_default_env_file() -> Path | None:
    for directory in (Path.cwd(), *Path.cwd().parents):
        env_file = directory / ".env"
        if env_file.is_file():
            return env_file
    return None


def load_env_file(env_file: Path | None) -> None:
    if env_file is None:
        return
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"无法读取 .env 文件：{exc}")
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            fail(f".env 第 {line_number} 行格式不正确，应为 KEY=value。")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            fail(f".env 第 {line_number} 行缺少变量名。")
        if key not in os.environ:
            os.environ[key] = strip_env_value(value)


def require_config(name: str) -> str:
    candidates = (name, *ENV_ALIASES.get(name, ()))
    value = ""
    for candidate in candidates:
        value = os.environ.get(candidate, "").strip()
        if value:
            return value
    accepted = "、".join(candidates)
    fail(
        f"缺少配置 {name}。请在 .env 中设置 IMG_BASE_URL、IMG_MODEL、IMG_API_KEY；"
        f"也兼容这些变量名：{accepted}。"
    )


def encode_image_as_data_uri(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        fail(f"参考图片不存在：{image_path}")
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}
    mime = mime_map.get(suffix)
    if not mime:
        fail(f"不支持的图片格式：.{suffix}，仅支持 png/jpg/jpeg/webp/gif。")
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(f"无法读取参考图片：{exc}")
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_payload(args: argparse.Namespace, prompt: str, model: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": args.size,
        "resolution": args.resolution,
    }
    if args.image:
        payload["image_urls"] = [encode_image_as_data_uri(args.image)]
    return payload


def http_post(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"接口返回 HTTP {exc.code}：{detail}")
    except urllib.error.URLError as exc:
        fail(f"无法连接接口：{exc.reason}")
    except (http.client.RemoteDisconnected, TimeoutError):
        fail("接口连接失败或超时，请稍后重试。")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"接口返回的不是有效 JSON：{raw[:500]}")
    if not isinstance(parsed, dict):
        fail("接口返回格式不正确：顶层结果不是对象。")
    return parsed


def http_get(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"查询接口返回 HTTP {exc.code}：{detail}")
    except (urllib.error.URLError, http.client.RemoteDisconnected, TimeoutError):
        fail("查询接口连接失败或超时。")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"查询接口返回的不是有效 JSON：{raw[:500]}")
    return parsed


def submit_task(base_url: str, api_key: str, payload: dict[str, Any]) -> str:
    endpoint = f"{base_url}/images/generations"
    result = http_post(endpoint, api_key, payload)
    code = result.get("code")
    if code and code != 200:
        error = result.get("error", {})
        fail(f"提交失败（code={code}）：{error.get('message', json.dumps(result))}")
    data = result.get("data")
    if not isinstance(data, list) or not data:
        fail(f"提交响应缺少 data 数组：{json.dumps(result)[:300]}")
    task_id = data[0].get("task_id")
    if not task_id:
        fail(f"提交响应缺少 task_id：{json.dumps(data[0])[:300]}")
    return task_id


def poll_task(base_url: str, api_key: str, task_id: str,
              poll_interval: int, timeout: int) -> dict[str, Any]:
    url = f"{base_url}/tasks/{task_id}"
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            fail(f"任务 {task_id} 超时（{timeout}s），请稍后手动查询。")
        result = http_get(url, api_key)
        task_data = result.get("data", {})
        status = task_data.get("status", "")
        if status == "completed":
            return task_data
        if status == "failed":
            error = task_data.get("error", {})
            fail(f"任务 {task_id} 失败：{error.get('message', json.dumps(task_data)[:300])}")
        progress = task_data.get("progress", 0)
        print(f"  轮询中... 状态={status} 进度={progress}% 耗时={elapsed:.0f}s",
              file=sys.stderr)
        time.sleep(poll_interval)


def filename_for(suffix: str) -> str:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return f"image-{timestamp}-01.{suffix.lstrip('.')}"


def suffix_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower().lstrip(".")
    return "jpg" if suffix == "jpeg" else (suffix if suffix in {"png", "jpg", "webp"} else "png")


def download_image(url: str, output_dir: Path, fmt: str) -> Path:
    suffix = suffix_from_url(url) or fmt
    output_path = output_dir / filename_for(suffix)
    print(f"  下载图片: {url}", file=sys.stderr)
    dl_request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    })
    try:
        with urllib.request.urlopen(dl_request, timeout=120) as response:
            image_bytes = response.read()
    except urllib.error.URLError as exc:
        fail(f"无法下载图片：{exc.reason}")
    except TimeoutError:
        fail("下载图片超时。")
    try:
        output_path.write_bytes(image_bytes)
    except OSError as exc:
        fail(f"无法写入图片文件：{exc}")
    return output_path


def save_results(task_data: dict[str, Any], output_dir: Path, fmt: str) -> list[Path]:
    result = task_data.get("result", {})
    images = result.get("images")
    if not isinstance(images, list) or not images:
        fail(f"任务结果中缺少 images 数组：{json.dumps(task_data)[:300]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, img_item in enumerate(images):
        url_list = img_item.get("url")
        if not isinstance(url_list, list) or not url_list:
            fail(f"图片结果缺少 url 数组：{json.dumps(img_item)[:300]}")
        image_url = url_list[0]
        if not isinstance(image_url, str) or not image_url:
            fail(f"图片 URL 为空：{json.dumps(url_list)[:300]}")
        paths.append(download_image(image_url, output_dir, fmt))
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 apimart.ai 图像接口生成图片（异步轮询模式）。"
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="直接传入图片生成 Prompt。")
    prompt_group.add_argument("--prompt-file", help="从文本文件读取图片生成 Prompt。")
    parser.add_argument(
        "--output-dir",
        default="generated-images",
        help="图片输出目录，默认 generated-images。",
    )
    parser.add_argument(
        "--env-file",
        help="指定 .env 配置文件；不指定时从当前目录向上查找 .env。",
    )
    parser.add_argument(
        "--size",
        default="1:1",
        help=f"图片比例，默认 1:1。可选：{', '.join(VALID_SIZES)}",
    )
    parser.add_argument(
        "--resolution",
        default="2k",
        choices=VALID_RESOLUTIONS,
        help="输出分辨率档位，默认 2k。",
    )
    parser.add_argument(
        "--image",
        help="参考产品图片路径（支持多张，逗号分隔），传入 image_urls 以提升产品一致性。",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="轮询间隔秒数，默认 5。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="轮询超时秒数，默认 180。",
    )
    parser.add_argument(
        "--format",
        choices=("png", "jpeg", "webp"),
        default="png",
        help="图片下载后保存格式（仅影响文件扩展名），默认 png。",
    )
    args = parser.parse_args()
    if args.size not in VALID_SIZES:
        fail(f"--size 不合法：{args.size}。可选值：{', '.join(VALID_SIZES)}")
    return args


def main() -> None:
    args = parse_args()
    env_file = Path(args.env_file) if args.env_file else find_default_env_file()
    load_env_file(env_file)
    prompt = read_prompt(args)
    base_url = require_config(ENV_BASE_URL).rstrip("/")
    model = require_config(ENV_MODEL)
    api_key = require_config(ENV_API_KEY)

    payload = build_payload(args, prompt, model)

    print("提交生成任务...", file=sys.stderr)
    task_id = submit_task(base_url, api_key, payload)
    print(f"任务已提交: {task_id}，开始轮询...", file=sys.stderr)

    time.sleep(15)
    task_data = poll_task(base_url, api_key, task_id, args.poll_interval, args.timeout)

    actual_time = task_data.get("actual_time", 0)
    cost = task_data.get("cost", 0)
    print(f"任务完成，耗时 {actual_time}s，费用 ${cost:.4f}", file=sys.stderr)

    paths = save_results(task_data, Path(args.output_dir), args.format)
    print("生成完成：")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
