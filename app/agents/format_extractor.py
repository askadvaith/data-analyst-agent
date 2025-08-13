from __future__ import annotations
import json
import re
import asyncio
from typing import Dict, Any, Optional, Union
from textwrap import dedent
from app.agents.llm import generate_plain
from app.utils.logger import LogSession


async def extract_expected_format(
    questions_txt: str, 
    timeout: int = 30, 
    logger: LogSession | None = None
) -> Optional[Union[Dict[str, Any], list, str]]:
    """
    Extract the expected output format from the questions text and return a template with null/empty values.
    
    Returns:
        The expected format template with null/empty values, or None if format cannot be determined
    """
    
    if logger:
        logger.log("Extracting expected output format from questions")
    
    # Use LLM to analyze the questions and determine the expected format
    format_prompt = dedent(f"""
    Analyze the following questions and determine the EXACT JSON output format that is expected.
    Identify:
    - Whether output is an object or array
    - Field names and their primitive / nested data types
    - Repeated record structure (arrays of objects)
    - Approximate number of elements if explicitly stated (retain representative single element only)

    Return a JSON TEMPLATE using DEFAULT TYPED PLACEHOLDERS:
    - string -> "default"
    - integer/float -> 0 (use 0 for all numerics)
    - boolean -> false
    - null / unknown -> "default"
    - array -> one representative element only (do not repeat 3 times unless explicitly distinct)
    - object -> include all keys with placeholder values recursively

    Examples:
    - "JSON array of 3 strings" => ["default", "default", "default"] (if count explicitly specified)
    - "JSON object with name and age" => {"name": "default", "age": 0}
    - "Array of objects with id and value" => [{"id": 0, "value": "default"}]

    QUESTIONS:
    {questions_txt}

    Respond with ONLY the JSON template (no explanation). If format cannot be determined, respond with {"result": "default"}.
    """)
    
    try:
        # Use asyncio.wait_for to enforce timeout
        format_response = await asyncio.wait_for(
            asyncio.to_thread(generate_plain, format_prompt, "gemini-2.5-flash", timeout),
            timeout=timeout
        )
        
        if logger:
            logger.log(f"Format extractor response: {format_response}")
        
        # Clean the response and try to parse as JSON
        cleaned_response = format_response.strip()
        
        # Remove code fences if present
        if cleaned_response.startswith("```"):
            lines = cleaned_response.split('\n')
            # Find first line without ```
            start_idx = 0
            for i, line in enumerate(lines):
                if not line.strip().startswith("```"):
                    start_idx = i
                    break
            # Find last line without ```
            end_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if not lines[i].strip().startswith("```"):
                    end_idx = i + 1
                    break
            cleaned_response = '\n'.join(lines[start_idx:end_idx])
        
        # Try to parse as JSON
        try:
            format_template = json.loads(cleaned_response)
            if logger:
                logger.log(f"Successfully extracted format template: {json.dumps(format_template)}")
            return format_template
        except json.JSONDecodeError:
            # If direct parsing fails, try to extract JSON from the response
            json_matches = re.findall(r'\{.*?\}|\[.*?\]', cleaned_response, re.DOTALL)
            for match in json_matches:
                try:
                    format_template = json.loads(match)
                    if logger:
                        logger.log(f"Extracted format template from match: {json.dumps(format_template)}")
                    return format_template
                except json.JSONDecodeError:
                    continue
            
            if logger:
                logger.log("Could not parse format response as JSON")
            return None
            
    except asyncio.TimeoutError:
        if logger:
            logger.log(f"Format extraction timed out after {timeout} seconds")
        return None
    except Exception as e:
        if logger:
            logger.log(f"Format extraction failed: {str(e)}")
        return None


def create_fallback_format() -> Dict[str, Any]:
    return {"error": "timeout", "result": "default"}


def _default_for(value):
    if isinstance(value, str):
        return "default"
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if value is None:
        return "default"
    return "default"


def populate_format_with_timeout_message(format_template: Any) -> Any:
    """
    Populate the extracted format template with timeout-appropriate values.
    
    Args:
        format_template: The template extracted from questions
        
    Returns:
        The template filled with appropriate timeout values
    """
    if format_template is None:
        return create_fallback_format()
    
    def fill_template(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    out[k] = fill_template(v)
                else:
                    out[k] = _default_for(v)
            return out
        if isinstance(obj, list):
            if not obj:
                return []
            # single representative element (recursively defaulted)
            return [fill_template(obj[0])]
        return _default_for(obj)
    
    return fill_template(format_template)
