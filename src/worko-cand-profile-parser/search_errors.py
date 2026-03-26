import re

LOG_FILE = r"C:\Users\Administrator\Desktop\worko_working\worko-workspace\worko-ai-lambda\logs\lambda_logs.txt"

# Error patterns from lambda_function.py (excluding throttling)
ERROR_PATTERNS = [

    "Unexpected error:",
    "Error in checking dublicacy in firstore for this resume with email",
    "Exception:",
    "Traceback",

    "Failed",
    "error",
]

# Exclude throttling errors
EXCLUDE_PATTERNS = [
    "Errore of {execution_error} now sending sqs",
    "throttling",
    "Throttling",
]

def should_exclude(line):
    for pattern in EXCLUDE_PATTERNS:
        if pattern.lower() in line.lower():
            return True
    return False

def search_errors():
    errors_found = []
    current_invocation = []
    invocation_has_error = False
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # Check if new invocation starts
            if line.startswith('[') and 'START RequestId:' in line:
                # Save previous invocation if it had errors
                if invocation_has_error and current_invocation:
                    errors_found.append('\n'.join(current_invocation))
                
                # Reset for new invocation
                current_invocation = [line]
                invocation_has_error = False
            elif '*' * 50 in line:
                # End of invocation
                if invocation_has_error and current_invocation:
                    errors_found.append('\n'.join(current_invocation))
                current_invocation = []
                invocation_has_error = False
            else:
                current_invocation.append(line)
                
                # Check for error patterns
                if not should_exclude(line):
                    for pattern in ERROR_PATTERNS:
                        if pattern.lower() in line.lower():
                            invocation_has_error = True
                            break
    
    # Save last invocation if needed
    if invocation_has_error and current_invocation:
        errors_found.append('\n'.join(current_invocation))
    
    return errors_found

# Run search
print("Searching for errors in logs (excluding throttling errors)...\n")
errors = search_errors()

if errors:
    print(f"Found {len(errors)} invocations with errors:\n")
    print("=" * 100)
    for idx, error_log in enumerate(errors, 1):
        print(f"\n### ERROR INVOCATION {idx} ###\n")
        print(error_log)
        print("\n" + "=" * 100)
else:
    print("No errors found (excluding throttling errors)")
