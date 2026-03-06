#!/usr/bin/env python3
"""
Token Guardian Core - Unified Pipeline
Orchestrates classification, routing, optimization, and monitoring
"""
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from .classifier import Classifier, ClassificationResult
from .optimizer import Optimizer, OptimizationResult
from .monitor import Monitor, TokenRecord

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Complete routing decision with all context"""
    timestamp: str
    query: str
    classification: str
    confidence: float
    threshold: float
    selected_model: str
    fallback_triggered: bool
    fallback_reason: str
    optimization: Optional[Dict[str, Any]] = None
    estimated_cost: float = 0.0
    status: str = "pending"


class UnifiedPipeline:
    """
    Unified Token Guardian Pipeline
    
    Single entry point for:
    - Query classification with confidence
    - Safe model routing with fallback
    - Prompt optimization
    - Token monitoring and audit
    """
    
    def __init__(self, 
                 config_dir: str = None,
                 shadow_mode: bool = True):
        """
        Initialize unified pipeline
        
        Args:
            config_dir: Configuration directory
            shadow_mode: If True, log decisions but don't modify behavior
        """
        self.config_dir = Path(config_dir) if config_dir else Path('~/.tokenguardian').expanduser()
        self.shadow_mode = shadow_mode
        
        # Load routing config for threshold
        self.routing_config = self._load_routing_config()
        self.confidence_threshold = self.routing_config.get('confidence_threshold', 0.80)
        self.safe_fallback_model = self.routing_config.get('safe_fallback', {}).get('model', 'openai/gpt-5-mini')
        
        # Initialize components
        self.classifier = Classifier(str(self.config_dir / 'routing.yaml') if (self.config_dir / 'routing.yaml').exists() else None)
        self.optimizer = Optimizer(str(self.config_dir / 'guardian.yaml') if (self.config_dir / 'guardian.yaml').exists() else None)
        self.monitor = Monitor(str(self.config_dir))
        
        # Decision log
        self.decision_log: List[RoutingDecision] = []
        
        logger.info(f"Pipeline initialized (shadow={shadow_mode}, threshold={self.confidence_threshold})")
    
    def _load_routing_config(self) -> Dict[str, Any]:
        """Load routing configuration"""
        config_paths = [
            self.config_dir / 'routing.yaml',
            Path('/etc/tokenguardian/routing.yaml')
        ]
        
        for path in config_paths:
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        return yaml.safe_load(f)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
        
        return {'confidence_threshold': 0.80, 'safe_fallback': {'model': 'openai/gpt-5-mini'}}
    
    def process(self, query: str, response: str = None) -> RoutingDecision:
        """
        Process a query through the complete pipeline
        
        Args:
            query: User query
            response: Optional response to cache
            
        Returns:
            RoutingDecision with complete routing context
        """
        import time
        start_ms = int(time.time() * 1000)
        
        timestamp = datetime.now().isoformat()
        
        # Step 1: Classify with confidence
        classification = self.classifier.classify(query)
        
        # Step 2: Determine model selection with THREE-TIER FALLBACK
        # Tiers: 
        #   - global: 0.80
        #   - specialist LOW band: 0.45-0.79
        #   - simple_qa budget: 0.45-0.59 (MiniMax)
        #   - simple_qa LOW: 0.60-0.79 (MiniMax)
        #   - safe quality fallback: <0.45 or VAGUE (gpt-5-mini)
        preferred_model = self.classifier.get_preferred_model(classification.label)
        
        if classification.confidence < self.confidence_threshold:
            # Below global threshold - check tier
            if classification.is_vague:
                # Vague query - safe quality fallback
                selected_model = self.safe_fallback_model
                fallback_triggered = True
                fallback_reason = f"VAGUE_QUERY_SAFE_ROUTE: conf={classification.confidence:.2f}"
            elif classification.label == 'simple_qa' and classification.confidence >= 0.60:
                # Simple QA in LOW band (0.60-0.79) → budget MiniMax
                selected_model = preferred_model  # MiniMax
                fallback_triggered = True
                fallback_reason = f"LOW_CONF_SIMPLE_QA_OK: conf={classification.confidence:.2f} → {selected_model}"
            elif classification.label == 'simple_qa' and 0.45 < classification.confidence < 0.60:
                # Simple QA in budget band (0.45-0.59) → budget MiniMax
                selected_model = preferred_model  # MiniMax
                fallback_triggered = True
                fallback_reason = f"BUDGET_SIMPLE_QA: conf={classification.confidence:.2f} → {selected_model}"
            elif classification.label in ('coding', 'data_analysis', 'creative', 'reasoning') and classification.confidence > 0.44:
                # Specialist in LOW band (0.45-0.79) → preferred specialist
                selected_model = preferred_model
                fallback_triggered = True
                fallback_reason = f"LOW_CONF_{classification.label.upper()}_OK: conf={classification.confidence:.2f} → {selected_model}"
            elif classification.confidence <= 0.45:
                # Very low confidence or simple_qa < 0.45 → safe quality fallback
                selected_model = self.safe_fallback_model
                fallback_triggered = True
                fallback_reason = f"SAFE_QUALITY_FALLBACK: conf={classification.confidence:.2f} < 0.45"
            else:
                # Other cases → safe fallback
                selected_model = self.safe_fallback_model
                fallback_triggered = True
                fallback_reason = f"LOW_CONF: conf={classification.confidence:.2f} < {self.confidence_threshold}"
        else:
            # Normal routing
            selected_model = preferred_model
            fallback_triggered = False
            fallback_reason = ""
        
        # Step 3: Optimize prompt (if not shadow)
        optimization = None
        if self.shadow_mode:
            # Simulate optimization
            opt_result = self.optimizer.optimize(query, response) if not self.shadow_mode else None
            if opt_result:
                optimization = {
                    'action': 'refine_simulated',
                    'tokens_saved': opt_result.tokens_saved,
                    'savings_percent': opt_result.savings_percent
                }
        else:
            # Actually optimize
            opt_result = self.optimizer.optimize(query, response)
        
        # Create decision record
        decision = RoutingDecision(
            timestamp=timestamp,
            query=query,
            classification=classification.label,
            confidence=classification.confidence,
            threshold=self.confidence_threshold,
            selected_model=selected_model,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            optimization=optimization,
            estimated_cost=0.001,
            status="shadow" if self.shadow_mode else "dispatched"
        )
        
        # Log decision
        self.decision_log.append(decision)
        
        # REQ_DONE logging for per-request latency tracking
        end_ms = int(time.time() * 1000)
        duration_ms = end_ms - start_ms
        import uuid
        request_id = uuid.uuid4().hex[:8]
        logger.info(f"REQ_DONE: ts={timestamp} lane={classification.label} provider={selected_model} duration_ms={duration_ms} request_id={request_id}")
        
        # Log routing decision
        if fallback_triggered:
            logger.warning(f"ROUTING: label={classification.label} confidence={classification.confidence:.2f} threshold={self.confidence_threshold} model={selected_model} fallback=YES:{fallback_reason}")
        else:
            logger.info(f"ROUTING: label={classification.label} confidence={classification.confidence:.2f} threshold={self.confidence_threshold} model={selected_model} fallback=NO")
        
        return decision
    
    def dispatch(self, query: str) -> Dict[str, Any]:
        """
        Dispatch query to selected model
        
        In shadow mode, just log what would have been done
        In live mode, actually dispatch
        """
        from .classifier import ClassificationResult
        
        # Process through pipeline
        decision = self.process(query)
        
        # Dispatch to model
        if self.shadow_mode:
            return {
                'status': 'shadow',
                'message': f"Would have dispatched to {decision.selected_model}",
                'query_preview': decision.query[:50] + "...",
                'estimated_cost': decision.estimated_cost
            }
        
        # Live mode - in real implementation, call the model API here
        # For now, record usage
        self.monitor.record_usage(
            len(decision.query) // 4 + 100,
            decision.selected_model,
            'dispatched'
        )
        
        return {
            'status': 'dispatched',
            'model': decision.selected_model,
            'estimated_cost': decision.estimated_cost
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        last_decision = self.decision_log[-1] if self.decision_log else None
        
        return {
            'mode': 'shadow' if self.shadow_mode else 'live',
            'confidence_threshold': self.confidence_threshold,
            'safe_fallback_model': self.safe_fallback_model,
            'decisions_logged': len(self.decision_log),
            'last_decision': {
                'timestamp': last_decision.timestamp if last_decision else None,
                'classification': last_decision.classification if last_decision else None,
                'model': last_decision.selected_model if last_decision else None,
                'fallback': last_decision.fallback_triggered if last_decision else None
            },
            'monitor_stats': self.monitor.get_stats()
        }
    
    def get_recent_decisions(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent routing decisions"""
        decisions = self.decision_log[-count:]
        
        return [
            {
                'timestamp': d.timestamp,
                'classification': d.classification,
                'confidence': d.confidence,
                'model': d.selected_model,
                'fallback': d.fallback_triggered
            }
            for d in decisions
        ]


