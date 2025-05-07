"""
Model configuration presets for different LLM backends.
This file provides recommended configurations for various models to avoid timeout issues.
"""

import logging

logger = logging.getLogger(__name__)

# Model configuration presets
MODEL_CONFIGS = {
    # Ollama models
    "gemma:3b": {
        "timeout": 180.0,  # 3 minutes
        "max_transcript_chars": 20000,
        "description": "Lightweight 3B model, good for basic summaries"
    },
    "gemma:7b": {
        "timeout": 240.0,  # 4 minutes
        "max_transcript_chars": 15000,
        "description": "Medium 7B model, balanced performance"
    },
    "gemma3:1b": {
        "timeout": 180.0,  # 3 minutes
        "max_transcript_chars": 20000,
        "description": "Lightweight Gemma 3 1B model, good for basic summaries"
    },
    "gemma3:12b": {
        "timeout": 600.0,  # 10 minutes (increased from 6 minutes)
        "max_transcript_chars": 8000,  # Reduced from 12000
        "description": "Large 12B model, better quality but slower"
    },
    "qwen3:30b-a3b": {
        "timeout": 480.0,  # 8 minutes
        "max_transcript_chars": 15000,
        "description": "Large 30B model, high quality with good performance"
    },
    "llama3:8b": {
        "timeout": 240.0,  # 4 minutes
        "max_transcript_chars": 15000,
        "description": "Medium 8B model, good all-around performance"
    },
    "llama3:70b": {
        "timeout": 600.0,  # 10 minutes
        "max_transcript_chars": 10000,
        "description": "Very large 70B model, high quality but very slow"
    },
    
    # OpenAI models
    "gpt-3.5-turbo": {
        "timeout": 60.0,  # 1 minute (API is fast)
        "max_transcript_chars": 25000,
        "description": "Fast OpenAI model with good performance"
    },
    "gpt-4": {
        "timeout": 120.0,  # 2 minutes
        "max_transcript_chars": 20000,
        "description": "High-quality OpenAI model"
    },
    
    # Gemini models
    "gemini-pro": {
        "timeout": 120.0,  # 2 minutes
        "max_transcript_chars": 20000,
        "description": "Google's Gemini Pro model"
    },
    "gemini-2.5-flash-preview": {
        "timeout": 120.0,  # 2 minutes
        "max_transcript_chars": 25000,
        "description": "Google's Gemini 2.5 Flash Preview model"
    }
}

# Default configuration for unknown models
DEFAULT_MODEL_CONFIG = {
    "timeout": 180.0,  # 3 minutes
    "max_transcript_chars": 15000,
    "description": "Default configuration for unknown models"
}

def get_model_config(model_name):
    """
    Get the configuration for a specific model.
    
    Args:
        model_name: Name of the model
        
    Returns:
        Dictionary with model configuration
    """
    logger.info(f"Getting configuration for model: {model_name}")
    
    # Check if model name contains a colon (namespace:model format)
    if ":" in model_name:
        base_name, version = model_name.split(":", 1)
        logger.info(f"Model has namespace format: base={base_name}, version={version}")
    
    if model_name in MODEL_CONFIGS:
        logger.info(f"Found exact match for model: {model_name}")
        config = MODEL_CONFIGS[model_name]
        logger.info(f"Using configuration: timeout={config['timeout']}s, max_chars={config['max_transcript_chars']}")
        return config
    
    # Try to find a partial match (e.g., if user specified "llama3" without exact version)
    for known_model in MODEL_CONFIGS:
        if model_name.lower() in known_model.lower():
            logger.info(f"Found partial match: {known_model} for requested model: {model_name}")
            config = MODEL_CONFIGS[known_model]
            logger.info(f"Using configuration: timeout={config['timeout']}s, max_chars={config['max_transcript_chars']}")
            return config
    
    logger.warning(f"Unknown model: {model_name}. Using default configuration.")
    logger.info(f"Default config: timeout={DEFAULT_MODEL_CONFIG['timeout']}s, max_chars={DEFAULT_MODEL_CONFIG['max_transcript_chars']}")
    return DEFAULT_MODEL_CONFIG

def list_available_models():
    """
    List all available model configurations with their descriptions.
    
    Returns:
        String with formatted list of models
    """
    result = "Available model configurations:\n\n"
    
    for model, config in MODEL_CONFIGS.items():
        result += f"- {model}: {config['description']}\n"
        result += f"  Timeout: {config['timeout']}s, Max transcript: {config['max_transcript_chars']} chars\n\n"
    
    return result