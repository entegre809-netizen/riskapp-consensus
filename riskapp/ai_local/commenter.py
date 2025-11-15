# riskapp/ai_local/commenter.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import re as _re

from .ps_estimator import PSEstimator
from .engine import (
    AILocal,
    KEYSETS,
    ACTION_TEMPLATES,
    _kpis_default as _kpis_by_text,
    _dept_raci_defaults
)
from ..models import db, Risk

# (buradan sonrası senin uzunca gönderdiğin kod)
# ...
# def make_ai_risk_comment(...):
#    ...
