# -*- coding: utf-8 -*-
"""전형명과 정규화된 전형 단계에서 표준 분류를 만든다."""


def compact(value):
    # 공백과 문장 부호를 지운 뒤 키워드를 찾는다.
    return "".join(ch for ch in str(value or "") if not ch.isspace() and ch not in "()/[]·,.:;+-")


def selection_evidence(record):
    parts = [record.get("selection_name")]
    for stage in record.get("stages") or []:
        parts.append(stage.get("method"))
        for element in stage.get("elements") or []:
            parts.append(element.get("name"))
    return compact(" ".join(str(part) for part in parts if part))


def selection_method(record):
    text = selection_evidence(record)
    if not text or "모집인원현황" in text or "전형료안내" in text:
        return "기타"
    # 주 전형요소 기준으로 상호배타적으로 분류한다. 혼합형은 더 특수한 요소를 우선한다.
    if any(word in text for word in ("실기", "실적", "예체능")):
        return "실기"
    if "논술" in text:
        return "논술"
    if "수능" in text:
        return "수능"
    if "학생부교과" in text or "학생부교과성적" in text or "교과" in text:
        return "학생부교과"
    if "학생부종합" in text or "학생부" in text or "서류" in text or "면접" in text:
        return "학생부종합"
    return "기타"


def selection_target(record):
    text = selection_evidence(record)
    if not text or "모집인원현황" in text or "전형료안내" in text:
        return "기타"
    # 하나의 전형이 여러 대상을 포함하면 더 특수한 대상을 우선한다.
    if any(word in text for word in ("특수교육", "장애")):
        return "특수교육"
    if any(word in text for word in ("특성화고", "마이스터고")):
        return "특성화고"
    if "농어촌" in text:
        return "농어촌"
    if any(word in text for word in (
        "기회균형", "고른기회", "사회통합", "사회배려", "사회기여", "기초생활",
        "차상위", "한부모", "국가보훈", "보훈", "북한이탈", "저소득",
    )):
        return "기회균형"
    if "특기자" in text:
        return "특기자"
    if any(word in text for word in ("재직", "성인학습", "만학", "평생학습")):
        return "재직성인"
    if any(word in text for word in ("지역인재", "지역균형", "지역의사")):
        return "지역인재"
    if any(word in text for word in ("외국인", "재외국민", "편입")):
        return "기타"
    return "일반"


def quota_type(record):
    text = selection_evidence(record)
    if "정원외" in text:
        return "정원외"
    if "정원내" in text:
        return "정원내"
    # 문서에 정원 구분이 없으면 추측하지 않고 NULL로 둔다.
    return None


def classify_selection(record):
    return selection_method(record), selection_target(record), quota_type(record)
