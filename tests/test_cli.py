from flow_healer.cli import build_parser


def test_doctor_parser_accepts_preflight_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["doctor", "--preflight"])

    assert args.command == "doctor"
    assert args.preflight is True


def test_recycle_helpers_parser_accepts_idle_only_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["recycle-helpers", "--repo", "demo", "--idle-only"])

    assert args.command == "recycle-helpers"
    assert args.repo == "demo"
    assert args.idle_only is True
