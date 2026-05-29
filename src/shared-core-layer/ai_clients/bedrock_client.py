"""AWS Bedrock client for various models (Claude, Nova, DeepSeek, Titan)."""

import json
import boto3
from typing import Dict, Any, List, Optional


class BedrockClient:
    """Client for AWS Bedrock runtime API."""
    
    def __init__(self, region_name: str = 'ap-south-1'):
        """Initialize Bedrock client.
        
        Args:
            region_name: AWS region name
        """
        self.region = region_name
        self.bedrock = boto3.client(service_name='bedrock', region_name=region_name)
        self.bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=region_name)
    
    def invoke_claude(
        self,
        prompt: str,
        model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0",
        max_tokens: int = 4096,
        temperature: float = 0.5,
        top_p: float = 0.9
    ) -> str:
        """Invoke Claude model.
        
        Args:
            prompt: User prompt
            model_id: Claude model ID
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            
        Returns:
            Model response text
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        })
        
        response = self.bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
    
    def invoke_nova(
        self,
        prompt: str,
        model_id: str = "amazon.nova-pro-v1:0",
        max_tokens: int = 4096,
        temperature: float = 0.5,
        top_p: float = 0.9
    ) -> Dict[str, Any]:
        """Invoke Amazon Nova model.
        
        Args:
            prompt: User prompt
            model_id: Nova model ID
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            
        Returns:
            Parsed JSON response from model
        """
        body = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p
            }
        })
        
        response = self.bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        return response_body
    
    def invoke_deepseek(
        self,
        prompt: str,
        model_id: str = "us.deepseek.r1-v1:0",
        max_tokens: int = 4096,
        temperature: float = 0.5,
        top_p: float = 0.9
    ) -> str:
        """Invoke DeepSeek model.
        
        Args:
            prompt: User prompt
            model_id: DeepSeek model ID
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            
        Returns:
            Model response text
        """
        body = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p
        })
        
        response = self.bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        return response_body
    
    def invoke_titan_embeddings(self, input_text: str) -> List[float]:
        """Invoke Titan embeddings model.
        
        Args:
            input_text: Text to embed
            
        Returns:
            Embedding vector
        """
        body = json.dumps({
            "inputText": input_text
        })
        
        response = self.bedrock_runtime.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=body,
            contentType='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body.get('embedding', [])
