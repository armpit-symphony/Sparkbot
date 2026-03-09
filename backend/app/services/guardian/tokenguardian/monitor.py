#!/usr/bin/env python3
"""
Token Guardian Core - Monitor Module
Token tracking, cost estimation, and usage monitoring
"""
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml


@dataclass
class TokenRecord:
    """Record of token usage"""
    timestamp: str
    tokens: int
    cost: float
    model: str
    action: str


@dataclass
class UsageStats:
    """Aggregated usage statistics"""
    total_tokens: int = 0
    total_cost: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    requests_processed: int = 0
    refinements: int = 0
    by_model: Dict[str, int] = field(default_factory=dict)
    by_action: Dict[str, int] = field(default_factory=dict)


class Monitor:
    """Token usage monitoring and cost tracking"""
    
    def __init__(self, config_path: str = None):
        """Initialize monitor with configuration"""
        self.config_dir = Path('~/.tokenguardian').expanduser()
        self.stats_file = self.config_dir / 'stats.json'
        self.audit_dir = self.config_dir / 'audit'
        
        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        # Load models config for cost calculations
        self.models = {}
        self._load_models()
        
        # Initialize or load stats
        self.stats = self._load_stats()
        
        # Token records
        self.records: List[TokenRecord] = []
        
        # Track last poll for delta calculations
        self._last_total_tokens = 0
        self._last_by_model = {}
    
    def _load_models(self):
        """Load model costs from config"""
        config_path = self.config_dir / 'models.yaml'
        system_path = Path('/etc/tokenguardian/models.yaml')
        
        if config_path.exists():
            self._load_models_from_file(str(config_path))
        elif system_path.exists():
            self._load_models_from_file(str(system_path))
        else:
            # Default costs (per 1M tokens)
            self.models = {
                'MiniMax-M2.1': {'input': 0.50, 'output': 0.50},
                'gpt-5-mini': {'input': 1.50, 'output': 6.00},
                'grok-4': {'input': 3.00, 'output': 15.00},
                'gpt-5.2': {'input': 10.00, 'output': 30.00},
                'minimax/MiniMax-M2.1': {'input': 0.50, 'output': 0.50},
                'openai/gpt-5-mini': {'input': 1.50, 'output': 6.00},
                'xai/grok-4': {'input': 3.00, 'output': 15.00},
                'openai/gpt-5.2': {'input': 10.00, 'output': 30.00},
            }
    
    def _load_models_from_file(self, path: str):
        """Load model definitions from YAML"""
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            
            if 'models' in config:
                for model_name, model_config in config['models'].items():
                    cost = model_config.get('cost', {'input': 1.0, 'output': 1.0})
                    self.models[model_name] = {
                        'input': cost.get('input', 1.0),
                        'output': cost.get('output', 1.0)
                    }
        except Exception as e:
            print("[WARN] Failed to load models from {}: {}".format(path, e))
    
    def _load_stats(self) -> UsageStats:
        """Load stats from file"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                
                return UsageStats(
                    total_tokens=data.get('total_tokens', 0),
                    total_cost=data.get('estimated_cost', 0.0),
                    cache_hits=data.get('cache_hits', 0),
                    requests_processed=data.get('requests_processed', 0),
                    by_model=data.get('by_model', {}),
                    by_action=data.get('by_action', {})
                )
            except Exception:
                pass
        
        return UsageStats()
    
    def _save_stats(self):
        """Save stats to file"""
        model_sum = sum(self.stats.by_model.values()) if self.stats.by_model else 0
        unattributed_gap = self.stats.total_tokens - model_sum
        data = {
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'total_tokens': self.stats.total_tokens,
            'estimated_cost': self.stats.total_cost,
            'cache_hits': self.stats.cache_hits,
            'requests_processed': self.stats.requests_processed,
            'by_model': self.stats.by_model,
            'by_action': self.stats.by_action,
            'unattributed_gap': unattributed_gap,
            'attribution_lag_detected': unattributed_gap > 0
        }
        
        with open(self.stats_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _estimate_cost_for_model(self, tokens: int, model: str) -> float:
        """Estimate cost for token usage on a model."""
        if model not in self.models:
            # Default cost if model unknown
            return tokens * 0.001 / 1_000_000
        
        # Average input/output split (70% input, 30% output for estimation)
        model_costs = self.models[model]
        avg_rate = (model_costs.get('input', 1.0) * 0.7 + model_costs.get('output', 1.0) * 0.3)
        return tokens * avg_rate / 1_000_000
    
    def poll_openclaw(self) -> Dict[str, Any]:
        """
        Poll OpenClaw for current session token data by parsing actual session files.
        
        This correctly attributes tokens by reading the actual usage data from session JSONL files.
        
        Returns: dict with current token state
        """
        try:
            configured = os.getenv("OPENCLAW_SESSIONS_DIR", "").strip()
            if configured:
                sessions_dir = Path(configured).expanduser()
            else:
                sessions_dir = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
            
            if not sessions_dir.exists():
                return {"error": "Sessions directory not found"}
            
            total_tokens = 0
            total_input = 0
            total_output = 0
            total_cache_read = 0
            total_cache_write = 0
            by_model = {}
            session_count = 0
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            
            for filepath in sessions_dir.glob('*.jsonl'):
                try:
                    # Read first line to get session timestamp
                    with open(filepath, 'r') as f:
                        first_line = f.readline()
                        if not first_line:
                            continue
                        first_event = json.loads(first_line)
                        session_time = first_event.get("timestamp", "")
                        if session_time:
                            session_dt = datetime.fromisoformat(session_time.replace("Z", "+00:00"))
                            if session_dt < cutoff:
                                continue  # Skip old sessions
                    
                    # Parse all usage from this session
                    with open(filepath, 'r') as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                event = json.loads(line)
                                if event.get("type") == "message" and event.get("message"):
                                    msg = event.get("message", {})
                                    if isinstance(msg, dict):
                                        usage = msg.get("usage", {})
                                        if usage and isinstance(usage, dict):
                                            provider = msg.get("provider", "unknown")
                                            model = msg.get("model", "")
                                            model_key = f"{provider}/{model}" if model else provider
                                            
                                            tokens = usage.get("input", 0) + usage.get("output", 0)
                                            if tokens > 0:
                                                total_tokens += tokens
                                                total_input += usage.get("input", 0)
                                                total_output += usage.get("output", 0)
                                                total_cache_read += usage.get("cacheRead", 0)
                                                total_cache_write += usage.get("cacheWrite", 0)
                                                
                                                if model_key not in by_model:
                                                    by_model[model_key] = 0
                                                by_model[model_key] += tokens
                            except json.JSONDecodeError:
                                continue
                    
                    session_count += 1
                    
                except Exception:
                    continue
            
            # Calculate new tokens since last poll
            new_tokens = total_tokens - self._last_total_tokens
            
            # Update last poll values
            self._last_total_tokens = total_tokens
            
            return {
                "success": True,
                "total_tokens": total_tokens,
                "new_tokens": max(0, new_tokens),
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cache_read": total_cache_read,
                "cache_write": total_cache_write,
                "by_model": by_model,
                "session_count": session_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def update_from_openclaw(self) -> Dict[str, Any]:
        """
        Poll OpenClaw and update internal stats.
        
        This is the main method called each cycle.
        """
        poll_result = self.poll_openclaw()
        
        if not poll_result.get("success", False):
            return poll_result
        
        # Update total tokens
        total = poll_result["total_tokens"]
        new_tokens = poll_result["new_tokens"]
        by_model = poll_result["by_model"]
        
        if total > self.stats.total_tokens:
            self.stats.total_tokens = total
        
        # Update by_model breakdown
        self.stats.by_model = by_model
        
        # Calculate cost for new tokens
        if new_tokens > 0 and self.stats.total_tokens > 0:
            # Estimate cost based on model distribution
            total_cost = 0
            for model, tokens in by_model.items():
                total_cost += self._estimate_cost_for_model(tokens, model)
            
            # Add cost proportionally for new tokens
            cost_increment = total_cost * (new_tokens / total)
            self.stats.total_cost += cost_increment
        
        # Save stats
        self._save_stats()
        
        return poll_result
    
    def record_usage(self, 
                    tokens: int, 
                    model: str, 
                    action: str = 'unknown',
                    is_output: bool = False):
        """Record token usage"""
        cost = self._estimate_cost_for_model(tokens, model)
        
        # Update stats
        self.stats.total_tokens += tokens
        self.stats.total_cost += cost
        self.stats.requests_processed += 1
        
        # Track by model
        if model not in self.stats.by_model:
            self.stats.by_model[model] = 0
        self.stats.by_model[model] += tokens
        
        # Track by action
        if action not in self.stats.by_action:
            self.stats.by_action[action] = 0
        self.stats.by_action[action] += 1
        
        # Record
        record = TokenRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tokens=tokens,
            cost=cost,
            model=model,
            action=action
        )
        self.records.append(record)
        
        # Save periodically (every 10 records)
        if len(self.records) % 10 == 0:
            self._save_stats()
    
    def record_cache_hit(self):
        """Record a cache hit"""
        self.stats.cache_hits += 1
        self._save_stats()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            'total_tokens': self.stats.total_tokens,
            'total_cost': self.stats.total_cost,
            'cache_hits': self.stats.cache_hits,
            'requests': self.stats.requests_processed,
            'by_model': self.stats.by_model,
            'by_action': self.stats.by_action,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }


def get_monitor_stats(config_dir: str = None) -> Dict[str, Any]:
    """Convenience function to get monitor stats."""
    monitor = Monitor(config_dir)
    return monitor.get_stats()


if __name__ == '__main__':
    # Test monitor with OpenClaw
    print("Testing Monitor with OpenClaw...")
    monitor = Monitor()
    
    result = monitor.update_from_openclaw()
    print("Poll result: {}".format(json.dumps(result, indent=2)))
    
    stats = monitor.get_stats()
    print("\nCurrent Stats:")
    for key, value in stats.items():
        print("  {}: {}".format(key, value))
