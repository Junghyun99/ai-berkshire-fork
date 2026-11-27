"""동일한 주식 예산에서 합성 후보의 비중·집중도·충격 기여를 비교한다."""
from fractions import Fraction as F

groups = ("X", "X", "Y")
budget = F(3, 5)
for method in ("종목 동일가중", "그룹 동일가중"):
    weights = [F(1, len(groups)) if method == "종목 동일가중" else
               F(1, len(set(groups)) * groups.count(group)) for group in groups]
    exposure = sum(w for w, group in zip(weights, groups) if group == "X")
    assert sum(weights) == 1 and all(w > 0 for w in weights)
    assert sum(budget * w for w in weights) == budget
    hhi = sum(w*w for w in weights)
    print(method, "주식 내부 비중", list(map(str, weights)),
          "X 노출", str(exposure), "종목 HHI", str(hhi),
          "X 동반 하락 기여", str(-budget * exposure / 5),
          "C 단독 하락 기여", str(-budget * weights[2] / 5))
