# -*- coding: utf-8 -*-
"""집필 프로바이더 오류 — 화면이 사람에게 무엇을 하라고 말할 수 있게 타입을 나눈다.

★ 출처: showcase-agent/llm/errors.py 의 계약과 같게 유지한다.
  두 앱이 같은 CLI·같은 구독을 쓰므로, 오류 분류가 갈리면 같은 증상에 서로 다른
  안내가 나간다(SME 는 두 앱을 같은 PC 에서 쓴다).

세 가지로 나누는 이유 — 사람이 할 일이 서로 다르다:
  NotAuthenticated : 로그인해야 한다 (SME 본인 계정)      → 앱이 대신 못 한다
  QuotaExceeded    : 기다려야 한다 (구독 사용량 한도)      → 재시도가 의미 있다
  ProviderError    : 그 밖 — 프롬프트·스키마·네트워크      → 재시도해도 같다
"""
from __future__ import annotations


class ProviderError(RuntimeError):
    """집필 호출이 실패했다. 재시도해도 같은 결과일 가능성이 높다."""


class NotAuthenticated(ProviderError):
    """Claude Code 로그인이 없거나 만료됐다.

    ★ 앱이 해결할 수 없다. API 키를 받아 우회하지 **않는다** —
      집필자별 구독으로 과금·사용량을 가르는 것이 이 방식의 목적이다.
    """


class QuotaExceeded(ProviderError):
    """구독 사용량 한도에 걸렸다. 시간이 지나면 풀린다."""
