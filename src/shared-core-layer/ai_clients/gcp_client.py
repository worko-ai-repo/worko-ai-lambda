import json
import time
import random
import requests
from typing import Dict, Any, Union
from google import genai
from google.genai import types
from google.oauth2 import service_account
import re


class GeminiClient:
    """Client for Google Gemini API with retry logic."""
    
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_MAX_OUTPUT_TOKENS = 10000
    
    def __init__(self, gcp_credentials: Dict[str, str], env: str, model="gemini-2.5-pro"):
        """Initialize Gemini client.
        
        Args:
            gcp_credentials: Dict containing GCP service account credentials
            env: Environment (dev/staging/prod)
            model: Model name (default: gemini-2.5-pro)
        """
        self.model = model
        self.env = env
        self.project_id = f"worko-{env}"
        self.location = "global"
        
        if not isinstance(gcp_credentials, dict):
            raise TypeError("gcp_credentials must be a dictionary")
        
        # Load credentials
        self.credentials = service_account.Credentials.from_service_account_info(
            gcp_credentials,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        # Initialize Google Gen AI client with Vertex AI
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
            credentials=self.credentials
        )
    
    def clean_and_load(self, raw: str) -> dict:
        """Cleans raw JSON string and loads it into a dictionary."""
        cleaned = re.sub(r"```json|```", "", raw).strip()
        try:
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError as e:
            print("JSON loading error:", e)
            print("Cleaned JSON (first 500 chars):", cleaned[:500])
            raise ValueError(f"Invalid JSON response from Gemini: {str(e)}") from e
    
    def invoke_model_with_backoff(
        self,
        prompt: str,
        Task="Not specified",
        system_content: str = "You are a helpful assistant.",
        max_retries: int = 10,
        base_delay: int = 2,
        want_json: bool = True
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke model without retry logic - throttling handled at Lambda level.
        
        Args:
            prompt: User prompt
            system_content: System message for the model
            max_retries: Not used (kept for compatibility)
            base_delay: Not used (kept for compatibility)
            want_json: Whether to parse response as JSON
            
        Returns:
            Model response as string or parsed JSON dict
        """
        print("using model :-", self.model)
        print("Task to Ai is :- ", Task)
        return self.invoke_model(system_content, prompt, want_json)
    
    def invoke_model(
        self,
        system_content: str,
        prompt: str,
        want_json: bool = True,
        max_json_retries: int = 3,
        temperature: float = DEFAULT_TEMPERATURE
    ) -> Union[str, Dict[Any, Any]]:
        """Invoke Gemini model.
        
        Args:
            system_content: System message
            prompt: User prompt
            want_json: Whether to parse response as JSON
            max_json_retries: Max retries for JSON parsing
            temperature: Model temperature
            
        Returns:
            Model response as string or parsed JSON dict
        """
        # Build config
        generate_config = types.GenerateContentConfig(
            max_output_tokens=self.DEFAULT_MAX_OUTPUT_TOKENS,
            temperature=temperature,
            system_instruction=system_content if system_content else None,
        )
        
        # Build contents
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )
        ]
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=generate_config,
        )
        
        response_text = response.text
        input_t = response.usage_metadata.prompt_token_count
        output_t = response.usage_metadata.candidates_token_count
        cached_t = response.usage_metadata.cached_content_token_count or 0
        
        print(f"Token usage details input_tokens :- {input_t}, output_tokens: {output_t}, cached_tokens: {cached_t}")
        
        # Check if response was truncated
        if output_t >= self.DEFAULT_MAX_OUTPUT_TOKENS - 100:
            print(f"WARNING: Response may be truncated (output_tokens: {output_t}, limit: {self.DEFAULT_MAX_OUTPUT_TOKENS})")
        
        if not want_json:
            return response_text
        
        # JSON mode with retries
        for attempt in range(max_json_retries):
            try:
                cleaned = self.clean_and_load(response_text)
                return cleaned
            
            except (json.JSONDecodeError, ValueError) as e:
                remaining = max_json_retries - attempt - 1
                print(f"JSON parse failed. Retries left: {remaining}")
                print(f"Error: {e}")
                
                if remaining == 0:
                    print(f"Raw content (first 500 chars): {response_text[:500]}")
                    print(f"Raw content (last 200 chars): {response_text[-200:]}")
                    raise ValueError(f"Failed to parse JSON after {max_json_retries} attempts: {str(e)}") from e
                
                # Re-invoke model for retry with slightly higher temperature for variation
                retry_config = types.GenerateContentConfig(
                    max_output_tokens=self.DEFAULT_MAX_OUTPUT_TOKENS,
                    temperature=min(temperature + 0.1, 1.0),
                    system_instruction=system_content if system_content else None,
                )
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=retry_config,
                )
                response_text = response.text
                print(f"Retry attempt {attempt + 1}: Got new response (output_tokens: {response.usage_metadata.candidates_token_count})")
