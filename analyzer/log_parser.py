import os

def extract_relevant_logs(log_file_path):
    """
    Reads a Jenkins console log file and extracts sections containing errors.
    Returns a cleaned string with context around each error.

    Args:
        log_file_path (str): Absolute path to the Jenkins log file.

    Returns:
        str: A string containing the extracted log snippets or an error message.
    """
    # Keywords that usually indicate a failure in a CI/CD pipeline
    ERROR_KEYWORDS = ["ERROR", "FAILED", "Exception", "exit code", "fatal", "Error:", "BUILD FAILURE"]
    CONTEXT_WINDOW = 15  # Lines to capture before and after the error
    MAX_CHARS = 8000      # Heuristic for ~2000 tokens to avoid hitting LLM limits

    # 1. Handle edge case: File doesn't exist
    if not os.path.exists(log_file_path):
        return "Error: Log file not found."

    # 2. Handle edge case: Very large log files (>5MB)
    # We check the size first to avoid loading gigabytes of data into memory
    file_size = os.path.getsize(log_file_path)
    if file_size > 5 * 1024 * 1024:
        # If the file is too large, we will only read the first 5MB to prevent crashes
        # In a real production environment, we might read from the end of the file (tail)
        pass

    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading log file: {str(e)}"

    # 3. Handle edge case: Empty file
    if not lines:
        return "No significant errors found in log."

    # We will store the indices of all lines that are part of an error context
    # Using a set ensures that we don't duplicate lines if two errors are close to each other
    lines_to_include = set()

    for i, line in enumerate(lines):
        # Check if any of our error keywords are in the current line
        if any(keyword in line for keyword in ERROR_KEYWORDS):
            # Mark the line itself and the window around it
            start = max(0, i - CONTEXT_WINDOW)
            end = min(len(lines), i + CONTEXT_WINDOW + 1)
            for line_num in range(start, end):
                lines_to_include.add(line_num)

    # 4. Handle case where no error keywords were found
    if not lines_to_include:
        return "No significant errors found in log."

    # 5. Merge and Deduplicate
    # Sort the indices and group them into contiguous blocks
    sorted_indices = sorted(list(lines_to_include))

    final_snippets = []
    if sorted_indices:
        start_idx = sorted_indices[0]
        end_idx = sorted_indices[0]

        for i in range(1, len(sorted_indices)):
            # If the current index is consecutive to the previous one, expand the block
            if sorted_indices[i] == end_idx + 1:
                end_idx = sorted_indices[i]
            else:
                # We've hit a gap; save the current block and start a new one
                final_snippets.append("".join(lines[start_idx : end_idx + 1]))
                start_idx = sorted_indices[i]
                end_idx = sorted_indices[i]

        # Add the last block
        final_snippets.append("".join(lines[start_idx : end_idx + 1]))

    # Join the merged blocks with a separator for clarity
    full_text = "\n\n--- Error Context Block ---\n\n".join(final_snippets)

    # 6. Token Budgeting: Trim if the log is huge
    # We keep the end of the log because the root cause is usually at the bottom
    if len(full_text) > MAX_CHARS:
        full_text = "... [Log Truncated] ...\n" + full_text[-MAX_CHARS:]

    return full_text.strip()
