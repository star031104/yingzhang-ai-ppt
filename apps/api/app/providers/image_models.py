"""Conservative discovery: a vision/chat model is not a text-to-image model."""
import re


def image_model_problem(model):
    name = model.lower()
    if re.search(r"(?:image.*edit|flux.*kontext|inpaint)", name):
        return "该模型需要输入原图，不能用于当前的纯文字生图。请选择文生图模型。"
    if re.search(r"deepseek|intern(?:vl|-s)|qwen(?:2|3)|ernie|glm-|minimax-m|mistral|embedding|rerank|compassjudger|longcat|step-\d|xiyansql", name):
        return "该模型用于文字推理、图片理解或向量处理，不支持当前的文生图接口。"
    return None


def image_candidates(items):
    result = []
    for item in items:
        name = str(item.get("id", ""))
        metadata = str({key: item.get(key) for key in ("type", "task", "capabilities", "output_modalities")}).lower()
        known = re.search(r"qwen[-/]image|z-image|flux|dall-e|gpt-image|imagen|stable-diffusion|sdxl|kolors|seedream|hunyuan.?image", name.lower())
        declared = any(value in metadata for value in ("text-to-image", "image_generation", "text2image", "'image'"))
        if name and not image_model_problem(name) and (known or declared):
            result.append(name)
    return list(dict.fromkeys(result))
