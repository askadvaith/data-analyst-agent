import asyncio
import json
import time
from typing import Dict, Any
from app.utils.logger import LogSession

from app.agents.coding_agent import generate_code_for_task
from app.agents.validator import validate_output, generate_feedback_for_retry
from app.core.sandbox import run_python_in_sandbox


async def run_pipeline(questions_txt: str, attachments: Dict[str, bytes], deadline_secs: int = 170, logger: LogSession | None = None) -> Any:
    start = time.time()
    remaining = lambda: max(5, deadline_secs - int(time.time() - start))

    # LOGGING CODE: log pipeline start
    if logger:
        logger.log("Pipeline start; simplified workflow without task parsing")
        logger.log(f"Questions length: {len(questions_txt)} chars")
        logger.log(f"Attachments: {list(attachments.keys())}")

    # Create a single comprehensive task that includes everything
    task = type("Task", (), {
        "id": "comprehensive_analysis",
        "instructions": f"""
        Analyze the provided questions and data to produce the requested output.
        
        USER QUESTIONS:
        {questions_txt}
        
        REQUIREMENTS:
        - Read and process any provided attachments
        - Answer all questions in the requested format
        - If URLs are mentioned, scrape the required data
        - Generate any requested visualizations as base64 data URIs
        - Return the final answer as specified in the questions
        """,
        "context": {
            "questions_txt": questions_txt,
            "attachments": list(attachments.keys())
        }
    })()

    max_retries = 3
    current_code = None
    
    for attempt in range(max_retries):
        if remaining() <= 10:
            break
            
        # LOGGING CODE: log attempt
        if logger:
            logger.log(f"Code generation attempt {attempt + 1}/{max_retries}")
        
        # Generate code (with feedback if this is a retry)
        feedback = None
        if attempt > 0 and current_code:
            # Generate feedback for retry
            if logger:
                logger.log("Generating feedback for code regeneration")
            feedback = await generate_feedback_for_retry(
                questions_txt, 
                current_code, 
                "Previous attempt failed validation or execution",
                last_result if 'last_result' in locals() else {},
                attachments,
                timeout=min(30, remaining()),
                logger=logger
            )
            if logger:
                logger.log(f"Generated feedback: {feedback[:300]}...")

        try:
            current_code = await generate_code_for_task(
                task, 
                timeout=min(60, remaining()), 
                logger=logger, 
                mode="code",
                feedback=feedback
            )
            
            # LOGGING CODE: log generated code size
            if logger:
                logger.log(f"Generated code: {len(current_code)} chars")
                logger.log(f"Full generated code:\n{current_code}")
            
        except Exception as e:
            if logger:
                logger.log(f"Code generation failed: {str(e)}")
            if attempt == max_retries - 1:
                return {"error": f"Code generation failed: {str(e)}"}
            continue
        
        # Execute the code
        if logger:
            logger.log("Executing generated code in sandbox")
            
        try:
            last_result = await run_python_in_sandbox(
                current_code, 
                attachments, 
                questions_txt=questions_txt, 
                timeout=min(90, remaining())
            )
            
            # LOGGING CODE: log sandbox execution results
            if logger:
                ok = last_result.get("ok", False)
                stdout = last_result.get("stdout", "")
                stderr = last_result.get("stderr", "")
                
                if ok:
                    preview = stdout[:400] if len(stdout) <= 400 else stdout[:400] + "..."
                    logger.log(f"Sandbox execution OK; stdout preview: {preview}")
                else:
                    logger.log(f"Sandbox execution ERROR; stderr (full):\n{stderr}")
                    
        except Exception as e:
            if logger:
                logger.log(f"Sandbox execution failed: {str(e)}")
            last_result = {"ok": False, "stderr": str(e), "stdout": ""}
        
        # Validate the output
        if last_result.get("ok", False):
            if logger:
                logger.log("Validating output against requirements")
                
            try:
                is_valid, validation_feedback = await validate_output(
                    questions_txt,
                    current_code,
                    last_result,
                    attachments,
                    timeout=min(30, remaining()),
                    logger=logger
                )
                
                # LOGGING CODE: log validation results
                if logger:
                    logger.log(f"Validation result: {'VALID' if is_valid else 'INVALID'}")
                    if not is_valid:
                        logger.log(f"Validation feedback: {validation_feedback}")
                
                if is_valid:
                    # Success! Return the output
                    output = last_result.get("stdout_json")
                    if output is None:
                        try:
                            output = json.loads(last_result.get("stdout", ""))
                        except:
                            output = last_result.get("stdout", "")
                    
                    # LOGGING CODE: log successful completion
                    if logger:
                        logger.log(f"Pipeline completed successfully on attempt {attempt + 1}")
                        logger.log(f"Final output: {str(output)[:500]}...")
                    
                    return output
                    
            except Exception as e:
                if logger:
                    logger.log(f"Validation failed: {str(e)}")
                # If validation fails, treat as invalid and retry
                
        # If we reach here, either execution failed or validation failed
        if attempt == max_retries - 1:
            # Final attempt failed
            if logger:
                logger.log("All attempts exhausted, returning error result")
            
            if last_result.get("ok", False):
                # Execution succeeded but validation failed
                output = last_result.get("stdout_json")
                if output is None:
                    try:
                        output = json.loads(last_result.get("stdout", ""))
                    except:
                        output = {"error": "Could not parse output as JSON", "raw_stdout": last_result.get("stdout", "")}
                return output
            else:
                # Execution failed
                return {"error": "Code execution failed", "stderr": last_result.get("stderr", ""), "stdout": last_result.get("stdout", "")}

    # Should not reach here, but safety fallback
    return {"error": "Pipeline failed to complete within time constraints"}
