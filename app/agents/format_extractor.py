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
    Analyze the following questions and determine the EXACT output format that is expected.
    Look for specific mentions of:
    - JSON arrays
    - JSON objects  
    - Specific field names
    - Number of items expected
    - Data types (strings, numbers, booleans)
    - Nested structures
    
    Return a JSON template that matches the expected format, but with null/empty values as placeholders.
    
    For example:
    - If questions ask for "JSON array of 3 strings" → return ["", "", ""]
    - If questions ask for "JSON object with name and age" → return {{"name": "", "age": null}}
    - If questions ask for "array of objects with id and value" → return [{{"id": null, "value": ""}}]
    
    QUESTIONS:
    {questions_txt}
    
    Respond with ONLY the JSON template (no explanation). If you cannot determine a specific format, respond with null.
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
    """
    Create a generic fallback format when format extraction fails.
    """
    return {"error": "Request timed out", "result": None}


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
            result = {}
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    result[key] = fill_template(value)
                elif value is None:
                    result[key] = None
                elif isinstance(value, str) and value == "":
                    result[key] = ""
                elif isinstance(value, (int, float)) and value == 0:
                    result[key] = 0
                else:
                    result[key] = fill_template(value)
            return result
        elif isinstance(obj, list):
            if len(obj) == 0:
                return []
            # Fill each item in the list
            return [fill_template(item) for item in obj]
        else:
            # For primitive values, return as-is (they're already null/empty placeholders)
            return obj
    
    return fill_template(format_template)
