from __future__ import annotations
import json
import time
import asyncio
from typing import Dict, Any, Tuple
from textwrap import dedent
from app.agents.llm import generate_plain
from app.utils.logger import LogSession


class ValidationError(Exception):
    pass


async def validate_output(
    questions_txt: str,
    generated_code: str,
    code_output: Dict[str, Any],
    attachments: Dict[str, bytes],
    timeout: int = 30,
    logger: LogSession | None = None
) -> Tuple[bool, str]:
    """
    Validates the output against the requirements in questions.txt.
    
    Returns:
        Tuple[bool, str]: (is_valid, feedback_for_regeneration)
    """
    
    # Check if code execution was successful
    if not code_output.get("ok", False):
        stderr = code_output.get("stderr", "")
        return False, f"Code execution failed with error: {stderr}"
    
    # Get the actual output
    actual_output = code_output.get("stdout_json")
    if actual_output is None:
        stdout = code_output.get("stdout", "")
        try:
            actual_output = json.loads(stdout)
        except:
            return False, f"Code did not produce valid JSON output. Stdout was: {stdout[:500]}"
    
    # Use LLM to validate the output against requirements
    validation_prompt = dedent(f"""
    You are a validator for a data analysis task. Given the user's questions and the generated output,
    determine if the output correctly answers ALL the questions.

    USER QUESTIONS:
    {questions_txt}

    GENERATED OUTPUT:
    {json.dumps(actual_output, indent=2) if actual_output else "None"}

    GENERATED CODE:
    {generated_code}

    VALIDATION CRITERIA:
    1. Check if the output format matches what was requested (e.g., JSON array of strings)
    2. Verify that all questions are answered
    3. Check if numeric answers seem reasonable
    4. For plots, verify base64 data URI format is correct
    5. Check if the logic in the code appears sound

    Respond with JSON:
    {{
        "valid": true/false,
        "feedback": "Detailed feedback for the code generator if invalid, or 'Valid' if valid"
    }}

    Focus on:
    - Are all questions answered?
    - Is the output format correct?
    - Do the answers make logical sense?
    - If there are errors, what specifically needs to be fixed?
    """)
    
    try:
        # Use asyncio.wait_for to enforce timeout on the entire validation process
        try:
            validation_response = await asyncio.wait_for(
                asyncio.to_thread(generate_plain, validation_prompt, "gemini-2.5-flash", timeout),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            if logger:
                logger.log(f"Validator timed out after {timeout} seconds")
            return True, f"Validator timed out after {timeout}s, assuming output is valid"
        except Exception as e:
            if logger:
                logger.log(f"Validator API call failed: {str(e)}")
            return True, f"Validator API failed, assuming output is valid: {str(e)}"
        
        # Log the validation response
        if logger:
            logger.log(f"Validator response: {validation_response[:500] if validation_response else 'Empty response'}")
        
        # Check for empty response
        if not validation_response or not validation_response.strip():
            if logger:
                logger.log("Validator returned empty response, assuming output is valid")
            return True, "Validator returned empty response, assuming output is valid"
        
        # Parse validation response
        try:
            # Extract JSON from response if wrapped in code fences
            import re
            json_match = re.search(r'```json\n(.*?)\n```', validation_response, re.DOTALL)
            if json_match:
                validation_json = json.loads(json_match.group(1))
            else:
                validation_json = json.loads(validation_response)
                
            is_valid = validation_json.get("valid", False)
            feedback = validation_json.get("feedback", "Unknown validation error")
            
            if logger:
                logger.log(f"Validation result: {'VALID' if is_valid else 'INVALID'}")
                if not is_valid:
                    logger.log(f"Validation feedback: {feedback}")
            
            return is_valid, feedback
            
        except Exception as e:
            # Fallback: assume invalid if we can't parse validation response
            if logger:
                logger.log(f"Validation parsing error: {str(e)}. Raw response: {validation_response[:200] if validation_response else 'None'}")
            return False, f"Validation parsing error: {str(e)}. Raw response: {validation_response[:200] if validation_response else 'None'}"
            
    except Exception as e:
        # If validator fails, assume output is valid to avoid blocking
        if logger:
            logger.log(f"Validator failed: {str(e)}")
        return True, "Validator failed, assuming output is valid"


async def generate_feedback_for_retry(
    questions_txt: str,
    previous_code: str,
    error_message: str,
    code_output: Dict[str, Any],
    attachments: Dict[str, bytes],
    timeout: int = 30,
    logger: LogSession | None = None
) -> str:
    """
    Generate specific feedback for the coding agent to fix issues.
    """
    
    stderr = code_output.get("stderr", "")
    stdout = code_output.get("stdout", "")
    
    feedback_prompt = dedent(f"""
    You are helping debug a Python code generation issue. The previous code failed or produced incorrect output.

    ORIGINAL QUESTIONS:
    {questions_txt}

    PREVIOUS CODE:
    {previous_code}

    ERROR/ISSUE:
    {error_message}

    STDERR:
    {stderr}

    STDOUT:
    {stdout}

    AVAILABLE ATTACHMENTS:
    {list(attachments.keys())}

    Provide specific, actionable feedback for fixing the code. Focus on:
    1. What went wrong?
    2. How to fix it?
    3. What the corrected code should do differently?

    Be concise but specific. Your response will be used to regenerate better code.
    """)
    
    try:
        # Use asyncio.wait_for to enforce timeout
        feedback = await asyncio.wait_for(
            asyncio.to_thread(generate_plain, feedback_prompt, "gemini-2.5-flash", timeout),
            timeout=timeout
        )
        return feedback
    except asyncio.TimeoutError:
        return f"Feedback generation timed out after {timeout}s. Original error: {error_message}"
    except Exception as e:
        return f"Could not generate feedback: {str(e)}. Original error: {error_message}"
