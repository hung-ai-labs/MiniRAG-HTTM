"""Phân loại câu trả lời cho câu Null bằng regex — dùng chung cho các script kiểm toán Null.

Ba kiểu:
- `từ chối thuần`        — mở đầu nói không có thông tin và không suy đoán tiếp
- `từ chối rồi suy đoán` — mở đầu nói không có thông tin rồi vẫn đưa phỏng đoán
- `khẳng định`           — không mở đầu bằng lời từ chối

Đây là heuristic để phân tầng mẫu và mô tả, KHÔNG phải nhãn đúng. Người rà quyết định (Đ1).
"""
import re

NEG = re.compile(
    r"insufficient information|no information|there (is|are) no\b|"
    r"(is|are)n'?t (any |a )?(explicit |specific |direct |clear )?(mention|information|record|detail)|"
    r"no (explicit|specific|direct|clear|particular) (mention|information|record|detail)|"
    r"not (explicitly |specifically |directly |clearly )?(mentioned|specified|stated|provided|detailed)|"
    r"does(n'?t| not) (mention|specify|provide|state|say|indicate)|cannot (be )?determine|unable to determine",
    re.I,
)
SPEC = re.compile(r"\b(however|likely|it appears|appears to|suggests?|infer|inferred|probably|might|may have|could be)\b", re.I)
# nói "không tìm thấy" ở BẤT KỲ đâu trong câu trả lời, không chỉ ở mở đầu
SAYS_NO = re.compile(
    r"no (specific|explicit|direct|clear|particular)? ?(mention|information|record|detail|data)|"
    r"there (is|are)n?'?t? (any |no )|"
    r"not (explicitly |specifically |directly |clearly )?(mentioned|specified|stated|provided|detailed|documented)|"
    r"does(n'?t| not) (mention|specify|provide|state|say|indicate)|insufficient information|no mention",
    re.I,
)

PURE, MIXED, ASSERT = "từ chối thuần", "từ chối rồi suy đoán", "khẳng định"
KINDS = (PURE, MIXED, ASSERT)


def kind(answer: str) -> str:
    m = NEG.search(answer[:250])
    if not m:
        return ASSERT
    return MIXED if SPEC.search(answer[m.end():]) else PURE


def says_no(answer: str) -> bool:
    """Câu trả lời có nói rõ ở đâu đó rằng chi tiết được hỏi không có trong dữ liệu không."""
    return bool(SAYS_NO.search(answer))
