# Worko Candidate Search Prompt Parser

## Overview

This Lambda function parses natural language search queries into structured JSON format and applies intelligent threshold adjustments for experience and CTC ranges based on validation logic.

## Features

### 1. Natural Language Query Parsing
- Converts user search prompts into structured JSON
- Extracts job requirements, skills, experience, salary, location, etc.
- Uses Azure OpenAI GPT-4o model

### 2. Experience Threshold Adjustment
Automatically widens experience ranges based on role seniority:

| Experience Range | Gap Applied | Example |
|-----------------|-------------|---------|
| 0-3 years | ±1 year | 2-3y → 1-4y |
| 3-6 years | ±1.5 years | 4-6y → 2.5-7.5y |
| 6-10 years | ±2 years | 7-9y → 5-11y |
| 10+ years | check_experience logic | Variable |

### 3. CTC Threshold Adjustment
Adjusts salary ranges based on compensation bands:

- **High-paying roles** (max * 1.2 > 10 LPA): Allow ECTC up to 120% of max
- **Low-paying roles** (max * 1.2 ≤ 10 LPA): Allow ECTC up to 130% of max

Formula: `ECTC = Current CTC * 1.25`

## Input Format

```json
{
  "searchByPrompt": "Senior Software Engineer with 5-8 years experience and 15-20 LPA"
}
```

## Output Format

```json
{
  "jobTitle": "Senior Software Engineer",
  "experienceRange": {
    "min": 3.5,
    "max": 10.0
  },
  "salaryRange": {
    "min": 15,
    "max": 19
  },
  "coreSkills": ["Node.js", "Python"],
  "location": "Bangalore",
  ...
}
```

## Threshold Adjustment Logic

### Experience Adjustment
- **MIN**: Reduces minimum by gap value (allows underqualified candidates within tolerance)
- **MAX**: Increases maximum by gap value (allows overqualified candidates within tolerance)

### CTC Adjustment
- **MAX**: Adjusts based on expected CTC (ECTC) calculation
- Prevents rejection of candidates whose expected salary is within acceptable range

## Usage

### Local Testing
```bash
python lambda_function.py
```

### AWS Lambda Invocation
```bash
aws lambda invoke \
  --function-name worko-candidate-search-prompt-parser-dev \
  --region ap-south-1 \
  --payload file://test-event.json \
  response.json
```

## Dependencies

- `boto3`: AWS SDK for Python
- `requests`: HTTP library for Azure OpenAI API calls

## Environment Variables

- `ENVIRONMENT`: Deployment environment (dev/staging/prod)

## Logs

The function provides concise logs showing:
- Original ranges
- Applied adjustments with calculations
- Final adjusted ranges

Example:
```
=== THRESHOLD ADJUSTMENT ===
Experience: 5.0-8.0 years
  MIN: 5.0 - 1.5 = 3.5 (3-6y range)
  MAX: 8.0 + 2 = 10.0 (6-10y range)
  → Adjusted: 3.5-10.0 years
CTC: 15.0-20.0 LPA
  MAX: (20.0 * 1.2) / 1.25 = 19.2 (High-paying)
  → Adjusted: 15-19 LPA
=== ADJUSTMENT COMPLETE ===
```

## Integration

This function is designed to work with:
- Candidate search systems
- Job matching algorithms
- Recruitment platforms

The adjusted ranges ensure better candidate discovery while maintaining quality standards defined in `check_experience` and `check_ctc` validation functions.

## Error Handling

- Validates input format
- Handles missing fields gracefully
- Retries Azure OpenAI API calls with exponential backoff
- Returns original query on parsing failures

## Performance

- **Timeout**: 120 seconds
- **Memory**: 512 MB
- **Cold Start**: ~2-3 seconds
- **Warm Execution**: ~1-2 seconds
