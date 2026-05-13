import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

SKILL_DIR = Path(os.environ.get("ECOM_SKILL_DIR", ".")).resolve()
TEMPLATES_DIR = SKILL_DIR / "references" / "templates"
SCRIPTS_DIR = SKILL_DIR / "scripts"

# Import generate_image functions directly
sys.path.insert(0, str(SCRIPTS_DIR))
from generate_image import (
    build_payload,
    download_image,
    encode_image_as_data_uri,
    fail,
    find_default_env_file,
    load_env_file,
    poll_task,
    require_config,
    save_results,
    submit_task,
    ENV_BASE_URL,
    ENV_MODEL,
    ENV_API_KEY,
)

# Load .env at import time
_skill_env = SKILL_DIR / ".env"
if _skill_env.is_file():
    load_env_file(_skill_env)
else:
    load_env_file(find_default_env_file())

mcp = FastMCP("ecom_image")


def _load_template_index() -> list[dict[str, Any]]:
    index = []
    if not TEMPLATES_DIR.is_dir():
        return index
    for fp in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            index.append({
                "file": fp.name,
                "id": data.get("id", ""),
                "name": data.get("name", ""),
                "keywords": data.get("keywords", []),
                "trigger_phrases": data.get("trigger_phrases", []),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return index


_TEMPLATE_INDEX = _load_template_index()


@mcp.tool()
def list_templates() -> list[dict[str, Any]]:
    """列出所有可用的电商图片场景模板。
    返回：
        每个模板包含 file（文件名）、id、name（中文名）、keywords、trigger_phrases。
    """
    return _TEMPLATE_INDEX


@mcp.tool()
def find_template(keywords: str) -> dict[str, Any]:
    """根据关键词匹配最佳场景模板，返回完整模板内容。
    参数：
        keywords: 用户描述中的关键词，用空格或逗号分隔。
            例如 "白底 主图"、"小红书"、"lifestyle 生活图"。
    返回：
        匹配度最高的模板完整 JSON（包含 prompt_template、variants、
        category_tips、examples、anti_ai_tips 等）。
        无匹配时返回 01-hero-image.json 作为默认。
    """
    input_words = set(keywords.replace(",", " ").lower().split())
    best_score = -1
    best_file = "01-hero-image.json"

    for tpl in _TEMPLATE_INDEX:
        searchable = set(
            w.lower()
            for w in tpl.get("keywords", []) + tpl.get("trigger_phrases", [])
        )
        score = len(input_words & searchable)
        if score > best_score:
            best_score = score
            best_file = tpl["file"]

    tpl_path = TEMPLATES_DIR / best_file
    if not tpl_path.is_file():
        return {"error": f"模板文件不存在：{best_file}"}
    try:
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"读取模板失败：{e}"}
    return {"matched_file": best_file, "match_score": best_score, "template": data}


@mcp.tool()
def read_template(template_file: str) -> dict[str, Any]:
    """读取指定模板文件的完整内容。
    参数：
        template_file: 模板文件名，例如 '01-hero-image.json'。
    返回：
        模板的完整 JSON 内容。
    """
    safe_name = Path(template_file).name
    tpl_path = TEMPLATES_DIR / safe_name
    if not tpl_path.is_file():
        return {"error": f"模板不存在：{safe_name}，可用模板：{[t['file'] for t in _TEMPLATE_INDEX]}"}
    try:
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"读取模板失败：{e}"}
    return data


@mcp.tool()
def generate_image(
    prompt: str,
    size: str = "1:1",
    resolution: str = "2k",
    image: str | None = None,
    output_dir: str | None = None,
    poll_interval: int = 5,
    timeout: int = 300,
    fmt: str = "png",
) -> dict[str, Any]:
    """调用生图 API 生成电商图片。
    参数：
        prompt: 图片生成 Prompt。
        size: 图片比例，默认 '1:1'。可选：auto, 1:1, 3:2, 2:3, 4:3, 3:4,
              5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 21:9, 9:21。
        resolution: 分辨率档位，默认 '2k'。可选：1k, 2k, 4k。
        image: 参考产品图片路径（可选），传入后走图生图模式。
        output_dir: 输出目录，默认 'generated-images'。
        poll_interval: 轮询间隔秒数，默认 5。
        timeout: 轮询超时秒数，默认 300。
        fmt: 图片格式，默认 'png'。
    返回：
        包含 'success'（布尔值）的字典。成功时包含 'files'（生成文件路径列表）
        和 'cost'。失败时包含 'error'。
    """
    try:
        base_url = require_config(ENV_BASE_URL).rstrip("/")
        model = require_config(ENV_MODEL)
        api_key = require_config(ENV_API_KEY)
    except SystemExit as e:
        return {"error": "缺少生图 API 配置，请在 .env 中设置 IMG_BASE_URL、IMG_MODEL、IMG_API_KEY"}

    # Resolve image path relative to SKILL_DIR
    image_path = None
    if image:
        img = Path(image)
        if not img.is_absolute():
            img = SKILL_DIR / img
        if not img.is_file():
            return {"error": f"参考图片不存在：{img}"}
        image_path = str(img)

    out = Path(output_dir) if output_dir else SKILL_DIR / "generated-images"

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "resolution": resolution,
    }
    if image_path:
        try:
            payload["image_urls"] = [encode_image_as_data_uri(image_path)]
        except SystemExit as e:
            return {"error": str(e)}

    try:
        task_id = submit_task(base_url, api_key, payload)
    except SystemExit as e:
        return {"error": str(e)}

    print(f"  生图任务已提交: {task_id}", file=sys.stderr)

    time.sleep(15)

    try:
        task_data = poll_task(base_url, api_key, task_id, poll_interval, timeout)
    except SystemExit as e:
        return {"error": str(e)}

    actual_time = task_data.get("actual_time", 0)
    cost = task_data.get("cost", 0)

    try:
        paths = save_results(task_data, out, fmt)
    except SystemExit as e:
        return {"error": str(e)}

    return {
        "success": True,
        "files": [str(p) for p in paths],
        "actual_time": actual_time,
        "cost": cost,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
