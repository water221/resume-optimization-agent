import json
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException

# Simple server-side memory. In production, replace it with Redis/Postgres.
SESSIONS: Dict[str, Dict[str, Any]] = {}

ANALYZE_SYSTEM = """你是一个严谨的简历优化 Agent，目标是帮助求职者基于真实经历提升岗位匹配度。\n\n硬性规则：\n1. 只能基于原始简历中已经出现的事实进行分析，不允许编造学历、公司、项目、指标、技术栈。\n2. 如果 JD 需要但简历没有证据，必须放入主要缺口，而不是替用户虚构。\n3. 输出必须是合法 JSON，不要输出 Markdown 代码块。\n4. 建议要具体到简历修改动作，例如“把 X 项目改写为面向 Y 场景的 Agent 项目描述”。\n"""

OPTIMIZE_SYSTEM = """你是一个严谨的中文简历改写 Agent。\n\n硬性规则：\n1. 必须忠于原始简历事实，不得新增不存在的经历、公司、奖项、论文、指标。\n2. 可以重组表达、强化与 JD 相关的关键词、突出已有项目中的职责/技术/结果。\n3. 对不确定信息不要写成确定事实。\n4. 输出一份可直接复制到 Markdown/Word 的中文简历正文。\n5. 使用清晰标题、项目经历 bullet、专业技能分组，适合 AI Agent/AI 应用开发岗位。\n"""


def trim_text(text: str, max_chars: int = 30000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[内容过长，已截断。请上传更精简版本以获得更完整分析。]"


def extract_keywords(text: str) -> set[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9+.#-]{1,}", text.lower())
    stopwords = {
        "以及", "相关", "负责", "熟悉", "能够", "岗位", "要求", "优先", "经验", "工作",
        "and", "the", "for", "with", "from", "that", "this", "have", "will", "you",
    }
    return {t for t in tokens if t not in stopwords}


def normalize_score(score: Any) -> Optional[int]:
    try:
        value = int(score)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, value))


def compute_rule_based_match_score(resume_text: str, jd_text: str) -> int:
    jd_keywords = extract_keywords(jd_text)
    if not jd_keywords:
        return 50
    resume_keywords = extract_keywords(resume_text)
    matched = len(jd_keywords & resume_keywords)
    coverage = matched / max(1, len(jd_keywords))
    return int(round(30 + coverage * 70))


def merge_match_score(llm_score: Any, resume_text: str, jd_text: str) -> int:
    rule_score = compute_rule_based_match_score(resume_text, jd_text)
    parsed_llm_score = normalize_score(llm_score)
    if parsed_llm_score is None:
        return rule_score
    return int(round(parsed_llm_score * 0.6 + rule_score * 0.4))


def build_score_details(llm_score: Any, resume_text: str, jd_text: str) -> Dict[str, Any]:
    jd_keywords = extract_keywords(jd_text)
    resume_keywords = extract_keywords(resume_text)
    matched_keywords = sorted(jd_keywords & resume_keywords)

    coverage = len(matched_keywords) / len(jd_keywords) if jd_keywords else 0.0
    rule_score = compute_rule_based_match_score(resume_text, jd_text)
    parsed_llm_score = normalize_score(llm_score)
    final_score = merge_match_score(llm_score, resume_text, jd_text)

    return {
        "llm_score": parsed_llm_score,
        "rule_based_score": rule_score,
        "final_score": final_score,
        "jd_keywords_count": len(jd_keywords),
        "matched_keywords_count": len(matched_keywords),
        "coverage_percent": round(coverage * 100, 1),
        "matched_keywords_preview": matched_keywords[:20],
    }