def create_pipeline(config_dir: str = None, shadow_mode: bool = True) -> UnifiedPipeline:
    """Factory function to create pipeline instance"""
    return UnifiedPipeline(config_dir, shadow_mode)


if __name__ == '__main__':
    # Test unified pipeline
    print("Unified Pipeline Test")
    print("=" * 80)
    
    pipeline = create_pipeline(shadow_mode=True)
    
    test_queries = [
        "Write a Python function to sort arrays",
        "Analyze sales data from last quarter",
        "Write a creative story about space",
        "Explain why the sky is blue",
        "What's 2+2?",
        "General question",
    ]
    
    print(f"\nPipeline Status: {pipeline.get_status()['mode']}")
    print(f"Confidence Threshold: {pipeline.confidence_threshold}")
    print(f"Safe Fallback: {pipeline.safe_fallback_model}")
    print("\n" + "-" * 80)
    
    for query in test_queries:
        decision = pipeline.process(query)
        
        print(f"\nQuery: {query[:50]}...")
        print(f"  Classification: {decision.classification} (conf={decision.confidence:.2f})")
        print(f"  Model: {decision.selected_model}")
        print(f"  Fallback: {'YES - ' + decision.fallback_reason if decision.fallback_triggered else 'NO'}")
    
    print("\n" + "=" * 80)
    print("\nPipeline Status:")
    status = pipeline.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
