from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT / "data" / "workspaces"
PUBLISHED_DIR = ROOT / "published"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.publish import publish_report


REPORTS = [
    {
        "workspace": "20260330-ywc-jongseok-ko",
        "subject_name": "Jongseok Ko",
        "test_date": "2026-01-16",
        "comment_title": "Jongseok Ko 코멘트",
        "comment_body": (
            "현재 프로필은 상단 ceiling과 지구력 연료 효율이 모두 강한 편입니다. "
            "VO2max 69.5와 FatMax 248W 조합은 이미 긴 steady 구간을 높은 출력에서 유지할 수 있다는 뜻이라, "
            "지금 단계에서는 무작정 더 세게 하기보다 230-260W 부근의 지구력 재현성과 후반 안정성을 더 정교하게 끌어올리는 편이 좋습니다. "
            "상단은 이미 충분히 열려 있으니, 다음 블럭은 높은 엔진을 실제 레이스 지속성으로 연결하는 데 집중하는 것이 맞습니다."
        ),
    },
    {
        "workspace": "20260330-ywc-youngsu-byeon",
        "subject_name": "Youngsu Byeon",
        "test_date": "2026-01-16",
        "comment_title": "Youngsu Byeon 코멘트",
        "comment_body": (
            "이번 결과는 절대 출력 기반 엔진이 아주 강하다는 점이 가장 먼저 보입니다. "
            "FatMax 362W와 VT2 241W는 파워를 만드는 능력이 확실하다는 신호라, 강점을 유지하면서도 threshold 아래 지구력 구간을 더 길게 안정화하면 레이스 체감이 크게 달라질 수 있습니다. "
            "RQ 1.0 이전 연료 분할은 이번 데이터에서 명확히 잡히지 않았기 때문에, 다음 테스트에서는 같은 프로토콜로 연료 효율 구간을 한 번 더 확인해 두면 훈련 처방의 정확도가 더 좋아집니다."
        ),
    },
    {
        "workspace": "20260330-ywc-miso-kim",
        "subject_name": "Miso Kim",
        "test_date": "2026-01-16",
        "comment_title": "Miso Kim 코멘트",
        "comment_body": (
            "이번 프로필은 상단 반응은 살아 있지만, 오래 버티는 aerobic base를 더 키울 여지가 분명히 보입니다. "
            "FatMax 99W와 VT2 142W 조합은 현재는 고강도 반응보다 기본 지구력 바탕을 먼저 넓히는 편이 효율적이라는 뜻입니다. "
            "다음 단계에서는 쉬운 구간 볼륨과 중간 강도 지속 시간을 늘려서 100-140W 영역이 더 편해지도록 만드는 것이 우선이고, "
            "그 위에 짧은 고강도를 얹는 구조가 더 잘 맞습니다."
        ),
    },
    {
        "workspace": "20260330-ywc-daseul-song",
        "subject_name": "Daseul Song",
        "test_date": "2026-01-16",
        "comment_title": "Daseul Song 코멘트",
        "comment_body": (
            "VO2max 70.5는 매우 강한 엔진을 보여주지만, 이번 데이터에서는 그 엔진이 threshold 지속성으로 완전히 연결되지는 않은 모습입니다. "
            "FatMax 280W에 비해 VT2 180W가 낮게 잡힌 점을 보면, 고출력 잠재력은 충분한데 실제 지속 가능한 middle-high aerobic 운영을 더 다듬을 필요가 있습니다. "
            "즉, 지금은 더 강한 인터벌을 추가하는 것보다 160-210W 부근의 긴 지속 구간과 안정적인 호흡 패턴을 쌓아 두는 편이 전체 퍼포먼스를 더 크게 끌어올릴 수 있습니다."
        ),
    },
    {
        "workspace": "20260330-ywc-greenna-kim",
        "subject_name": "Greenna Kim",
        "test_date": "2026-01-16",
        "comment_title": "Greenna Kim 코멘트",
        "comment_body": (
            "이번 결과는 현재 threshold가 아직 이른 시점에서 형성되고 있어, 먼저 기본 지구력과 sub-threshold 적응을 차분히 키우는 접근이 맞다는 쪽에 가깝습니다. "
            "VT1/VT2가 99W에서 겹쳐 보인 것은 강도 상승에 대한 여유 구간이 아직 좁다는 뜻이므로, 당분간은 무리해서 상단을 올리기보다 90-120W 부근에서 편안함과 지속 시간을 늘리는 것이 더 중요합니다. "
            "기본기가 올라오면 지금보다 더 높은 출력에서도 호흡과 연료 사용이 훨씬 안정적으로 정리될 가능성이 큽니다."
        ),
    },
]


def inject_personal_comment(report_path: Path, title: str, body: str) -> None:
    soup = BeautifulSoup(report_path.read_text(encoding="utf-8"), "html.parser")

    style_tag = soup.find("style", attrs={"data-ywc-personal-comment": "true"})
    if style_tag is None:
        head = soup.head or soup
        style_tag = soup.new_tag("style")
        style_tag["data-ywc-personal-comment"] = "true"
        style_tag.string = """
    .personal-comment {
      margin-top: 18px;
      padding: 18px 20px;
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.18);
      backdrop-filter: blur(10px);
    }
    .personal-comment strong {
      display: block;
      margin-bottom: 8px;
      font-size: 0.95rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .personal-comment p {
      margin: 0;
      color: rgba(247, 241, 231, 0.94);
      line-height: 1.7;
      font-size: 0.98rem;
    }
        """.strip()
        head.append(style_tag)

    coach_section = soup.select_one("section.coach-brief")
    if coach_section is None:
        raise RuntimeError(f"coach-brief section not found in {report_path}")

    existing = coach_section.select_one(".personal-comment")
    if existing is not None:
        existing.decompose()

    comment_box = soup.new_tag("div", attrs={"class": "personal-comment"})
    title_tag = soup.new_tag("strong")
    title_tag.string = title
    body_tag = soup.new_tag("p")
    body_tag.string = body
    comment_box.append(title_tag)
    comment_box.append(body_tag)
    coach_section.append(comment_box)

    report_path.write_text(str(soup), encoding="utf-8")


def main() -> None:
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)

    for item in REPORTS:
        workspace = WORKSPACES_DIR / item["workspace"]
        report_path = workspace / "report" / "index.html"
        if not report_path.is_file():
            raise FileNotFoundError(f"missing report: {report_path}")

        inject_personal_comment(
            report_path,
            title=item["comment_title"],
            body=item["comment_body"],
        )
        slug = publish_report(
            workspace,
            item["subject_name"],
            item["test_date"],
            PUBLISHED_DIR,
        )
        print(f"{item['subject_name']} -> {slug}")


if __name__ == "__main__":
    main()