def remove_square_noise(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[■□▪▫▮▯█▓▒▉▊▋▌▍▎▏]{3,}", "", text)
    cleaned = re.sub(r"[\u25A0-\u25FF]{4,}", "", cleaned)
    return cleaned


def sanitize_optimized_resume(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    markers = [
        "以下是优化后的完整简历正文：",
        "以下是优化后的简历正文：",
        "优化后的完整简历正文：",
        "优化后的简历如下：",
    ]
    for marker in markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[1].strip()
            break
    cleaned = re.sub(r"^好的[，,。!！\s].*?(?=\n\n|$)", "", cleaned, flags=re.S)
    cleaned = remove_square_noise(cleaned)
    return cleaned.strip().strip('"“”')


def extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not match:
        raise ValueError("LLM did not return JSON.")
    return json.loads(match.group(0))


def build_analysis_prompt(resume_text: str, jd_text: str) -> str:
    return f"""
请分析下面的【原始简历】与【目标 JD】的匹配情况。\n\n请输出 JSON，字段如下：\n{{\n  "match_score": 0-100的整数,\n  "target_role_summary": "用一句话概括JD核心要求",\n  "matching_highlights": ["匹配亮点1", "匹配亮点2"],\n  "main_gaps": ["主要缺口1", "主要缺口2"],\n  "optimization_suggestions": [\n    {{"area": "模块名称", "problem": "当前问题", "action": "具体修改动作", "evidence_from_resume": "来自原简历的事实依据"}}\n  ],\n  "risk_warnings": ["哪些内容不能乱写或需要用户补充确认"]\n}}\n\n【目标 JD】\n{jd_text}\n\n【原始简历】\n{resume_text}\n"""


def build_optimize_prompt(session: Dict[str, Any], extra_instruction: str = "") -> str:
    return f"""
用户已经确认根据分析结果优化简历。请基于以下内容生成优化后的简历。\n\n【目标 JD】\n{session['jd_text']}\n\n【原始简历】\n{session['resume_text']}\n\n【上一轮分析结果】\n{json.dumps(session['analysis'], ensure_ascii=False, indent=2)}\n\n【用户补充要求】\n{extra_instruction or '无'}\n\n请输出优化后的完整简历正文。\n"""


def analyze_resume(
    *,
    resume_text: str,
    jd_text: str,
    source_filename: str,
    llm_chat_func: Callable[[list[dict[str, str]], float], str],
) -> Dict[str, Any]:
    raw = llm_chat_func([
        {"role": "system", "content": ANALYZE_SYSTEM},
        {"role": "user", "content": build_analysis_prompt(resume_text, jd_text)},
    ])
    try:
        analysis = extract_json(raw)
    except Exception:
        analysis = {
            "match_score": None,
            "target_role_summary": "模型未返回标准 JSON，以下为原始分析结果。",
            "matching_highlights": [],
            "main_gaps": [],
            "optimization_suggestions": [],
            "risk_warnings": ["请检查模型输出格式。"],
            "raw_output": raw,
        }

    score_details = build_score_details(analysis.get("match_score"), resume_text, jd_text)
    analysis["match_score"] = score_details["final_score"]
    analysis["score_details"] = score_details

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "source_filename": source_filename or "",
        "analysis": analysis,
        "optimized_resume": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"session_id": session_id, "analysis": analysis}


def optimize_resume(
    *,
    session_id: str,
    user_confirmed: bool,
    extra_instruction: str,
    llm_chat_func: Callable[[list[dict[str, str]], float], str],
) -> Dict[str, Any]:
    if not user_confirmed:
        raise HTTPException(status_code=400, detail="用户尚未确认生成优化简历。")

    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please analyze again.")

    optimized = llm_chat_func([
        {"role": "system", "content": OPTIMIZE_SYSTEM},
        {"role": "user", "content": build_optimize_prompt(session, extra_instruction or "")},
    ])
    session["optimized_resume"] = sanitize_optimized_resume(optimized)
    return {"session_id": session_id, "optimized_resume": session["optimized_resume"]}


def get_session(session_id: str) -> Dict[str, Any]:
    return SESSIONS.get(session_id) or {}


def get_resume_or_404(session_id: str) -> str:
    session = SESSIONS.get(session_id)
    if not session or not session.get("optimized_resume"):
        raise HTTPException(status_code=404, detail="Optimized resume not found. Please generate it first.")
    return session["optimized_resume"]
