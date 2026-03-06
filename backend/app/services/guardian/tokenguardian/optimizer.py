#!/usr/bin/env python3
"""
Token Guardian Core - Optimizer Module
Prompt optimization: refinement, caching, and token management
"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import yaml


@dataclass
class OptimizationResult:
    """Result of optimizing a prompt"""
    original: str
    refined: str
    tokens_saved: int
    savings_percent: float
    action_taken: str  # 'refined', 'cached', 'unchanged', 'batched'
    cache_hit: bool
    cached_response: Optional[str] = None


class Optimizer:
    """Prompt optimization engine"""
    
    def __init__(self, config_path: str = None):
        """Initialize optimizer with configuration"""
        self.config = {
            'enabled': True,
            'dry_run': False,
            'refinement': {
                'enabled': True,
                'fluff_words': [
                    'please', 'thank you', 'could you', 'i would like to',
                    'can you', 'kindly', 'just', 'really', 'very',
                    'absolutely', 'essentially', 'basically', 'quite'
                ]
            },
            'caching': {
                'enabled': True,
                'ttl': 86400,
                'dir': '~/.tokenguardian/cache'
            },
            'compaction': {
                'enabled': False,
                'batch_window': 5
            }
        }
        
        self.cache_dir = Path('~/.tokenguardian/cache').expanduser()
        self.cache_hits = 0
        self.cache_misses = 0
        
        if config_path:
            self.load_config(config_path)
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self, config_path: str):
        """Load optimizer configuration from YAML"""
        path = Path(config_path)
        if not path.exists():
            return
        
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            
            if 'optimizer' in config:
                self.config.update(config['optimizer'])
            
            # Set cache dir
            cache_cfg = self.config.get('caching', {})
            self.cache_dir = Path(cache_cfg.get('dir', '~/.tokenguardian/cache')).expanduser()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
        except Exception as e:
            print(f"[WARN] Failed to load optimizer config {config_path}: {e}")
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _check_cache(self, text: str) -> Optional[str]:
        """Check if response is cached"""
        if not self.config.get('caching', {}).get('enabled', True):
            return None
        
        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / cache_key
        
        if cache_file.exists():
            # Check TTL
            ttl = self.config.get('caching', {}).get('ttl', 86400)
            mtime = cache_file.stat().st_mtime
            
            if time.time() - mtime < ttl:
                self.cache_hits += 1
                with open(cache_file, 'r') as f:
                    return f.read()
            else:
                # Expired
                cache_file.unlink()
        
        self.cache_misses += 1
        return None
    
    def _save_cache(self, text: str, response: str):
        """Save response to cache"""
        if not self.config.get('caching', {}).get('enabled', True):
            return
        
        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / cache_key
        
        with open(cache_file, 'w') as f:
            f.write(response)
    
    def _refine_prompt(self, prompt: str) -> str:
        """Remove fluff words from prompt"""
        if not self.config.get('refinement', {}).get('enabled', True):
            return prompt
        
        fluff_words = self.config.get('refinement', {}).get('fluff_words', [])
        
        refined = prompt.lower()
        
        for word in fluff_words:
            # Word boundary match
            pattern = r'\b' + re.escape(word) + r'\b'
            refined = re.sub(pattern, ' ', refined)
        
        # Clean up extra spaces
        refined = ' '.join(refined.split())
        
        return refined.strip()
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from character count"""
        return len(text) // 4 + 1
    
    def optimize(self, prompt: str, response: str = None) -> OptimizationResult:
        """
        Optimize a prompt through refinement and caching
        
        Args:
            prompt: User prompt
            response: Optional response to cache
            
        Returns:
            OptimizationResult with details
        """
        original_tokens = self._estimate_tokens(prompt)
        
        # Step 1: Check cache
        if response is None:
            cached = self._check_cache(prompt)
            if cached:
                refined = self._refine_prompt(prompt)
                refined_tokens = self._estimate_tokens(refined)
                
                return OptimizationResult(
                    original=prompt,
                    refined=refined,
                    tokens_saved=original_tokens - refined_tokens,
                    savings_percent=((original_tokens - refined_tokens) / original_tokens * 100) if original_tokens > 0 else 0,
                    action_taken='cached',
                    cache_hit=True,
                    cached_response=cached
                )
        
        # Step 2: Refine prompt
        refined = self._refine_prompt(prompt)
        refined_tokens = self._estimate_tokens(refined)
        tokens_saved = original_tokens - refined_tokens
        savings_percent = ((tokens_saved / original_tokens) * 100) if original_tokens > 0 else 0
        
        # Step 3: Cache response if provided
        if response:
            self._save_cache(prompt, response)
        
        action = 'cached' if response and self._check_cache(prompt) else 'refined'
        
        return OptimizationResult(
            original=prompt,
            refined=refined,
            tokens_saved=max(0, tokens_saved),
            savings_percent=max(0, savings_percent),
            action_taken=action,
            cache_hit=False
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics"""
        cache_dir_size = sum(
            f.stat().st_size for f in self.cache_dir.glob('*') if f.is_file()
        ) if self.cache_dir.exists() else 0
        
        cache_files = len(list(self.cache_dir.glob('*'))) if self.cache_dir.exists() else 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_files': cache_files,
            'cache_size_bytes': cache_dir_size,
            'enabled': self.config.get('enabled', True),
            'refinement_enabled': self.config.get('refinement', {}).get('enabled', True),
            'caching_enabled': self.config.get('caching', {}).get('enabled', True)
        }


def optimize_prompt(prompt: str, 
                   response: str = None,
                   dry_run: bool = False,
                   config_path: str = None) -> OptimizationResult:
    """
    Convenience function to optimize a prompt
    
    Args:
        prompt: User prompt
        response: Optional response to cache
        dry_run: If True, don't actually optimize
        config_path: Path to guardian.yaml config
        
    Returns:
        OptimizationResult
    """
    optimizer = Optimizer(config_path)
    
    if dry_run:
        # Simulate but don't modify
        refined = optimizer._refine_prompt(prompt)
        orig_tokens = optimizer._estimate_tokens(prompt)
        ref_tokens = optimizer._estimate_tokens(refined)
        
        return OptimizationResult(
            original=prompt,
            refined=refined,
            tokens_saved=orig_tokens - ref_tokens,
            savings_percent=((orig_tokens - ref_tokens) / orig_tokens * 100) if orig_tokens > 0 else 0,
            action_taken='refine_simulated' if refined != prompt else 'unchanged',
            cache_hit=False
        )
    
    return optimizer.optimize(prompt, response)


if __name__ == '__main__':
    # Test optimizer
    optimizer = Optimizer()
    
    test_prompts = [
        "Please could you write me a Python function to sort arrays? Thank you very much!",
        "Explain how quantum computing works",
        "Can you debug this code? I would really appreciate your help!",
        "What is the capital of France?",
    ]
    
    print("Optimizer Test Results")
    print("=" * 80)
    
    for prompt in test_prompts:
        result = optimizer.optimize(prompt, "Cached response")
        
        print(f"\nOriginal ({len(prompt)} chars): {prompt[:50]}...")
        print(f"Refined ({len(result.refined)} chars): {result.refined[:50]}...")
        print(f"Tokens saved: {result.tokens_saved} ({result.savings_percent:.1f}%)")
        print(f"Action: {result.action_taken}")
        print(f"Cache hit: {result.cache_hit}")
    
    print("\n" + "=" * 80)
    print("Optimizer Stats:")
    stats = optimizer.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
