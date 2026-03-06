#!/usr/bin/env python3
"""
Token Guardian Core - Classifier Module
Classification with confidence scoring, keyword matching, and intent detection
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import yaml


@dataclass
class ClassificationResult:
    """Result of classifying a query"""
    label: str
    confidence: float
    matched_keywords: List[str]
    matched_patterns: List[str]
    reasoning: str
    is_vague: bool = False


class Classifier:
    """Query classifier with confidence scoring and intent detection"""
    
    def __init__(self, routing_config_path: str = None):
        """Initialize classifier with routing rules"""
        self.routing_rules = {}
        self.keywords = {}
        self.classifications = []
        
        if routing_config_path:
            self.load_config(routing_config_path)
        else:
            self._load_defaults()
    
    def _load_defaults(self):
        """Load default classification rules"""
        self.routing_rules = {
            'coding': {
                'preferred': 'xai/grok-4',
                'keywords': ['code', 'function', 'program', 'debug', 'api', 
                            'script', 'algorithm', 'sql', 'javascript',
                            'java', 'class', 'compile', 'execute', 'test', 'refactor',
                            'write', 'create', 'build', 'method']
            },
            'data_analysis': {
                'preferred': 'xai/grok-4',
                'keywords': ['analyze', 'data', 'statistics', 'chart', 'graph',
                            'table', 'query', 'summary', 'trend', 'pattern',
                            'insight', 'report']
            },
            'creative': {
                'preferred': 'openai/gpt-5-mini',
                'keywords': ['write', 'story', 'poem', 'creative', 'article',
                           'blog', 'marketing', 'design', 'narrative', 'character', 'plot']
            },
            'reasoning': {
                'preferred': 'xai/grok-4',
                'keywords': ['explain', 'reason', 'logic', 'why', 'how', 'think',
                           'decide', 'compare', 'evaluate', 'consider']
            },
            'simple_qa': {
                'preferred': 'minimax/MiniMax-M2.1',
                'keywords': ['what', 'when', 'where', 'who', 'why', 'how',
                           'does', 'is', 'are', 'can', 'should', 'could',
                           'what is', 'what are', 'what does', 'define', 'definition',
                           'meaning', 'explain', 'time', 'date', 'weather', 'temperature',
                           'capital', 'population', 'inventor', 'creator', 'author',
                           'location', 'cost', 'price', 'year', 'day', 'called', 'name'],
                'max_length': 100
            },
            'general': {
                'preferred': 'minimax/MiniMax-M2.1',
                'keywords': []
            }
        }
        
        self.classifications = list(self.routing_rules.keys())
    
    def load_config(self, config_path: str):
        """Load routing configuration from YAML file"""
        path = Path(config_path).expanduser()
        if not path.exists():
            self._load_defaults()
            return
        
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load routing rules
            if 'routing_rules' in config:
                for cls_name, cls_config in config['routing_rules'].items():
                    self.routing_rules[cls_name] = {
                        'preferred': cls_config.get('preferred', 'minimax/MiniMax-M2.1'),
                        'keywords': cls_config.get('keywords', []),
                        'max_length': cls_config.get('max_length', 1000)
                    }
            
            self.classifications = list(self.routing_rules.keys())
            
        except Exception as e:
            print(f"[WARN] Failed to load config {config_path}: {e}")
            self._load_defaults()
    
    def _is_vague_query(self, query_lower: str, word_count: int) -> bool:
        """
        Detect vague/undefined queries
        Only marked vague if truly underspecified with no strong intent
        """
        # True vague patterns - these ARE actually vague
        truly_vague = [
            'general question', 'vague', 'about topic', 'in general',
            'something about', 'anything about', 'discuss'
        ]
        
        # Check for true vagueness
        if any(pattern in query_lower for pattern in truly_vague):
            return True
        
        # Very short AND no question words AND no action verbs = vague
        strong_intent_words = [
            'what', 'when', 'where', 'who', 'why', 'how', 'explain', 'define',
            'write', 'create', 'build', 'analyze', 'compare', 'implement'
        ]
        
        has_intent = any(word in query_lower for word in strong_intent_words)
        
        if word_count < 4 and not has_intent:
            return True
        
        return False
    
    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a query with confidence score
        
        Args:
            query: The user query to classify
            
        Returns:
            ClassificationResult with label, confidence, and reasoning
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        query_length = len(query)
        word_count = len(query_words)
        
        # Detect vague queries first
        is_vague = self._is_vague_query(query_lower, word_count)
        
        # Score each classification
        scores = {}
        matched_keywords_all = {}
        
        for cls_name, cls_config in self.routing_rules.items():
            score = 0.0
            matched = []
            patterns = []
            
            # Check length constraint
            max_len = cls_config.get('max_length', 1000)
            if cls_name == 'simple_qa' and query_length > max_len:
                scores[cls_name] = 0.0
                continue
            
            # ============================================
            # REASONING BOOSTS
            # ============================================
            if cls_name == 'reasoning':
                # Reasoning intent patterns (+0.20 to +0.30)
                reasoning_patterns = [
                    ('explain why', 0.30),
                    ('why does', 0.30),
                    ('how does', 0.30),
                    ('pros and cons', 0.25),
                    ('tradeoffs', 0.25),
                    ('walk me through', 0.25),
                    ('step by step', 0.20),
                    ('compare', 0.25),
                    ('differences between', 0.25),
                    ('what are the', 0.20),
                    ('explain the', 0.20),
                    ('reason for', 0.25),
                    ('cause of', 0.25),
                ]
                
                for pattern, boost in reasoning_patterns:
                    if pattern in query_lower:
                        score += boost
                        matched.append(f'reasoning:{pattern}')
                
                # Causal markers (+0.10)
                causal_markers = ['because', 'therefore', 'reason', 'cause', 'impact', 'effect', 'result', 'lead to', 'due to']
                for marker in causal_markers:
                    if marker in query_lower:
                        score += 0.10
                        matched.append(f'causal:{marker}')
                        break
                
                # Length floor: if query has reasoning patterns, floor at 0.80
                has_reasoning_pattern = any(p[0] in query_lower for p in reasoning_patterns)
                has_causal = any(m in query_lower for m in causal_markers)
                
                if (has_reasoning_pattern or has_causal) and word_count >= 12:
                    score = max(score, 0.80)
            
            # ============================================
            # SIMPLE QA BOOSTS
            # ============================================
            if cls_name == 'simple_qa':
                # Question form bonus (+0.15)
                question_starts = ['what', 'when', 'where', 'who', 'why', 'how', 'does', 'is', 'are', 'can', 'should', 'could']
                if any(query_lower.strip().startswith(q) for q in question_starts):
                    score += 0.15
                    matched.append('question_form')
                
                # Short query bonus (+0.10)
                if word_count <= 20:
                    score += 0.10
                    matched.append(f'short({word_count}words)')
                
                # Definition patterns bonus (+0.15)
                definition_patterns = ['what is', 'what are', 'what does', 'define', 'definition', 'meaning']
                for pattern in definition_patterns:
                    if pattern in query_lower:
                        score += 0.15
                        matched.append(f'def_pattern:{pattern}')
                
                # Utility patterns bonus (+0.20)
                utility_patterns = ['time', 'date', 'weather', 'temperature', 'timezone', 'day', 'year', 'capital', 'population']
                for pattern in utility_patterns:
                    if pattern in query_lower:
                        score += 0.20
                        matched.append(f'utility:{pattern}')
                
                # "Who invented" pattern (+0.15)
                if any(x in query_lower for x in ['invented', 'created', 'creator', 'author']):
                    score += 0.15
                    matched.append('inventor_pattern')
            
            # ============================================
            # STANDARD KEYWORD MATCHING (all categories)
            # ============================================
            keywords = cls_config.get('keywords', [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Multi-word phrase match (stronger)
                if ' ' in keyword:
                    if keyword_lower in query_lower:
                        score += 0.35
                        matched.append(keyword)
                # Single word match
                elif keyword_lower in query_words:
                    score += 0.3
                    matched.append(keyword)
                # Partial phrase match
                elif keyword_lower in query_lower:
                    score += 0.2
                    patterns.append(keyword)
            
            # ============================================
            # SPECIALIST LABEL VERB/INTENT PATTERNS (+0.15 per match, cap 2)
            # ============================================
            if cls_name == 'coding':
                coding_verbs = ['write', 'implement', 'fix', 'debug', 'refactor', 'build', 'create']
                verb_matches = sum(1 for v in coding_verbs if v in query_lower)
                if verb_matches > 0:
                    score += 0.15 * min(verb_matches, 2)
                    matched.append(f'coding_verb:{verb_matches}')
            
            if cls_name == 'data_analysis':
                data_verbs = ['analyze', 'summarize', 'compute', 'plot', 'trend', 'correlation', 'statistical', 'calculate', 'find', 'generate', 'forecast', 'predict']
                verb_matches = sum(1 for v in data_verbs if v in query_lower)
                if verb_matches > 0:
                    score += 0.15 * min(verb_matches, 2)
                    matched.append(f'data_verb:{verb_matches}')
                
                # Data analysis nouns - boost when present
                data_nouns = ['metric', 'revenue', 'churn', 'funnel', 'cohort', 'segmentation', 
                            'lifetime value', 'conversion', 'kpi', 'report', 'dashboard', 
                            'forecast', 'trend', 'analysis', 'data', 'dataset', 'sales',
                            'customer', 'business', 'performance', 'insight']
                data_noun_matches = sum(1 for n in data_nouns if n in query_lower)
                if data_noun_matches > 0:
                    score += 0.15 * min(data_noun_matches, 3)
                    matched.append(f'data_noun:{data_noun_matches}')
                
                # Data floor: if 2+ data nouns present, ensure minimum score = 0.50
                if data_noun_matches >= 2:
                    score = max(score, 0.50)
                    matched.append('data_floor:0.50')
            
            if cls_name == 'creative':
                creative_verbs = ['draft', 'rewrite', 'tone', 'headline', 'story', 'script', 'ad copy', 'design']
                verb_matches = sum(1 for v in creative_verbs if v in query_lower)
                if verb_matches > 0:
                    score += 0.15 * min(verb_matches, 2)
                    matched.append(f'creative_verb:{verb_matches}')
            
            # ============================================
            # MULTI-HIT SPECIALIST DENSITY BONUS
            # ============================================
            if cls_name in ('coding', 'data_analysis', 'creative'):
                base_matches = len([m for m in matched if not any(x in m for x in [':', '?', '(', '['])])
                if base_matches >= 3:
                    score += 0.30
                    matched.append(f'multi_hit:{base_matches}')
                elif base_matches == 2:
                    score += 0.20
                    matched.append(f'multi_hit:{base_matches}')
            
            # Coding patterns bonus - only apply full boost if coding noun present
            if cls_name == 'coding':
                # Strong coding nouns (require one of these for full coding boost)
                coding_nouns = ['api', 'function', 'class', 'method', 'component', 'service', 'regex', 'query', 'endpoint', 'schema', 'docker', 'graphql', 'cron', 'blockchain', 'middleware', 'resolver', 
                               'docker', 'resolver', 'script', 'algorithm', 'database', 'endpoint',
                               'middleware', 'container', 'microservice', 'worker', 'pipeline',
                               'handler', 'module', 'interface', 'schema', 'query', 'table']
                
                # Generic coding verbs (weaker without noun)
                generic_verbs = ['write', 'create', 'build']
                
                has_coding_noun = any(noun in query_lower for noun in coding_nouns)
                generic_verb_hits = sum(1 for v in generic_verbs if v in query_lower)
                
                if has_coding_noun:
                    # Full coding boost with noun present
                    code_indicators = ['write', 'create', 'build', 'function', 'code', 'class', 'method']
                    code_matches = sum(1 for w in code_indicators if w in query_lower)
                    score += 0.15 * min(code_matches, 3)
                elif generic_verb_hits > 0:
                    # Weaker boost (+0.05) for generic verbs without coding noun
                    # This prevents "create a blog post" from scoring as coding
                    score += 0.05
                    matched.append('weak_verb_only')
            
            # Creative patterns - explicit detection for blog posts, articles
            if cls_name == 'creative':
                creative_nouns = ['blog', 'post', 'article', 'story', 'poem', 'script', 
                                  'headline', 'tagline', 'slogan', 'caption', 'copy', 'ad',
                                  'content', 'marketing', 'social media', 'email']
                has_creative_noun = any(noun in query_lower for noun in creative_nouns)
                if has_creative_noun:
                    # Give creative a boost when these nouns are present
                    creative_indicators = ['draft', 'write', 'create', 'design', 'rewrite']
                    creative_matches = sum(1 for w in creative_indicators if w in query_lower)
                    if creative_matches > 0:
                        score += 0.15 * min(creative_matches, 2)
                        matched.append(f'creative_noun:{creative_matches}')
            
            # Multiple match bonus
            clean_matches = [m for m in matched if not any(x in m for x in [':', '?', '(', '['])]
            if len(clean_matches) >= 2:
                score += 0.10
            if len(clean_matches) >= 3:
                score += 0.10
            
            # Cap at 1.0, floor at 0
            scores[cls_name] = max(0.0, min(score, 1.0))
            matched_keywords_all[cls_name] = matched
        
        # Strong reasoning pattern detection (for override)
        # These patterns indicate reasoning/complex thinking, NOT simple_qa
        strong_reasoning_patterns = [
            # Complex reasoning patterns
            'explain why', 'why does', 'why is', 'why are', 'how does', 'how can', 'how should',
            'pros and cons', 'tradeoffs', 'advantages and disadvantages',
            'walk me through', 'step by step', 'compare and contrast', 
            'differences between', 'similarities between',
            # Causal reasoning
            'because', 'therefore', 'reason for', 'cause of', 'result of', 'impact of', 
            'effect of', 'lead to', 'due to', 'what causes', 'what leads to',
            # Evaluation patterns
            'evaluate', 'assess', 'analyze pros', 'weigh the', 'consider both',
            # Comparative/analytical
            'think about', 'reason about', 'logic behind', 'argument for'
        ]
        has_strong_reasoning = any(p in query_lower for p in strong_reasoning_patterns)
        
        # Find best match
        best_label = max(scores, key=lambda k: scores[k])
        best_score = scores[best_label]
        
        # Override: if strong reasoning patterns detected, force reasoning label
        if has_strong_reasoning and 'reasoning' in scores:
            best_label = 'reasoning'
            best_score = max(scores['reasoning'], 0.80)  # Floor for strong reasoning
        
        # ============================================
        # SIMPLE_QA HARD GATE: Prevent creative from leaking into simple_qa
        # ============================================
        # Only apply this gate if best_label is simple_qa
        # If creative triggers present, let creative win instead
        if best_label == 'simple_qa':
            # Creative triggers that disqualify simple_qa
            creative_triggers = [
                'story', 'poem', 'blog', 'post', 'article', 'marketing',
                'caption', 'copy', 'ad ', 'script', 'narrative', 'character',
                'plot', 'headline', 'tagline', 'slogan', 'design', 'creative',
                'write a', 'write an', 'create a', 'create an', 'draft a',
                'recipe', 'storytelling', 'social media'
            ]
            has_creative_trigger = any(t in query_lower for t in creative_triggers)
            
            # Question form check
            question_starts = ['what ', 'when ', 'where ', 'who ', 'does ', 'is ', 'are ', 'can ', 'should ', 'could ']
            starts_with_question = any(query_lower.strip().startswith(q.strip()) for q in question_starts)
            
            # Definition pattern check
            definition_patterns = ['what is ', 'what are ', 'what does ', 'define ', 'definition of ', 'meaning of ', 'called ']
            has_definition = any(p in query_lower for p in definition_patterns)
            
            # Apply hard gate for simple_qa
            # If creative trigger present AND (not question OR not definition), fail simple_qa
            if has_creative_trigger:
                if not (starts_with_question or has_definition):
                    # creative trigger without question form → fail simple_qa
                    if 'creative' in scores and scores['creative'] >= 0.30:
                        best_label = 'creative'
                        best_score = max(scores['creative'], 0.45)
                    else:
                        best_label = 'general'
                        best_score = min(best_score, 0.25)
                        is_vague = True
            else:
                # Not creative trigger - check other simple_qa requirements
                if len(query) > 100 or (not starts_with_question and not has_definition):
                    best_label = 'general'
                    best_score = min(best_score, 0.30)
                    is_vague = True
        
        # ============================================
        # CREATIVE OVERRIDE: Creative nouns trump coding verbs
        # ============================================
        # If creative nouns present, force creative label (similar to reasoning override)
        creative_nouns = ['story', 'poem', 'blog', 'post', 'article', 'marketing',
                        'caption', 'copy', 'script', 'narrative', 'character', 'plot',
                        'headline', 'tagline', 'slogan', 'design', 'creative content',
                        'recipe', 'storytelling', 'social media']
        has_creative_noun = any(n in query_lower for n in creative_nouns)
        
        # Generic creative verbs (weaker signal)
        creative_verbs = ['write', 'create', 'draft', 'design', 'rewrite']
        has_creative_verb = any(v in query_lower for v in creative_verbs)
        
        # Creative override: if creative noun present AND has creative verb, force creative
        if has_creative_noun and has_creative_verb and 'creative' in scores:
            if best_label == 'coding' and scores['creative'] < scores['coding']:
                # Creative noun + verb should win over coding
                best_label = 'creative'
                best_score = max(scores['creative'], 0.60)
        
        # ============================================
        # SURGICAL FIX: Prevent weak labels from winning on low evidence
        # ============================================
        # If best_label is "general" or "simple_qa" with weak evidence, 
        # use intent verbs to force a specialist label
        # Note: matched_keywords_all may include partial matches and boosts,
        # so we check for actual keyword presence (not partial, not boosts)
        if best_label in ('general', 'simple_qa') and best_score < 0.50:
            coding_verbs = ['write', 'implement', 'fix', 'debug', 'refactor', 'build', 'create']
            data_verbs = ['analyze', 'summarize', 'compute', 'plot', 'trend', 'correlation', 'statistical', 'calculate', 'find', 'generate', 'forecast', 'predict']
            creative_verbs = ['draft', 'rewrite', 'tone', 'headline', 'story', 'script', 'ad copy', 'design']
            
            coding_hits = sum(1 for v in coding_verbs if v in query_lower)
            data_hits = sum(1 for v in data_verbs if v in query_lower)
            creative_hits = sum(1 for v in creative_verbs if v in query_lower)
            
            # Count actual keyword matches (not partial, not boosts)
            # matched keywords are those without ':', '(', etc.
            simple_qa_kw = [m for m in matched_keywords_all.get('simple_qa', []) 
                           if not any(x in m for x in [':', '(', '?', '['])]
            
            # Strong specialist intent (2+ verbs) wins
            if coding_hits >= 2 and 'coding' in scores:
                best_label = 'coding'
                best_score = max(scores['coding'], 0.55)
            elif data_hits >= 2 and 'data_analysis' in scores:
                best_label = 'data_analysis'
                best_score = max(scores['data_analysis'], 0.55)
            elif creative_hits >= 2 and 'creative' in scores:
                best_label = 'creative'
                best_score = max(scores['creative'], 0.55)
            # Single verb hint can win if current label has NO real keywords
            elif best_label == 'simple_qa' and len(simple_qa_kw) == 0:
                if coding_hits >= 1 and 'coding' in scores:
                    best_label = 'coding'
                    best_score = max(scores['coding'], 0.45)
                elif data_hits >= 1 and 'data_analysis' in scores:
                    best_label = 'data_analysis'
                    best_score = max(scores['data_analysis'], 0.45)
                elif creative_hits >= 1 and 'creative' in scores:
                    best_label = 'creative'
                    best_score = max(scores['creative'], 0.45)
        
        # ============================================
        # TIE-BREAKER: Creative wins over coding when creative noun present
        # ============================================
        if best_label == 'coding' and 'creative' in scores:
            # Check if creative has creative nouns (blog, post, article, story, etc.)
            creative_nouns = ['blog', 'post', 'article', 'story', 'poem', 'script', 
                             'headline', 'tagline', 'slogan', 'caption', 'copy', 'ad',
                             'content', 'marketing', 'social media', 'recipe']
            has_creative_noun = any(noun in query_lower for noun in creative_nouns)
            # Generic coding verbs that shouldn't override creative nouns
            generic_verbs = ['write', 'create', 'build', 'design']
            has_generic_verb = any(v in query_lower for v in generic_verbs)
            
            if has_creative_noun and has_generic_verb:
                if scores['creative'] >= scores['coding'] - 0.15:  # Close enough
                    best_label = 'creative'
                    best_score = max(scores['creative'], 0.50)  # Floor for creative with noun
        
        # ============================================
        # ZERO-MATCH FLOOR: Specialist intent with 2+ verbs gets minimum score
        # ============================================
        if best_label in ('coding', 'data_analysis', 'creative'):
            coding_verbs = ['write', 'implement', 'fix', 'debug', 'refactor', 'build', 'create']
            data_verbs = ['analyze', 'summarize', 'compute', 'plot', 'trend', 'correlation', 'statistical', 'calculate', 'find', 'generate', 'forecast', 'predict']
            creative_verbs = ['draft', 'rewrite', 'tone', 'headline', 'story', 'script', 'ad copy', 'design']
            
            verb_list = coding_verbs if best_label == 'coding' else (data_verbs if best_label == 'data_analysis' else creative_verbs)
            verb_hits = sum(1 for v in verb_list if v in query_lower)
            
            if verb_hits >= 2:
                best_score = max(best_score, 0.55)  # Floor for strong intent
        
        # Build reasoning
        matched_list = matched_keywords_all.get(best_label, [])
        reasoning_parts = []
        
        if is_vague:
            reasoning_parts.append("vague query")
        
        if best_label == 'simple_qa':
            boosts = [m for m in matched_list if any(x in m for x in ['question_form', 'short(', 'def_pattern', 'utility', 'inventor'])]
            if boosts:
                reasoning_parts.append(f"boosts: {', '.join(boosts[:3])}")
        
        if best_label == 'reasoning':
            boosts = [m for m in matched_list if 'reasoning:' in m or 'causal:' in m]
            if boosts:
                reasoning_parts.append(f"reasoning: {', '.join(boosts[:2])}")
        
        clean_keywords = [m for m in matched_list if ':' not in m and '(' not in m]
        if clean_keywords:
            reasoning_parts.append(f"matched: {', '.join(clean_keywords[:3])}")
        
        if not reasoning_parts:
            reasoning_parts.append("default classification")
        
        return ClassificationResult(
            label=best_label,
            confidence=best_score,
            matched_keywords=clean_keywords,
            matched_patterns=patterns,
            reasoning="; ".join(reasoning_parts),
            is_vague=is_vague
        )
    
    def get_preferred_model(self, label: str) -> str:
        """Get preferred model for a classification label"""
        if label in self.routing_rules:
            return self.routing_rules[label]['preferred']
        return 'minimax/MiniMax-M2.1'
    
    def get_safe_fallback_model(self) -> str:
        """Get safe fallback model for low-confidence scenarios"""
        return 'openai/gpt-5-mini'


def classify_with_confidence(query: str, 
                            threshold: float = 0.80,
                            routing_config: str = None) -> Tuple[ClassificationResult, str, bool]:
    """
    Classify query and determine if fallback is needed
    
    Args:
        query: User query
        threshold: Confidence threshold for fallback
        routing_config: Path to routing.yaml config
        
    Returns:
        Tuple of (ClassificationResult, selected_model, used_fallback)
    """
    classifier = Classifier(routing_config)
    result = classifier.classify(query)
    
    # Determine model selection with two-tier fallback
    if result.confidence < threshold:
        # Below threshold - determine which fallback tier
        if result.label == 'simple_qa' and result.confidence >= 0.60:
            # Simple QA in LOW band - route to intended cheap model
            selected_model = classifier.get_preferred_model(result.label)
            fallback_reason = f"LOW_CONF_SIMPLE_QA_OK: conf={result.confidence:.2f}"
        elif result.is_vague:
            # Vague query - safe route
            selected_model = classifier.get_safe_fallback_model()
            fallback_reason = f"VAGUE_QUERY_SAFE_ROUTE: conf={result.confidence:.2f}"
        elif result.confidence < 0.60:
            # Very low confidence - use safe fallback
            selected_model = classifier.get_safe_fallback_model()
            fallback_reason = f"VERY_LOW_CONF_FALLBACK: conf={result.confidence:.2f}"
        else:
            # Other categories below threshold
            selected_model = classifier.get_safe_fallback_model()
            fallback_reason = f"LOW_CONF: conf={result.confidence:.2f} < {threshold}"
        
        used_fallback = True
    else:
        # Normal routing
        selected_model = classifier.get_preferred_model(result.label)
        used_fallback = False
        fallback_reason = ""
    
    return result, selected_model, used_fallback


if __name__ == '__main__':
    # Test classifier
    classifier = Classifier()
    
    test_queries = [
        "Write a Python function to sort arrays",
        "Analyze sales data from last quarter",
        "Write a creative story about space",
        "Explain why the sky is blue",
        "What is machine learning?",
        "What time is it?",
        "General question about AI",
        "Compare REST vs GraphQL",
        "Pros and cons of AI",
        "Short question",
    ]
    
    print("Classification Test Results")
    print("=" * 80)
    
    for query in test_queries:
        result = classifier.classify(query)
        fallback = result.confidence < 0.80
        model = classifier.get_safe_fallback_model() if fallback else classifier.get_preferred_model(result.label)
        
        print(f"\nQuery: {query}")
        print(f"  Label: {result.label}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Vague: {result.is_vague}")
        print(f"  Keywords: {result.matched_keywords}")
        print(f"  Reasoning: {result.reasoning}")
